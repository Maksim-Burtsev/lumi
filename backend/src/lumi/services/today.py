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
                    "subtitle": f"Просрочено · срок был {fmt_local(task.due_at, user.timezone)}",
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
                "title": thread.subject or "(без темы)",
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
                "subtitle": "Ждет решения",
                "ref_id": str(confirmation.id),
                "action_type": confirmation.action_type,
                "action_payload": confirmation.action_payload,
                **policy_to_dict(policy),
            })
        needs_attention = needs_attention[:8]

        # --- suggestions ------------------------------------------------------
        suggestions: list[dict] = []
        proposed = [e for e in events if e.status == CalendarEventStatus.PROPOSED]
        for event in proposed[:2]:
            suggestions.append({
                "id": f"confirm-block-{event.id}",
                "kind": "focus_block",
                "title": f"Принять фокус-блок «{event.title}»",
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
                "title": "Собрать план на день",
                "description": f"Есть {len(unplanned)} приоритетных задач без слотов",
                "action": {"type": "plan_day", "payload": {}},
            })
        backlog = [t for t in active_tasks if t.due_at is None]
        if backlog and len(suggestions) < 3:
            suggestions.append({
                "id": "suggest-backlog",
                "kind": "plan_day",
                "title": "Разобрать бэклог",
                "description": f"{len(backlog)} задач без срока — могу расставить их по свободным окнам",
                "action": {"type": "plan_day", "payload": {}},
            })
        if task_counts["tasks_overdue"] and len(suggestions) < 3:
            suggestions.append({
                "id": "suggest-overdue",
                "kind": "plan_day",
                "title": "Пересобрать день",
                "description": f"{task_counts['tasks_overdue']} задач просрочено — предложу новые слоты",
                "action": {"type": "plan_day", "payload": {}},
            })
        if now_local.hour >= 17 and len(suggestions) < 3:
            from datetime import timedelta as _td

            tomorrow = (now_local + _td(days=1)).strftime("%Y-%m-%d")
            suggestions.append({
                "id": "suggest-plan-tomorrow",
                "kind": "plan_day",
                "title": "Спланировать завтра",
                "description": "Вечер — лучшее время разложить завтрашний день по слотам",
                "action": {"type": "plan_day", "payload": {"date": tomorrow}},
            })
        if emails_need_reply:
            suggestions.append({
                "id": "suggest-triage",
                "kind": "email_triage",
                "title": "Разобрать почту",
                "description": f"{emails_need_reply} писем ждут ответа",
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
                f"{greeting_for(now_local)}, {user.first_name}"
                if user.first_name else greeting_for(now_local)
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
