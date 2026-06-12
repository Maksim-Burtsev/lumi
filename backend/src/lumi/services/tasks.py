"""TaskService: create/complete/snooze tasks, reminders, audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.schemas import ExtractedTask
from lumi.db.models import Priority, Task, TaskEvent, TaskStatus, User
from lumi.services.audit import AuditService
from lumi.utils.time import local_day_bounds, local_to_utc, utc_now

SNOOZE_PRESETS = {"1h": timedelta(hours=1), "3h": timedelta(hours=3)}


def _task_snapshot(task: Task) -> dict[str, Any]:
    return {
        "title": task.title,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
        "priority": task.priority.value if isinstance(task.priority, Priority) else task.priority,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
        "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
    }


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # --- creation -----------------------------------------------------

    async def create_task(
        self,
        user: User,
        *,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        project: str | None = None,
        tags: list[str] | None = None,
        due_at: datetime | None = None,
        reminder_at: datetime | None = None,
        source: str = "manual",
        source_message_id: uuid.UUID | None = None,
        created_by: str = "user",
        actor: str = "user",
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        task = Task(
            user_id=user.id,
            title=title.strip()[:300],
            description=description,
            status=TaskStatus.ACTIVE,
            priority=Priority(priority),
            project=project,
            tags=tags or [],
            due_at=due_at,
            reminder_at=reminder_at,
            source=source,
            source_message_id=source_message_id,
            created_by=created_by,
        )
        self.session.add(task)
        await self.session.flush()
        await self._record_event(task, "created", actor=actor, after=_task_snapshot(task),
                                 agent_run_id=agent_run_id)
        await self.audit.log(user_id=user.id, actor=actor, entity_type="task",
                             entity_id=task.id, action="created", details={"title": task.title})
        return task

    async def find_active_by_title(self, user: User, title: str) -> Task | None:
        from lumi.utils.text import normalize_for_match

        wanted = normalize_for_match(title)
        for task in await self.list_active(user, limit=200):
            if normalize_for_match(task.title) == wanted:
                return task
        return None

    async def create_task_from_signal(
        self,
        user: User,
        signal: ExtractedTask,
        *,
        source_message_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> Task:
        # The agent must not create the same task twice (repeated phrasing,
        # re-extraction): refresh the existing one instead.
        existing = await self.find_active_by_title(user, signal.title)
        if existing is not None:
            updated = False
            if signal.due_at_local and existing.due_at is None:
                existing.due_at = local_to_utc(signal.due_at_local, user.timezone)
                updated = True
            if signal.reminder_at_local and existing.reminder_at is None:
                existing.reminder_at = local_to_utc(signal.reminder_at_local, user.timezone)
                updated = True
            if updated:
                await self._record_event(existing, "updated", actor="agent",
                                         after=_task_snapshot(existing),
                                         agent_run_id=agent_run_id)
            return existing

        due_at = local_to_utc(signal.due_at_local, user.timezone) if signal.due_at_local else None
        reminder_at = (
            local_to_utc(signal.reminder_at_local, user.timezone) if signal.reminder_at_local else None
        )
        return await self.create_task(
            user,
            title=signal.title,
            description=signal.description,
            priority=signal.priority,
            project=signal.project,
            tags=signal.tags,
            due_at=due_at,
            reminder_at=reminder_at,
            source="chat",
            source_message_id=source_message_id,
            created_by="agent",
            actor="agent",
            agent_run_id=agent_run_id,
        )

    # --- queries -------------------------------------------------------

    async def get(self, user: User, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user.id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(self, user: User, *, filter_: str = "all", limit: int = 100) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user.id)
        now = utc_now()
        day_start, day_end = local_day_bounds(now, user.timezone)
        active = Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX])

        if filter_ == "today":
            stmt = stmt.where(active, Task.due_at.is_not(None), Task.due_at < day_end)
            stmt = stmt.order_by(Task.due_at.asc())
        elif filter_ == "upcoming":
            stmt = stmt.where(active, or_(Task.due_at.is_(None), Task.due_at >= day_end))
            stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
        elif filter_ == "inbox":
            stmt = stmt.where(Task.status == TaskStatus.INBOX).order_by(Task.created_at.desc())
        elif filter_ == "done":
            stmt = stmt.where(Task.status == TaskStatus.DONE).order_by(Task.completed_at.desc())
        else:
            stmt = stmt.where(active).order_by(
                Task.due_at.asc().nulls_last(), Task.created_at.desc()
            )
        result = await self.session.execute(stmt.limit(limit))
        return list(result.scalars())

    async def list_active(self, user: User, limit: int = 50) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]))
            .order_by(Task.due_at.asc().nulls_last(), Task.priority.desc(), Task.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def count_summary(self, user: User) -> dict[str, int]:
        now = utc_now()
        _, day_end = local_day_bounds(now, user.timezone)
        tasks = await self.list_active(user, limit=500)
        due_today = [t for t in tasks if t.due_at and t.due_at < day_end and t.due_at >= now]
        overdue = [t for t in tasks if t.due_at and t.due_at < now]
        return {
            "tasks_active": len(tasks),
            "tasks_due_today": len(due_today),
            "tasks_overdue": len(overdue),
        }

    # --- mutations -----------------------------------------------------

    async def update_task(
        self, user: User, task: Task, updates: dict[str, Any], *, actor: str = "user"
    ) -> Task:
        before = _task_snapshot(task)
        allowed = {"title", "description", "priority", "project", "tags",
                   "due_at", "reminder_at", "status"}
        for key, value in updates.items():
            if key not in allowed or value is None and key in ("title",):
                continue
            if key == "priority" and value is not None:
                value = Priority(value)
            if key == "status" and value is not None:
                value = TaskStatus(value)
            setattr(task, key, value)
        await self._record_event(task, "updated", actor=actor, before=before,
                                 after=_task_snapshot(task))
        return task

    async def complete_task(self, user: User, task: Task, *, actor: str = "user") -> Task:
        before = _task_snapshot(task)
        task.status = TaskStatus.DONE
        task.completed_at = utc_now()
        await self._record_event(task, "completed", actor=actor, before=before,
                                 after=_task_snapshot(task))
        await self.audit.log(user_id=user.id, actor=actor, entity_type="task",
                             entity_id=task.id, action="completed", details={"title": task.title})
        return task

    async def snooze_task(
        self, user: User, task: Task, *, preset: str | None = None,
        until: datetime | None = None, actor: str = "user",
    ) -> Task:
        before = _task_snapshot(task)
        if until is None:
            if preset in SNOOZE_PRESETS:
                until = utc_now() + SNOOZE_PRESETS[preset]
            elif preset == "tomorrow":
                day_start, _ = local_day_bounds(utc_now() + timedelta(days=1), user.timezone)
                until = day_start + timedelta(hours=9)
            elif preset == "next_week":
                day_start, _ = local_day_bounds(utc_now() + timedelta(days=7), user.timezone)
                until = day_start + timedelta(hours=9)
            else:
                until = utc_now() + timedelta(hours=1)
        task.snoozed_until = until
        if task.reminder_at is not None:
            task.reminder_at = until
            task.metadata_ = {k: v for k, v in task.metadata_.items() if k != "reminder_sent_at"}
        await self._record_event(task, "snoozed", actor=actor, before=before,
                                 after=_task_snapshot(task))
        return task

    # --- reminders -----------------------------------------------------

    async def find_due_reminders(self, now: datetime | None = None) -> list[Task]:
        """Across all users: active tasks whose reminder time has come and was not sent yet."""
        now = now or utc_now()
        result = await self.session.execute(
            select(Task).where(
                Task.status.in_([TaskStatus.ACTIVE, TaskStatus.INBOX]),
                Task.reminder_at.is_not(None),
                Task.reminder_at <= now,
                or_(Task.snoozed_until.is_(None), Task.snoozed_until <= now),
                Task.metadata_["reminder_sent_at"].astext.is_(None),
            )
        )
        return list(result.scalars())

    async def mark_reminder_sent(self, task: Task) -> None:
        task.metadata_ = {**task.metadata_, "reminder_sent_at": utc_now().isoformat()}

    # ------------------------------------------------------------------

    async def _record_event(
        self,
        task: Task,
        event_type: str,
        *,
        actor: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> None:
        self.session.add(
            TaskEvent(
                task_id=task.id,
                user_id=task.user_id,
                event_type=event_type,
                before_json=before,
                after_json=after,
                actor=actor,
                agent_run_id=agent_run_id,
            )
        )
