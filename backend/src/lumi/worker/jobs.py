"""arq worker jobs: digests, triage, planning, sync, reminders, compaction."""

from __future__ import annotations

import uuid
from datetime import timedelta
from time import monotonic
from typing import Any

import httpx
from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.bot.formatting import telegram_plain_text
from lumi.bot.keyboards import markup_from_buttons
from lumi.bot.media import ImageDownloadError, download_image_input, ref_from_metadata
from lumi.config import get_settings
from lumi.db.models import (
    AgentRun,
    AgentRunType,
    AssistantTurn,
    Conversation,
    ScheduledTask,
    User,
)
from lumi.db.session import session_scope
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import agent_run_id_var, get_logger
from lumi.services.runs import RunService
from lumi.services.turns import TurnService
from lumi.utils.text import chunk_telegram
from lumi.utils.time import fmt_local, utc_now
from lumi.worker.queue import enqueue_job

log = get_logger(__name__)


def _deadline_job_id(turn_id: str | uuid.UUID, deadline) -> str:
    return f"assistant-turn:{turn_id}:at:{int(deadline.timestamp() * 1000)}"


async def _load_user(session, user_id: str) -> User | None:
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()


async def _load_turn_user(session, turn: AssistantTurn) -> User | None:
    result = await session.execute(select(User).where(User.id == turn.user_id))
    return result.scalar_one_or_none()


def _telegram_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value


async def _telegram_api_post(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=5, read=20, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Telegram {method} returned non-JSON response") from exc
    if response.status_code >= 400 or data.get("ok") is not True:
        description = data.get("description") or response.text[:200]
        raise RuntimeError(f"Telegram {method} failed: {description}")
    return data


def _rich_message_payload(html: str) -> dict[str, Any]:
    return {"html": html, "skip_entity_detection": True}


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


async def send_turn_reply(
    *,
    user: User,
    turn: AssistantTurn,
    reply_text: str,
    buttons,
    reply_rich_html: str | None = None,
) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("cannot send turn reply: TELEGRAM_BOT_TOKEN is not set")
        return False
    from aiogram import Bot
    from aiogram.types import LinkPreviewOptions

    bot = Bot(token=settings.telegram_bot_token)
    chat_id = turn.telegram_chat_id or user.telegram_chat_id or user.telegram_user_id
    chunks = chunk_telegram(telegram_plain_text(reply_text))
    markup = markup_from_buttons(buttons)
    markup_payload = _telegram_json(markup)
    link_preview_options = LinkPreviewOptions(is_disabled=True)
    rich_html = reply_rich_html if reply_rich_html and len(chunks) == 1 else None
    use_bot_api_rich = bool(getattr(settings, "telegram_use_rich_messages", False))
    try:
        if turn.status_message_id and len(chunks) == 1:
            try:
                if rich_html and use_bot_api_rich:
                    await _telegram_api_post(
                        settings.telegram_bot_token,
                        "editMessageText",
                        _without_none({
                            "chat_id": chat_id,
                            "message_id": turn.status_message_id,
                            "rich_message": _rich_message_payload(rich_html),
                            "reply_markup": markup_payload,
                        }),
                    )
                    return True
                if rich_html:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=turn.status_message_id,
                        text=rich_html,
                        parse_mode="HTML",
                        link_preview_options=link_preview_options,
                        reply_markup=markup,
                    )
                    return True
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=turn.status_message_id,
                        text=chunks[0],
                        link_preview_options=link_preview_options,
                        reply_markup=markup,
                    )
                    return True
            except Exception:  # noqa: BLE001 — status edit can fail after restarts/deletes
                log.exception("telegram status edit failed; falling back to send_message")
        if rich_html:
            if use_bot_api_rich:
                try:
                    await _telegram_api_post(
                        settings.telegram_bot_token,
                        "sendRichMessage",
                        _without_none({
                            "chat_id": chat_id,
                            "rich_message": _rich_message_payload(rich_html),
                            "reply_markup": markup_payload,
                        }),
                    )
                    if turn.status_message_id:
                        try:
                            await bot.delete_message(chat_id=chat_id, message_id=turn.status_message_id)
                        except Exception:  # noqa: BLE001
                            log.info("telegram status delete skipped after rich send")
                    return True
                except Exception:  # noqa: BLE001 — rich messages are new; plain fallback must work
                    log.exception("telegram rich turn reply failed; falling back to send_message")
            await bot.send_message(
                chat_id=chat_id,
                text=rich_html,
                parse_mode="HTML",
                link_preview_options=link_preview_options,
                reply_markup=markup,
            )
            if turn.status_message_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=turn.status_message_id)
                except Exception:  # noqa: BLE001
                    log.info("telegram status delete skipped after html fallback")
            return True
        for i, chunk in enumerate(chunks):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                link_preview_options=link_preview_options,
                reply_markup=markup if i == len(chunks) - 1 else None,
            )
        return True
    except Exception:  # noqa: BLE001
        log.exception("telegram turn reply failed")
        return False
    finally:
        await bot.session.close()


async def edit_turn_status_message(
    *,
    user: User,
    turn: AssistantTurn,
    status_text: str,
) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token or not turn.status_message_id:
        return False
    from aiogram import Bot
    from aiogram.types import LinkPreviewOptions

    bot = Bot(token=settings.telegram_bot_token)
    chat_id = turn.telegram_chat_id or user.telegram_chat_id or user.telegram_user_id
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=turn.status_message_id,
            text=telegram_plain_text(status_text),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return True
    except Exception:  # noqa: BLE001 — progress edits are best-effort
        log.info("telegram progress status edit skipped")
        return False
    finally:
        await bot.session.close()


async def _enqueue_turn(turn: AssistantTurn, *, delay_seconds: float | None = None) -> None:
    kwargs: dict[str, Any] = {}
    if delay_seconds is not None:
        kwargs["_defer_by"] = timedelta(seconds=delay_seconds)
    elif turn.debounce_deadline_at:
        kwargs["_defer_until"] = turn.debounce_deadline_at
        kwargs["_job_id"] = _deadline_job_id(turn.id, turn.debounce_deadline_at)
    await enqueue_job("process_assistant_turn", str(turn.id), **kwargs)


async def _enqueue_turn_id(
    turn_id: str,
    *,
    delay_seconds: float | None = None,
    defer_until=None,
) -> str | None:
    kwargs: dict[str, Any] = {}
    if delay_seconds is not None:
        kwargs["_defer_by"] = timedelta(seconds=delay_seconds)
    if defer_until is not None:
        kwargs["_defer_until"] = defer_until
        kwargs["_job_id"] = _deadline_job_id(turn_id, defer_until)
    return await enqueue_job("process_assistant_turn", turn_id, **kwargs)


def _delivery_retry_delay(settings, retry_count: int) -> int:
    base = max(1, settings.telegram_turn_retry_base_seconds)
    return min(base * (2 ** max(0, retry_count - 1)), 300)


async def _download_turn_image(metadata: dict[str, Any], *, source: str):
    settings = get_settings()
    if not settings.telegram_bot_token:
        return None
    from aiogram import Bot

    ref = ref_from_metadata(metadata, source=source)
    if ref is None:
        return None
    bot = Bot(token=settings.telegram_bot_token)
    try:
        return await download_image_input(bot, ref)
    finally:
        await bot.session.close()


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
        await service.mark_failed(task, error)
    else:
        await service.mark_succeeded(task)


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

async def process_assistant_turn(ctx: dict[str, Any], turn_id: str) -> str:
    settings = get_settings()
    parsed_turn_id = uuid.UUID(turn_id)
    turn_snapshot: dict[str, Any]
    user_snapshot: dict[str, Any]

    async with session_scope() as session:
        turns = TurnService(session)
        acquired = await turns.acquire_turn(
            parsed_turn_id, lock_seconds=settings.telegram_turn_lock_seconds
        )
        if acquired.status == "deferred":
            if acquired.enqueue_at:
                await _enqueue_turn_id(turn_id, defer_until=acquired.enqueue_at)
            return "turn deferred"
        if acquired.status == "locked":
            await _enqueue_turn_id(turn_id, delay_seconds=3)
            return "turn locked"
        if acquired.status == "already_running":
            return "turn already running"
        if acquired.status == "not_ready":
            if acquired.turn is not None:
                await _enqueue_turn(acquired.turn)
            else:
                await _enqueue_turn_id(turn_id, delay_seconds=3)
            return "turn not ready"
        if acquired.status != "acquired" or acquired.turn is None:
            return f"turn {acquired.status}"

        turn = acquired.turn
        user = await _load_turn_user(session, turn)
        if user is None:
            await turns.fail_turn(turn.id, "user not found")
            return "user not found"

        turn_snapshot = {
            "id": turn.id,
            "conversation_id": turn.conversation_id,
            "telegram_chat_id": turn.telegram_chat_id,
            "primary_message_id": turn.primary_message_id,
            "input_text": turn.input_text,
            "payload": dict(turn.payload or {}),
            "status_message_id": turn.status_message_id,
            "retry_count": turn.retry_count,
        }
        user_snapshot = {
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "telegram_chat_id": user.telegram_chat_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

    payload = turn_snapshot["payload"]
    image = None
    image_payload = payload.get("image")
    if image_payload:
        try:
            image = await _download_turn_image(
                image_payload, source=image_payload.get("source") or "attached"
            )
        except ImageDownloadError as exc:
            next_turn = None
            async with session_scope() as session:
                next_turn = await TurnService(session).fail_turn(parsed_turn_id, str(exc))
            await send_turn_reply(
                user=user,
                turn=turn,
                reply_text="Не смог скачать картинку из Telegram. Пришли ее заново.",
                buttons=[],
            )
            if next_turn is not None:
                await _enqueue_turn(next_turn)
            return "image download failed"

    async def image_loader(metadata: dict):
        return await _download_turn_image(metadata, source="recent")

    last_progress_text: str | None = None
    last_progress_at = 0.0

    async def on_progress(status_text: str) -> None:
        nonlocal last_progress_at, last_progress_text
        status_text = telegram_plain_text(status_text).strip()
        if not status_text:
            return
        now = monotonic()
        if status_text == last_progress_text:
            return
        if last_progress_text is not None and now - last_progress_at < 1.0:
            return
        last_progress_text = status_text
        last_progress_at = now
        await edit_turn_status_message(user=user, turn=turn, status_text=status_text)

    try:
        async with session_scope() as session:
            result = await AssistantOrchestrator(session).handle_user_message(
                telegram_user_id=user_snapshot["telegram_user_id"],
                telegram_chat_id=turn_snapshot["telegram_chat_id"],
                telegram_message_id=turn_snapshot["primary_message_id"],
                text=str(payload.get("text") or turn_snapshot["input_text"] or ""),
                username=user_snapshot["username"],
                first_name=user_snapshot["first_name"],
                last_name=user_snapshot["last_name"],
                image=image,
                ignored_attachments=list(payload.get("ignored_attachments") or []),
                image_loader=image_loader,
                on_progress=on_progress,
                touch_last_seen=False,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("assistant turn failed", fields={"turn_id": turn_id})
        next_turn = None
        async with session_scope() as session:
            next_turn = await TurnService(session).fail_turn(parsed_turn_id, str(exc))
        await send_turn_reply(
            user=user,
            turn=turn,
            reply_text="Что-то пошло не так на моей стороне. Сообщение сохранено, попробуй еще раз.",
            buttons=[],
        )
        if next_turn is not None:
            await _enqueue_turn(next_turn)
        return f"turn failed: {exc}"

    reply_kwargs = {
        "user": user,
        "turn": turn,
        "reply_text": result.reply_text,
        "buttons": result.buttons,
    }
    if result.reply_rich_html:
        reply_kwargs["reply_rich_html"] = result.reply_rich_html
    delivered = await send_turn_reply(**reply_kwargs)
    if not delivered:
        next_turn = None
        retry_turn = None
        async with session_scope() as session:
            turns = TurnService(session)
            current = await session.get(AssistantTurn, parsed_turn_id)
            if current is None:
                return "turn missing"
            delivery_exhausted = current.retry_count + 1 >= settings.telegram_turn_max_retries
            if delivery_exhausted:
                next_turn = await turns.fail_turn(parsed_turn_id, "telegram delivery failed")
            else:
                retry_turn = await turns.retry_turn(
                    parsed_turn_id,
                    "telegram delivery failed",
                    delay_seconds=_delivery_retry_delay(settings, current.retry_count + 1),
                )
        if next_turn is not None:
            await _enqueue_turn(next_turn)
            return "turn delivery failed"
        if delivery_exhausted:
            return "turn delivery failed"
        if retry_turn is not None:
            await _enqueue_turn(retry_turn)
        return "turn delivery retry scheduled"

    if result.needs_compaction:
        await enqueue_job(
            "compact_conversation",
            str(user_snapshot["id"]),
            conversation_id=str(turn_snapshot["conversation_id"]),
            trigger="system",
            notify=False,
        )

    async with session_scope() as session:
        next_turn = await TurnService(session).complete_turn(parsed_turn_id)
    if next_turn is not None:
        await _enqueue_turn(next_turn)
    return "turn completed"


async def enqueue_due_assistant_turns(ctx: dict[str, Any]) -> str:
    enqueued = 0
    async with session_scope() as session:
        lease_seconds = max(30, get_settings().scheduler_tick_seconds * 2)
        turns = await TurnService(session).reserve_due_turns(limit=100, lease_seconds=lease_seconds)
        turn_ids = [str(turn.id) for turn in turns]
    for turn_id in turn_ids:
        job_id = await _enqueue_turn_id(turn_id)
        if job_id:
            enqueued += 1
    return f"enqueued {enqueued} assistant turns"


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
            await send_telegram_message(user, "No active tasks; no review needed. Clear horizon.")
        return "no tasks"
    now = utc_now()
    lines = []
    for t in tasks:
        line = f"- [{t.priority.value}] {t.title}"
        if t.due_at:
            line += f" (due {fmt_local(t.due_at, user.timezone)}"
            line += ", OVERDUE)" if t.due_at < now else ")"
        lines.append(line)
    response = await LLMGateway().complete(
        messages=[
            LLMMessage(
                role="user",
                content=f"Target language: {user.locale or 'en'}\nTasks:\n" + "\n".join(lines),
            )
        ],
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
        format_hint = "\n\nFormat the result as a structured Markdown document with headings."
    elif output_format == "html":
        format_hint = (
            "\n\nFormat the result as a complete self-contained HTML document "
            "(one file, polished typography, no external dependencies)."
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


async def cleanup_ui_events(ctx: dict[str, Any]) -> str:
    """Delete realtime outbox events after the reconnect catch-up window."""
    from lumi.services.realtime import RealtimeEventService

    async with session_scope() as session:
        deleted = await RealtimeEventService(session).delete_older_than(
            utc_now() - timedelta(hours=72)
        )
    return f"deleted {deleted}"


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
