"""TodayService: the aggregated 'command center' payload."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    AgentRun,
    CalendarEventStatus,
    EmailCategory,
    EmailThread,
    User,
)
from lumi.i18n import normalize_app_locale
from lumi.services.action_policy import policy_for_action, policy_to_dict
from lumi.services.calendar import CalendarService
from lumi.services.confirmations import ConfirmationService
from lumi.services.tasks import TaskService
from lumi.utils.time import fmt_local, greeting_for, local_day_bounds, local_now, utc_now


class TodayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskService(session)
        self.calendar = CalendarService(session)
        self.confirmations = ConfirmationService(session)

    async def build_payload(self, user: User) -> dict:
        locale = normalize_app_locale(user.locale)
        now = utc_now()
        now_local = local_now(user.timezone)
        day_start, day_end = local_day_bounds(now, user.timezone)

        events = await self.calendar.list_events(user, day_start, day_end)
        timeline = [
            {
                "id": str(e.id),
                "kind": (
                    "proposed" if e.status == CalendarEventStatus.PROPOSED
                    else ("focus" if e.source.value == "internal" and e.created_by == "agent" else "event")
                ),
                "title": e.title,
                "start_at": e.start_at.isoformat(),
                "end_at": e.end_at.isoformat(),
                "source": e.source.value,
                "status": e.status.value,
                "busy": e.busy,
                "meeting_url": e.metadata_.get("meeting_url"),
                **_private_note_fields(e.metadata_ or {}),
            }
            for e in events
        ]
        meetings_today = len([
            e for e in events
            if e.busy and e.status in (CalendarEventStatus.CONFIRMED, CalendarEventStatus.TENTATIVE)
        ])

        task_counts = await self.tasks.count_summary(user)
        active_tasks = await self.tasks.list_active(user, limit=200)

        # Tasks with a concrete due time today belong on the schedule, not in a side list.
        scheduled_task_ids = {e.source_task_id for e in events if e.source_task_id}
        for task in active_tasks:
            if task.id in scheduled_task_ids:
                continue  # already visible as its focus block
            if task.due_at and day_start <= task.due_at < day_end and task.due_at >= now:
                timeline.append({
                    "id": f"task-{task.id}",
                    "kind": "task",
                    "title": task.title,
                    "start_at": task.due_at.isoformat(),
                    "end_at": task.due_at.isoformat(),
                    "source": "internal",
                    "status": "confirmed",
                    "busy": False,
                })
        timeline.sort(key=lambda item: item["start_at"])

        needs_reply_count_result = await self.session.execute(
            select(func.count()).select_from(EmailThread).where(
                EmailThread.user_id == user.id,
                EmailThread.category == EmailCategory.NEEDS_REPLY,
            )
        )
        emails_need_reply = needs_reply_count_result.scalar_one()

        # --- needs attention ------------------------------------------------
        needs_attention: list[dict] = []
        for task in active_tasks:
            if task.due_at and task.due_at < now:
                needs_attention.append({
                    "id": f"task-overdue-{task.id}",
                    "kind": "overdue_task",
                    "title": task.title,
                    "subtitle": _overdue_subtitle(task.due_at, user.timezone, locale),
                    "ref_id": str(task.id),
                })
        important_threads = await self.session.execute(
            select(EmailThread)
            .where(
                EmailThread.user_id == user.id,
                EmailThread.category.in_([EmailCategory.NEEDS_REPLY, EmailCategory.DECISION_NEEDED]),
            )
            .order_by(EmailThread.importance.desc(), EmailThread.last_message_at.desc().nulls_last())
            .limit(3)
        )
        for thread in important_threads.scalars():
            sender = thread.participants[0] if thread.participants else ""
            needs_attention.append({
                "id": f"email-{thread.id}",
                "kind": "email",
                "title": thread.subject or _text(locale, "(no subject)", "(без темы)"),
                "subtitle": thread.summary or sender or None,
                "ref_id": str(thread.id),
            })
        for confirmation in await self.confirmations.list_pending(user, limit=3):
            policy = policy_for_action(confirmation.action_type)
            if policy.approval_mode == "auto":
                continue
            needs_attention.append({
                "id": f"confirmation-{confirmation.id}",
                "kind": "confirmation",
                "title": confirmation.prompt,
                "subtitle": _text(locale, "Needs decision", "Ждет решения"),
                "ref_id": str(confirmation.id),
                "action_type": confirmation.action_type,
                "action_payload": confirmation.action_payload,
                **policy_to_dict(policy, locale=locale),
            })
        needs_attention = needs_attention[:8]

        # --- suggestions ------------------------------------------------------
        suggestions: list[dict] = []
        proposed = [e for e in events if e.status == CalendarEventStatus.PROPOSED]
        for event in proposed[:2]:
            suggestions.append({
                "id": f"confirm-block-{event.id}",
                "kind": "focus_block",
                "title": _text(locale, f"Accept focus block \"{event.title}\"", f"Принять фокус-блок «{event.title}»"),
                "description": (
                    f"{fmt_local(event.start_at, user.timezone, '%H:%M')}–"
                    f"{fmt_local(event.end_at, user.timezone, '%H:%M')}"
                ),
                "action": {"type": "confirm_block", "payload": {"block_id": str(event.id)}},
            })
        unplanned = [t for t in active_tasks if t.priority.value in ("high", "urgent")]
        if unplanned and not proposed:
            suggestions.append({
                "id": "suggest-plan-day",
                "kind": "plan_day",
                "title": _text(locale, "Build today's plan", "Собрать план на день"),
                "description": _priority_tasks_description(len(unplanned), locale),
                "action": {"type": "plan_day", "payload": {}},
            })
        backlog = [t for t in active_tasks if t.due_at is None]
        if backlog and len(suggestions) < 3:
            suggestions.append({
                "id": "suggest-backlog",
                "kind": "plan_day",
                "title": _text(locale, "Sort the backlog", "Разобрать бэклог"),
                "description": _backlog_description(len(backlog), locale),
                "action": {"type": "plan_day", "payload": {}},
            })
        if task_counts["tasks_overdue"] and len(suggestions) < 3:
            suggestions.append({
                "id": "suggest-overdue",
                "kind": "plan_day",
                "title": _text(locale, "Rebuild the day", "Пересобрать день"),
                "description": _overdue_tasks_description(task_counts["tasks_overdue"], locale),
                "action": {"type": "plan_day", "payload": {}},
            })
        if now_local.hour >= 17 and len(suggestions) < 3:
            from datetime import timedelta as _td

            tomorrow = (now_local + _td(days=1)).strftime("%Y-%m-%d")
            suggestions.append({
                "id": "suggest-plan-tomorrow",
                "kind": "plan_day",
                "title": _text(locale, "Plan tomorrow", "Спланировать завтра"),
                "description": _text(
                    locale,
                    "Evening is a good time to block out tomorrow.",
                    "Вечер — лучшее время разложить завтрашний день по слотам",
                ),
                "action": {"type": "plan_day", "payload": {"date": tomorrow}},
            })
        if emails_need_reply:
            suggestions.append({
                "id": "suggest-triage",
                "kind": "email_triage",
                "title": _text(locale, "Triage inbox", "Разобрать почту"),
                "description": _emails_need_reply_description(emails_need_reply, locale),
                "action": {"type": "run_triage", "payload": {}},
            })

        # --- recent runs ------------------------------------------------------
        runs_result = await self.session.execute(
            select(AgentRun)
            .where(AgentRun.user_id == user.id)
            .order_by(AgentRun.created_at.desc())
            .limit(5)
        )
        recent_runs = [_run_brief(run) for run in runs_result.scalars()]

        return {
            "date": now_local.strftime("%Y-%m-%d"),
            "greeting": (
                f"{greeting_for(now_local, locale)}, {user.first_name}"
                if user.first_name else greeting_for(now_local, locale)
            ),
            "summary": {
                "meetings_today": meetings_today,
                "tasks_active": task_counts["tasks_active"],
                "tasks_due_today": task_counts["tasks_due_today"],
                "tasks_overdue": task_counts["tasks_overdue"],
                "emails_need_reply": emails_need_reply,
            },
            "timeline": timeline,
            "needs_attention": needs_attention,
            "suggestions": suggestions,
            "recent_runs": recent_runs,
        }


def _text(locale: str, en: str, ru: str) -> str:
    return en if locale == "en" else ru


def _private_note_fields(metadata: dict) -> dict:
    private_note = metadata.get("private_note")
    private_note_summary = metadata.get("private_note_summary")
    return {
        "private_note": private_note if isinstance(private_note, str) else None,
        "private_note_summary": private_note_summary if isinstance(private_note_summary, str) else None,
        "private_note_summary_status": metadata.get("private_note_summary_status"),
        "private_note_updated_at": metadata.get("private_note_updated_at"),
        "private_note_summary_updated_at": metadata.get("private_note_summary_updated_at"),
    }


def _en_plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _overdue_subtitle(due_at, timezone: str, locale: str) -> str:
    if locale == "en":
        return f"Overdue · due was {fmt_local(due_at, timezone)}"
    return f"Просрочено · срок был {fmt_local(due_at, timezone)}"


def _priority_tasks_description(count: int, locale: str) -> str:
    if locale == "en":
        return f"{count} priority {_en_plural(count, 'task', 'tasks')} without time slots"
    return f"Есть {count} приоритетных задач без слотов"


def _backlog_description(count: int, locale: str) -> str:
    if locale == "en":
        return f"{count} {_en_plural(count, 'task', 'tasks')} without a due date — I can place them into free windows"
    return f"{count} задач без срока — могу расставить их по свободным окнам"


def _overdue_tasks_description(count: int, locale: str) -> str:
    if locale == "en":
        return f"{count} overdue {_en_plural(count, 'task', 'tasks')} — I can suggest new slots"
    return f"{count} задач просрочено — предложу новые слоты"


def _emails_need_reply_description(count: int, locale: str) -> str:
    if locale == "en":
        return f"{count} {_en_plural(count, 'email needs', 'emails need')} a reply"
    return f"{count} писем ждут ответа"


def _run_brief(run: AgentRun) -> dict:
    duration_ms = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    return {
        "id": str(run.id),
        "type": run.type.value,
        "status": run.status.value,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": duration_ms,
        "result_summary": run.result_summary,
    }
