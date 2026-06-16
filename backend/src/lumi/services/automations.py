"""AutomationService: DB-backed scheduled tasks with croniter scheduling."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import ScheduledTask, ScheduledTaskType, User
from lumi.services.audit import AuditService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import get_zone, utc_now


def compute_next_run(cron_expression: str, tz_name: str, *, after: datetime | None = None) -> datetime:
    """Next run time in UTC for a cron expression interpreted in the user's timezone."""
    zone = get_zone(tz_name)
    base = (after or utc_now()).astimezone(zone)
    cron = croniter(cron_expression, base)
    next_local: datetime = cron.get_next(datetime)
    return next_local.astimezone(after.tzinfo if after and after.tzinfo else get_zone("UTC"))


class AutomationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def list_for_user(self, user: User, *, include_system: bool = False) -> list[ScheduledTask]:
        result = await self.session.execute(
            select(ScheduledTask)
            .where(ScheduledTask.user_id == user.id)
            .order_by(ScheduledTask.created_at)
        )
        tasks = list(result.scalars())
        if include_system:
            return tasks
        return [task for task in tasks if not (task.config or {}).get("system")]

    async def get(self, user: User, automation_id: uuid.UUID) -> ScheduledTask | None:
        result = await self.session.execute(
            select(ScheduledTask).where(
                ScheduledTask.id == automation_id, ScheduledTask.user_id == user.id
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user: User,
        *,
        type_: str,
        title: str,
        cron_expression: str,
        timezone: str | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
        run_at: datetime | None = None,
        actor: str = "user",
    ) -> ScheduledTask:
        tz_name = timezone or user.timezone
        config = dict(config or {})
        if run_at is not None:
            # One-shot: fire once at run_at, scheduler disables it afterwards.
            config["one_time"] = True
            cron_expression = cron_expression or "0 0 1 1 *"
        elif not croniter.is_valid(cron_expression):
            raise ValueError(f"invalid cron expression: {cron_expression}")
        task = ScheduledTask(
            user_id=user.id,
            type=ScheduledTaskType(type_),
            title=title.strip()[:200],
            cron_expression=cron_expression or "0 0 1 1 *",
            timezone=tz_name,
            config=config,
            enabled=enabled,
            next_run_at=(
                run_at if run_at is not None
                else compute_next_run(cron_expression, tz_name) if enabled else None
            ),
        )
        self.session.add(task)
        await self.session.flush()
        await self.audit.log(user_id=user.id, actor=actor, entity_type="automation",
                             entity_id=task.id, action="created",
                             details={"type": type_, "cron": cron_expression})
        await self._emit_automation_changed(task, "automation.created")
        return task

    async def ensure_system_calendar_sync(self, user: User) -> ScheduledTask:
        """Ensure calendar sync runs for connected-calendar users without user setup."""
        result = await self.session.execute(
            select(ScheduledTask).where(
                ScheduledTask.user_id == user.id,
                ScheduledTask.type == ScheduledTaskType.CALENDAR_SYNC,
            )
        )
        for task in result.scalars():
            if (task.config or {}).get("system"):
                task.title = "Синхронизация календаря"
                task.cron_expression = "*/5 * * * *"
                task.timezone = user.timezone
                task.config = {**(task.config or {}), "system": True, "hidden": True}
                task.enabled = True
                task.next_run_at = compute_next_run(task.cron_expression, task.timezone)
                task.last_error = None
                await self._emit_automation_changed(task, "automation.updated")
                return task
        return await self.create(
            user,
            type_=ScheduledTaskType.CALENDAR_SYNC.value,
            title="Синхронизация календаря",
            cron_expression="*/5 * * * *",
            config={"system": True, "hidden": True},
            enabled=True,
            actor="system",
        )

    async def update(
        self, user: User, task: ScheduledTask, updates: dict[str, Any], *, actor: str = "user"
    ) -> ScheduledTask:
        if "cron_expression" in updates and updates["cron_expression"]:
            if not croniter.is_valid(updates["cron_expression"]):
                raise ValueError(f"invalid cron expression: {updates['cron_expression']}")
            task.cron_expression = updates["cron_expression"]
        for key in ("title", "timezone", "config"):
            if key in updates and updates[key] is not None:
                setattr(task, key, updates[key])
        if "enabled" in updates and updates["enabled"] is not None:
            task.enabled = bool(updates["enabled"])
        # Recompute schedule after any change.
        task.next_run_at = (
            compute_next_run(task.cron_expression, task.timezone) if task.enabled else None
        )
        if task.enabled:
            task.failure_count = 0
            task.last_error = None
        await self.audit.log(user_id=user.id, actor=actor, entity_type="automation",
                             entity_id=task.id, action="updated", details=dict(updates))
        await self._emit_automation_changed(task, "automation.updated")
        return task

    # --- scheduler side -------------------------------------------------

    async def find_due_tasks(self, now: datetime | None = None, limit: int = 20) -> list[ScheduledTask]:
        now = now or utc_now()
        result = await self.session.execute(
            select(ScheduledTask)
            .where(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run_at.is_not(None),
                ScheduledTask.next_run_at <= now,
            )
            .order_by(ScheduledTask.next_run_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars())

    def try_lock(self, task: ScheduledTask, lock_seconds: int, now: datetime | None = None) -> bool:
        """In-row lock to prevent double enqueue. Call within the same transaction."""
        now = now or utc_now()
        if task.locked_until and task.locked_until > now:
            return False
        task.locked_until = now + timedelta(seconds=lock_seconds)
        return True

    def advance_schedule(self, task: ScheduledTask, now: datetime | None = None) -> None:
        now = now or utc_now()
        task.last_run_at = now
        task.next_run_at = compute_next_run(task.cron_expression, task.timezone, after=now)

    async def mark_succeeded(self, task: ScheduledTask) -> None:
        task.failure_count = 0
        task.last_error = None
        task.locked_until = None
        await self._emit_automation_changed(task, "automation.succeeded")

    async def mark_failed(self, task: ScheduledTask, error: str) -> None:
        task.failure_count += 1
        task.last_error = error[:1000]
        task.locked_until = None
        await self._emit_automation_changed(task, "automation.failed")

    async def _emit_automation_changed(self, task: ScheduledTask, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=task.user_id,
            topics=["automations"],
            event_type=event_type,
            payload={"automation_id": str(task.id), "type": task.type.value},
        )
