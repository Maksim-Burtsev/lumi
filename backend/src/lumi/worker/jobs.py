"""arq worker jobs: digests, triage, planning, sync, reminders, compaction."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from lumi.db.models import (
    AgentRun,
    AgentRunType,
    Conversation,
    ScheduledTask,
    User,
)
from lumi.db.session import session_scope
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import agent_run_id_var, get_logger
from lumi.services.runs import RunService
from lumi.utils.time import fmt_local, utc_now

log = get_logger(__name__)


async def _load_user(session, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()


async def _get_or_create_run(
    session, *, user: User, run_id: str | None, type_: AgentRunType, trigger: str,
    scheduled_task_id: str | None = None,
) -> AgentRun:
    runs = RunService(session)
    if run_id:
        run = await runs.get(uuid.UUID(run_id), user.id)
        if run:
            return run
    return await runs.create(
        user_id=user.id,
        type_=type_,
        trigger=trigger,
        scheduled_task_id=uuid.UUID(scheduled_task_id) if scheduled_task_id else None,
    )


async def _update_scheduled_task(session, scheduled_task_id: str | None, *, error: str | None) -> None:
    if not scheduled_task_id:
        return
    result = await session.execute(
        select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(scheduled_task_id))
    )
    task = result.scalar_one_or_none()
    if task is None:
        return
    from lumi.services.automations import AutomationService

    service = AutomationService(session)
    if error:
        service.mark_failed(task, error)
    else:
        service.mark_succeeded(task)


def _job(type_: AgentRunType):
    """Decorator: run lifecycle, scheduled task bookkeeping, error isolation."""

    def wrap(fn):
        async def runner(
            ctx: dict[str, Any],
            user_id: str,
            *,
            agent_run_id: str | None = None,
            scheduled_task_id: str | None = None,
            trigger: str = "manual_api",
            notify: bool = True,
            **kwargs: Any,
        ) -> str:
            async with session_scope() as session:
                user = await _load_user(session, user_id)
                if user is None:
                    return "user not found"
                run = await _get_or_create_run(
                    session, user=user, run_id=agent_run_id, type_=type_,
                    trigger=trigger, scheduled_task_id=scheduled_task_id,
                )
                runs = RunService(session)
                await runs.mark_running(run)
                agent_run_id_var.set(str(run.id))
                try:
                    summary = await fn(
                        session=session, user=user, run=run, notify=notify, **kwargs
                    )
                    await runs.mark_completed(run, summary)
                    await _update_scheduled_task(session, scheduled_task_id, error=None)
                    return summary or "ok"
                except Exception as exc:  # noqa: BLE001 — job must record its own failure
                    log.exception("job failed", fields={"job": fn.__name__})
                    await runs.mark_failed(run, str(exc))
                    await _update_scheduled_task(session, scheduled_task_id, error=str(exc))
                    return f"failed: {exc}"

        # arq registers functions by __qualname__ — make the wrapper transparent.
        runner.__name__ = fn.__name__
        runner.__qualname__ = fn.__name__
        return runner

    return wrap


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@_job(AgentRunType.MORNING_BRIEF)
async def run_morning_brief(*, session, user: User, run: AgentRun, notify: bool) -> str:
    """One message: today's plan (meetings + tasks) + mail + news."""
    from lumi.bot.formatting import format_today
    from lumi.connectors.google.auth import GoogleNotConnectedError, token_file_exists
    from lumi.services.email import EmailService
    from lumi.services.news import NewsService
    from lumi.services.notifier import send_telegram_message
    from lumi.services.today import TodayService

    parts: list[str] = []
    payload = await TodayService(session).build_payload(user)
    parts.append(format_today(payload, user.timezone))

    if token_file_exists():
        try:
            triage, _threads = await EmailService(session).triage_inbox(user, agent_run_id=run.id)
            if triage.telegram_digest:
                parts.append("📬 Почта\n" + triage.telegram_digest)
        except GoogleNotConnectedError:
            pass
        except Exception:  # noqa: BLE001 — почта не должна валить весь бриф
            log.exception("morning brief: triage failed")

    try:
        digest = await NewsService(session).generate_digest(user, agent_run_id=run.id)
        if digest is not None:
            parts.append("📰 Новости\n" + digest.digest_text)
    except Exception:  # noqa: BLE001
        log.exception("morning brief: news failed")

    text = "\n\n———\n\n".join(parts)
    if notify:
        await send_telegram_message(user, text)
    return f"brief: {len(parts)} sections"


@_job(AgentRunType.NEWS_DIGEST)
async def run_news_digest(*, session, user: User, run: AgentRun, notify: bool) -> str:
    from lumi.services.news import NewsService
    from lumi.services.notifier import send_telegram_message

    digest = await NewsService(session).generate_digest(user, agent_run_id=run.id)
    if digest is None:
        if notify:
            await send_telegram_message(user, "Новостных тем пока нет — добавь их в Mini App, раздел News.")
        return "no topics"
    if notify:
        await send_telegram_message(user, digest.digest_text)
    return f"digest: {len(digest.items_json)} items"


@_job(AgentRunType.EMAIL_TRIAGE)
async def run_email_triage(*, session, user: User, run: AgentRun, notify: bool) -> str:
    from lumi.connectors.google.auth import GoogleNotConnectedError
    from lumi.services.email import EmailService
    from lumi.services.notifier import send_telegram_message

    try:
        triage, threads = await EmailService(session).triage_inbox(user, agent_run_id=run.id)
    except GoogleNotConnectedError:
        if notify:
            await send_telegram_message(
                user,
                "Gmail не подключен. Подключи Google: положи client_secret.json в data/secrets "
                "и выполни make google-auth-local.",
            )
        return "google not connected"
    if notify and triage.telegram_digest:
        reply_markup = None
        candidates = [
            t for t in threads
            if t.metadata_.get("task_candidate")
        ]
        if candidates:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"✓ Создать задачи ({len(candidates)})",
                    callback_data="email_create_tasks",
                )
            ]])
        await send_telegram_message(user, triage.telegram_digest, reply_markup=reply_markup)
    return f"triaged {len(threads)} threads"


@_job(AgentRunType.DAILY_PLANNING)
async def run_daily_planning(*, session, user: User, run: AgentRun, notify: bool,
                             plan_date: str = "") -> str:
    from datetime import datetime as _dt

    from lumi.services.notifier import send_telegram_message
    from lumi.services.planning import PlanningService
    from lumi.utils.time import get_zone, utc_to_local

    day = None
    if plan_date:
        try:
            parsed = _dt.fromisoformat(plan_date)
            # Anchor at local noon so day-bounds resolve to the right date.
            day = parsed.replace(hour=12, tzinfo=get_zone(user.timezone))
        except ValueError:
            day = None
    summary, created = await PlanningService(session).propose_day_plan(
        user, day=day, agent_run_id=run.id
    )
    if notify:
        reply_markup = None
        if created:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            rows = [
                [InlineKeyboardButton(
                    text=(
                        f"✓ Принять {utc_to_local(e.start_at, user.timezone).strftime('%H:%M')}"
                        f" {e.title[:24]}"
                    ),
                    callback_data=f"block_confirm:{e.id}",
                )]
                for e in created[:3]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)
        await send_telegram_message(user, summary, reply_markup=reply_markup)
    return f"plan: {len(created)} blocks proposed"


@_job(AgentRunType.CALENDAR_SYNC)
async def run_calendar_sync(*, session, user: User, run: AgentRun, notify: bool) -> str:
    from lumi.connectors.google.auth import GoogleNotConnectedError
    from lumi.services.notifier import send_telegram_message
    from lumi.services.planning import CalendarSyncService

    try:
        results = await CalendarSyncService(session).sync_all_calendars(user)
    except GoogleNotConnectedError:
        if notify:
            await send_telegram_message(
                user,
                "Внешний календарь не подключен — внутренний календарь продолжает работать. "
                "Подключить Google или Яндекс можно в Mini App → Settings.",
            )
        return "no external calendar connected"
    parts = []
    for provider, value in results.items():
        label = {"google": "Google", "yandex": "Яндекс"}.get(provider, provider)
        parts.append(f"{label}: {value if isinstance(value, int) else 'ошибка'}")
    summary = "synced " + ", ".join(f"{k}={v}" for k, v in results.items())
    if notify:
        await send_telegram_message(
            user, "Календарь синхронизирован. Событий за 14 дней — " + "; ".join(parts) + "."
        )
    return summary


@_job(AgentRunType.TASK_REVIEW)
async def run_task_review(*, session, user: User, run: AgentRun, notify: bool) -> str:
    from lumi.assistant.prompts import TASK_REVIEW_SYSTEM
    from lumi.services.notifier import send_telegram_message
    from lumi.services.tasks import TaskService

    tasks = await TaskService(session).list_active(user, limit=50)
    if not tasks:
        if notify:
            await send_telegram_message(user, "Активных задач нет — обзор не нужен. Чистый горизонт.")
        return "no tasks"
    now = utc_now()
    lines = []
    for t in tasks:
        line = f"- [{t.priority.value}] {t.title}"
        if t.due_at:
            line += f" (срок {fmt_local(t.due_at, user.timezone)}"
            line += ", ПРОСРОЧЕНО)" if t.due_at < now else ")"
        lines.append(line)
    response = await LLMGateway().complete(
        messages=[LLMMessage(role="user", content="Задачи:\n" + "\n".join(lines))],
        system=TASK_REVIEW_SYSTEM,
        request_kind="task_review",
        user_id=user.id,
        agent_run_id=run.id,
        session=session,
    )
    if notify:
        await send_telegram_message(user, response.text.strip())
    return f"reviewed {len(tasks)} tasks"


@_job(AgentRunType.CUSTOM)
async def run_custom_prompt(*, session, user: User, run: AgentRun, notify: bool,
                            prompt: str = "") -> str:
    from lumi.assistant.prompts import LUMI_SYSTEM_PROMPT
    from lumi.services.notifier import send_telegram_message

    if not prompt:
        # Pull prompt from the scheduled task config.
        if run.scheduled_task_id:
            result = await session.execute(
                select(ScheduledTask).where(ScheduledTask.id == run.scheduled_task_id)
            )
            scheduled = result.scalar_one_or_none()
            prompt = (scheduled.config or {}).get("prompt", "") if scheduled else ""
    if not prompt:
        return "empty prompt"
    config = {}
    if run.scheduled_task_id:
        result = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == run.scheduled_task_id)
        )
        scheduled = result.scalar_one_or_none()
        config = (scheduled.config or {}) if scheduled else {}
    output_format = config.get("format", "text")  # text | md | html

    format_hint = ""
    if output_format == "md":
        format_hint = "\n\nОформи результат как структурированный Markdown-документ с заголовками."
    elif output_format == "html":
        format_hint = (
            "\n\nОформи результат как полный самодостаточный HTML-документ "
            "(один файл, аккуратная типографика, без внешних зависимостей)."
        )
    response = await LLMGateway().complete(
        messages=[LLMMessage(role="user", content=prompt + format_hint)],
        system=LUMI_SYSTEM_PROMPT,
        max_tokens=4096,
        request_kind="custom_prompt",
        user_id=user.id,
        agent_run_id=run.id,
        session=session,
    )
    text_out = response.text.strip()
    if notify:
        if output_format in ("md", "html"):
            from lumi.services.notifier import send_telegram_document
            from lumi.utils.time import local_now

            stamp = local_now(user.timezone).strftime("%d-%m-%H%M")
            ext = "md" if output_format == "md" else "html"
            title = (config.get("title") or "lumi-report").replace(" ", "-")[:40]
            ok = await send_telegram_document(
                user,
                file_name=f"{title}-{stamp}.{ext}",
                content=text_out.encode("utf-8"),
                caption="Готово — результат во вложении.",
            )
            if not ok:
                await send_telegram_message(user, text_out)
        else:
            await send_telegram_message(user, text_out)
    return f"custom prompt done ({output_format})"


@_job(AgentRunType.COMPACTION)
async def compact_conversation(*, session, user: User, run: AgentRun, notify: bool,
                               conversation_id: str = "") -> str:
    from lumi.assistant.compaction import CompactionService

    result = await session.execute(
        select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return "conversation not found"
    summary = await CompactionService(session).compact(user, conversation, agent_run_id=run.id)
    return f"compacted {summary.message_count} messages" if summary else "nothing to compact"


# ---------------------------------------------------------------------------
# Reminders (cron, every minute)
# ---------------------------------------------------------------------------

async def send_due_reminders(ctx: dict[str, Any]) -> str:
    """arq cron job: find due reminders across users and notify."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from lumi.services.notifier import send_telegram_message
    from lumi.services.tasks import TaskService

    sent = 0
    async with session_scope() as session:
        tasks_service = TaskService(session)
        due = await tasks_service.find_due_reminders()
        for task in due:
            result = await session.execute(select(User).where(User.id == task.user_id))
            user = result.scalar_one_or_none()
            if user is None:
                continue
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✓ Выполнено", callback_data=f"task_done:{task.id}"),
                InlineKeyboardButton(text="⏰ Через час", callback_data=f"task_snooze:{task.id}:1h"),
                InlineKeyboardButton(text="📅 Завтра", callback_data=f"task_snooze:{task.id}:tomorrow"),
            ]])
            text = f"⏰ Напоминание: {task.title}"
            if task.due_at:
                text += f"\nСрок: {fmt_local(task.due_at, user.timezone)}"
            ok = await send_telegram_message(user, text, reply_markup=markup)
            if ok:
                await tasks_service.mark_reminder_sent(task)
                sent += 1
    if sent:
        log.info("reminders sent", fields={"count": sent})
    return f"sent {sent}"


JOB_BY_AUTOMATION_TYPE = {
    "morning_brief": "run_morning_brief",
    "news_digest": "run_news_digest",
    "email_triage": "run_email_triage",
    "daily_planning": "run_daily_planning",
    "calendar_sync": "run_calendar_sync",
    "task_review": "run_task_review",
    "custom_prompt": "run_custom_prompt",
}

AGENT_RUN_TYPE_BY_AUTOMATION = {
    "morning_brief": AgentRunType.MORNING_BRIEF,
    "news_digest": AgentRunType.NEWS_DIGEST,
    "email_triage": AgentRunType.EMAIL_TRIAGE,
    "daily_planning": AgentRunType.DAILY_PLANNING,
    "calendar_sync": AgentRunType.CALENDAR_SYNC,
    "task_review": AgentRunType.TASK_REVIEW,
    "custom_prompt": AgentRunType.CUSTOM,
}
