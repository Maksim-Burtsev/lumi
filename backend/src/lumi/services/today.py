"""TodayService: the aggregated 'command center' payload."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.serializers import task_to_dict
from lumi.db.models import (
    AgentRun,
    AgentRunType,
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    Task,
    TaskStatus,
    User,
)
from lumi.i18n import normalize_app_locale
from lumi.services.action_policy import policy_for_action, policy_to_dict
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.calendar import CalendarService
from lumi.services.confirmations import ConfirmationService
from lumi.services.focus import FocusService
from lumi.services.planning import next_planning_workday
from lumi.services.planning_settings import planning_work_window
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

        events = [
            event for event in await self.calendar.list_events(user, day_start, day_end)
            if not _proposal_is_stale(event, now)
        ]
        timeline = [_event_timeline_item(event) for event in events]
        focus = FocusService(self.session)
        focus_sessions = await focus.completed_between(user, day_start, day_end)
        active_focus = await focus.get_active(user)
        if (
            active_focus is not None
            and active_focus.started_at < day_end
            and active_focus.target_end_at > day_start
        ):
            focus_sessions.append(active_focus)
        for session in focus_sessions:
            timeline.append({
                "id": f"focus-{session.id}",
                "kind": "focus_session",
                "title": session.intention,
                "start_at": session.started_at.isoformat(),
                "end_at": (session.ended_at or session.target_end_at).isoformat(),
                "source": "internal",
                "status": "confirmed",
                "busy": False,
            })
        meetings_today = len([
            e for e in events
            if (
                e.busy
                and e.source_task_id is None
                and e.status in (
                    CalendarEventStatus.CONFIRMED,
                    CalendarEventStatus.TENTATIVE,
                )
            )
        ])

        task_counts = await self.tasks.count_summary(user)
        active_tasks = await self.tasks.list_active(user, limit=200)

        # Tasks with a concrete due time today belong on the schedule, not in a side list.
        scheduled_task_ids = {e.source_task_id for e in events if e.source_task_id}
        open_task_ids = (
            set(
                await self.session.scalars(
                    select(Task.id).where(
                        Task.id.in_(scheduled_task_ids),
                        Task.user_id == user.id,
                        Task.status.in_((TaskStatus.INBOX, TaskStatus.ACTIVE)),
                    )
                )
            )
            if scheduled_task_ids
            else set()
        )
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
        work_window = planning_work_window(user.settings, now, user.timezone)
        work_minutes = _window_minutes(work_window)
        free_slots = await self.calendar.find_free_slots(
            user,
            day=now,
            duration_minutes=1,
        )
        free_minutes = sum(
            _interval_minutes(start, end)
            for start, end in free_slots
        )
        meeting_minutes = sum(
            _event_minutes_in_window(event, work_window)
            for event in events
            if (
                event.busy
                and event.source_task_id is None
                and event.status in (
                    CalendarEventStatus.CONFIRMED,
                    CalendarEventStatus.TENTATIVE,
                )
            )
        )
        planned_minutes = sum(
            _event_minutes_in_window(event, work_window)
            for event in events
            if (
                event.source == CalendarSource.INTERNAL
                and event.source_task_id is not None
                and event.status in (
                    CalendarEventStatus.CONFIRMED,
                    CalendarEventStatus.PROPOSED,
                )
            )
        )
        focus_minutes = sum(
            max(0, (session.duration_seconds or 0) // 60)
            for session in focus_sessions
        )
        occupied_minutes = meeting_minutes + planned_minutes
        utilization_percent = (
            round(occupied_minutes * 100 / work_minutes)
            if work_minutes
            else 0
        )
        work_blocks = [
            event
            for event in events
            if (
                event.source == CalendarSource.INTERNAL
                and event.source_task_id is not None
                and event.source_task_id in open_task_ids
                and event.status == CalendarEventStatus.CONFIRMED
                and event.end_at > now
                and (
                    active_focus is None
                    or active_focus.planned_event_id != event.id
                )
                and not _work_block_is_impacted(event)
            )
        ]
        next_block = (
            _event_timeline_item(min(work_blocks, key=lambda event: event.start_at))
            if work_blocks
            else None
        )
        planned_task_ids = {
            event.source_task_id
            for event in events
            if event.source_task_id is not None
        }
        planned_tasks = [
            task_to_dict(task, timezone=user.timezone, now=now)
            for task in active_tasks
            if (
                task.id in planned_task_ids
                or (task.target_at is not None and day_start <= task.target_at < day_end)
                or (task.due_at is not None and day_start <= task.due_at < day_end)
            )
        ]
        tomorrow = next_planning_workday(user, now=now)
        proposal_expiries = [
            expiry
            for event in events
            if event.status == CalendarEventStatus.PROPOSED
            if (expiry := _proposal_expiry(event)) is not None
        ]

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
        proposed = [e for e in events if e.status == CalendarEventStatus.PROPOSED and e.end_at > now]
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
            suggestions.append({
                "id": "suggest-plan-tomorrow",
                "kind": "plan_day",
                "title": _text(locale, "Plan tomorrow", "Спланировать завтра"),
                "description": _text(
                    locale,
                    "Evening is a good time to block out tomorrow.",
                    "Вечер — лучшее время разложить завтрашний день по слотам",
                ),
                "action": {
                    "type": "plan_day",
                    "payload": {"date": tomorrow.strftime("%Y-%m-%d")},
                },
            })
        # --- precomputed slot suggestions ------------------------------------
        slot_suggestions = []
        assistant_suggestions = AssistantSuggestionService(self.session)
        for suggestion in await assistant_suggestions.list_pending(user, kind="micro_slot", limit=8):
            slot = suggestion.payload.get("slot") if isinstance(suggestion.payload, dict) else None
            start_raw = slot.get("start_at") if isinstance(slot, dict) else None
            end_raw = slot.get("end_at") if isinstance(slot, dict) else None
            start_at = suggestion.start_at or _parse_dt(start_raw)
            end_at = suggestion.end_at or _parse_dt(end_raw)
            if start_at is None or end_at is None or end_at <= now:
                continue
            tasks = suggestion.payload.get("tasks") if isinstance(suggestion.payload, dict) else []
            slot_suggestions.append({
                "id": str(suggestion.id),
                "title": suggestion.title,
                "description": suggestion.description,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "tasks": tasks if isinstance(tasks, list) else [],
                "reason": suggestion.payload.get("reason") if isinstance(suggestion.payload, dict) else None,
                "source": suggestion.payload.get("source") if isinstance(suggestion.payload, dict) else None,
            })

        # --- recent runs ------------------------------------------------------
        runs_result = await self.session.execute(
            select(AgentRun)
            .where(
                AgentRun.user_id == user.id,
                AgentRun.type.notin_(
                    (AgentRunType.EMAIL_TRIAGE, AgentRunType.NEWS_DIGEST)
                ),
            )
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
            },
            "capacity": {
                "work_minutes": work_minutes,
                "meeting_minutes": meeting_minutes,
                "planned_minutes": planned_minutes,
                "focus_minutes": focus_minutes,
                "free_minutes": free_minutes,
                "utilization_percent": utilization_percent,
                "over_capacity": occupied_minutes > work_minutes if work_minutes else False,
            },
            "next_block": next_block,
            "planned_tasks": planned_tasks,
            "planning": {
                "tomorrow_date": tomorrow.strftime("%Y-%m-%d"),
                "can_replan": any(
                    event.status == CalendarEventStatus.PROPOSED
                    and event.start_at >= now
                    for event in events
                ),
                "proposal_expires_at": (
                    min(proposal_expiries).isoformat()
                    if proposal_expiries
                    else None
                ),
            },
            "timeline": timeline,
            "needs_attention": needs_attention,
            "suggestions": suggestions,
            "slot_suggestions": slot_suggestions,
            "recent_runs": recent_runs,
        }


def _proposal_expiry(event: CalendarEvent) -> datetime | None:
    raw_expiry = (event.metadata_ or {}).get("proposal_expires_at")
    if not isinstance(raw_expiry, str):
        return None
    try:
        expiry = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        return None
    return expiry


def _proposal_is_stale(event: CalendarEvent, now: datetime) -> bool:
    if event.status != CalendarEventStatus.PROPOSED:
        return False
    expiry = _proposal_expiry(event)
    return event.end_at <= now or (expiry is not None and expiry <= now)


def _work_block_is_impacted(event: CalendarEvent) -> bool:
    conflict = (event.metadata_ or {}).get("work_block_conflict")
    return isinstance(conflict, dict) and conflict.get("status") == "impacted"


def _event_timeline_item(event: CalendarEvent) -> dict:
    if event.status == CalendarEventStatus.PROPOSED:
        kind = "proposed"
    elif event.source == CalendarSource.INTERNAL and event.source_task_id is not None:
        kind = "work_block"
    elif event.source != CalendarSource.INTERNAL:
        kind = "meeting"
    else:
        kind = "event"
    expiry = _proposal_expiry(event)
    return {
        "id": str(event.id),
        "kind": kind,
        "title": event.title,
        "start_at": event.start_at.isoformat(),
        "end_at": event.end_at.isoformat(),
        "source": event.source.value,
        "status": event.status.value,
        "busy": event.busy,
        "meeting_url": (event.metadata_ or {}).get("meeting_url"),
        "expires_at": expiry.isoformat() if expiry else None,
        **_private_note_fields(event.metadata_ or {}),
    }


def _interval_minutes(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def _window_minutes(window: tuple[datetime, datetime] | None) -> int:
    return _interval_minutes(*window) if window is not None else 0


def _event_minutes_in_window(
    event: CalendarEvent,
    window: tuple[datetime, datetime] | None,
) -> int:
    if window is None:
        return 0
    start, end = window
    return _interval_minutes(max(start, event.start_at), min(end, event.end_at))


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
