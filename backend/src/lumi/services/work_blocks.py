"""Safe Task -> CalendarEvent (WorkBlock) lifecycle."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    Task,
    TaskStatus,
    User,
)
from lumi.services.calendar import MEETING_BUFFER, CalendarService
from lumi.services.planning_settings import planning_work_window
from lumi.utils.time import get_zone, utc_now


class WorkBlockResultStatus(enum.StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    CONFLICT = "conflict"
    STALE = "stale"
    INVALID = "invalid"
    NOT_FOUND = "not_found"


class WorkBlockReason(enum.StrEnum):
    TASK_NOT_FOUND = "task_not_found"
    TASK_CLOSED = "task_closed"
    NOT_WORK_BLOCK = "not_work_block"
    INVALID_INTERVAL = "invalid_interval"
    INTERVAL_IN_PAST = "interval_in_past"
    NON_WORK_DAY = "non_work_day"
    OUTSIDE_WORK_HOURS = "outside_work_hours"
    CALENDAR_CONFLICT = "calendar_conflict"
    PROPOSAL_CHANGED = "proposal_changed"
    PROPOSAL_CANCELLED = "proposal_cancelled"


@dataclass(slots=True)
class WorkBlockResult:
    status: WorkBlockResultStatus
    reason: WorkBlockReason | None = None
    event: CalendarEvent | None = None
    conflict: CalendarEvent | None = None


def is_work_block(event: CalendarEvent) -> bool:
    return event.source == CalendarSource.INTERNAL and event.source_task_id is not None


class WorkBlockService:
    """Owns all writes that turn an open Task into reserved calendar time."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calendar = CalendarService(session)

    async def _lock_user(self, user: User) -> None:
        await self.session.execute(
            select(User.id).where(User.id == user.id).with_for_update()
        )

    async def _owned_open_task(self, user: User, task_id: uuid.UUID) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .where(Task.id == task_id, Task.user_id == user.id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _validate_interval(
        self,
        user: User,
        *,
        start_at: datetime,
        end_at: datetime,
        exclude_event_id: uuid.UUID | None = None,
    ) -> tuple[WorkBlockReason | None, CalendarEvent | None]:
        if (
            start_at.tzinfo is None
            or start_at.utcoffset() is None
            or end_at.tzinfo is None
            or end_at.utcoffset() is None
            or end_at <= start_at
            or end_at - start_at < timedelta(minutes=1)
            or end_at - start_at > timedelta(minutes=240)
        ):
            return WorkBlockReason.INVALID_INTERVAL, None
        if start_at < utc_now():
            return WorkBlockReason.INTERVAL_IN_PAST, None

        zone = get_zone(user.timezone)
        local_start = start_at.astimezone(zone)
        local_end = end_at.astimezone(zone)
        roundtrip_start = start_at.astimezone(UTC).astimezone(zone)
        roundtrip_end = end_at.astimezone(UTC).astimezone(zone)
        if (
            (local_start.replace(tzinfo=None), local_start.utcoffset())
            != (roundtrip_start.replace(tzinfo=None), roundtrip_start.utcoffset())
            or (local_end.replace(tzinfo=None), local_end.utcoffset())
            != (roundtrip_end.replace(tzinfo=None), roundtrip_end.utcoffset())
        ):
            return WorkBlockReason.INVALID_INTERVAL, None
        if local_start.date() != local_end.date():
            return WorkBlockReason.INVALID_INTERVAL, None

        work_window = planning_work_window(user.settings, start_at, user.timezone)
        if work_window is None:
            return WorkBlockReason.NON_WORK_DAY, None
        window_start, window_end = work_window
        if start_at < window_start or end_at > window_end:
            return WorkBlockReason.OUTSIDE_WORK_HOURS, None

        stmt = (
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.busy.is_(True),
                CalendarEvent.status.in_(
                    (
                        CalendarEventStatus.CONFIRMED,
                        CalendarEventStatus.TENTATIVE,
                        CalendarEventStatus.PROPOSED,
                    )
                ),
                CalendarEvent.start_at < end_at + MEETING_BUFFER,
                CalendarEvent.end_at > start_at - MEETING_BUFFER,
            )
            .order_by(CalendarEvent.start_at, CalendarEvent.id)
            .limit(1)
        )
        if exclude_event_id is not None:
            stmt = stmt.where(CalendarEvent.id != exclude_event_id)
        conflict = (await self.session.execute(stmt)).scalar_one_or_none()
        if conflict is not None:
            return WorkBlockReason.CALENDAR_CONFLICT, conflict
        return None, None

    async def create(
        self,
        user: User,
        *,
        task_id: uuid.UUID,
        title: str | None,
        start_at: datetime,
        end_at: datetime,
        status: CalendarEventStatus = CalendarEventStatus.PROPOSED,
        description: str | None = None,
        created_by: str = "user",
        agent_run_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkBlockResult:
        await self._lock_user(user)
        task = await self._owned_open_task(user, task_id)
        if task is None:
            return WorkBlockResult(
                WorkBlockResultStatus.NOT_FOUND,
                WorkBlockReason.TASK_NOT_FOUND,
            )
        if task.status not in {TaskStatus.INBOX, TaskStatus.ACTIVE}:
            return WorkBlockResult(
                WorkBlockResultStatus.INVALID,
                WorkBlockReason.TASK_CLOSED,
            )
        clean_title = " ".join((title or task.title).split()).strip()
        if not clean_title or status not in {
            CalendarEventStatus.PROPOSED,
            CalendarEventStatus.CONFIRMED,
        }:
            return WorkBlockResult(
                WorkBlockResultStatus.INVALID,
                WorkBlockReason.INVALID_INTERVAL,
            )

        reason, conflict = await self._validate_interval(
            user,
            start_at=start_at,
            end_at=end_at,
        )
        if conflict is not None:
            return WorkBlockResult(
                WorkBlockResultStatus.CONFLICT,
                reason,
                conflict=conflict,
            )
        if reason is not None:
            return WorkBlockResult(WorkBlockResultStatus.INVALID, reason)

        event = await self.calendar.create_internal_block(
            user,
            title=clean_title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            status=status,
            created_by=created_by,
            source_task_id=task.id,
            agent_run_id=agent_run_id,
            metadata=metadata,
        )
        await self.session.flush()
        result_status = (
            WorkBlockResultStatus.PROPOSED
            if status == CalendarEventStatus.PROPOSED
            else WorkBlockResultStatus.CONFIRMED
        )
        return WorkBlockResult(result_status, event=event)

    async def confirm(
        self,
        user: User,
        *,
        event_id: uuid.UUID,
        expected_updated_at: datetime | None = None,
    ) -> WorkBlockResult:
        await self._lock_user(user)
        result = await self.session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.id == event_id, CalendarEvent.user_id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        event = result.scalar_one_or_none()
        if event is None:
            return WorkBlockResult(WorkBlockResultStatus.NOT_FOUND)
        if not is_work_block(event):
            return WorkBlockResult(
                WorkBlockResultStatus.INVALID,
                WorkBlockReason.NOT_WORK_BLOCK,
            )
        assert event.source_task_id is not None
        if event.status == CalendarEventStatus.CONFIRMED:
            return WorkBlockResult(WorkBlockResultStatus.ALREADY_CONFIRMED, event=event)
        if event.status != CalendarEventStatus.PROPOSED:
            return WorkBlockResult(
                WorkBlockResultStatus.STALE,
                WorkBlockReason.PROPOSAL_CANCELLED,
                event=event,
            )
        if expected_updated_at is not None and event.updated_at != expected_updated_at:
            return WorkBlockResult(
                WorkBlockResultStatus.STALE,
                WorkBlockReason.PROPOSAL_CHANGED,
                event=event,
            )

        task = await self._owned_open_task(user, event.source_task_id)
        if task is None:
            return WorkBlockResult(
                WorkBlockResultStatus.STALE,
                WorkBlockReason.TASK_NOT_FOUND,
                event=event,
            )
        if task.status not in {TaskStatus.INBOX, TaskStatus.ACTIVE}:
            return WorkBlockResult(
                WorkBlockResultStatus.STALE,
                WorkBlockReason.TASK_CLOSED,
                event=event,
            )

        reason, conflict = await self._validate_interval(
            user,
            start_at=event.start_at,
            end_at=event.end_at,
            exclude_event_id=event.id,
        )
        if conflict is not None:
            return WorkBlockResult(
                WorkBlockResultStatus.CONFLICT,
                reason,
                event=event,
                conflict=conflict,
            )
        if reason is not None:
            return WorkBlockResult(
                WorkBlockResultStatus.STALE,
                reason,
                event=event,
            )

        replaced_event: CalendarEvent | None = None
        replaced_event_id = (event.metadata_ or {}).get("alternative_for_event_id")
        if isinstance(replaced_event_id, str):
            try:
                parsed_replaced_event_id = uuid.UUID(replaced_event_id)
            except ValueError:
                parsed_replaced_event_id = None
            if parsed_replaced_event_id is not None:
                replaced_event = await self.session.scalar(
                    select(CalendarEvent)
                    .where(
                        CalendarEvent.id == parsed_replaced_event_id,
                        CalendarEvent.user_id == user.id,
                        CalendarEvent.source == CalendarSource.INTERNAL,
                        CalendarEvent.source_task_id == event.source_task_id,
                    )
                    .with_for_update()
                )

        await self.calendar.confirm_proposed_block(user, event)
        if (
            replaced_event is not None
            and replaced_event.status != CalendarEventStatus.CANCELLED
        ):
            replaced_metadata = dict(replaced_event.metadata_ or {})
            raw_conflict = replaced_metadata.get("work_block_conflict")
            conflict = dict(raw_conflict) if isinstance(raw_conflict, dict) else {}
            conflict.update(
                {
                    "status": "replaced",
                    "alternative_event_id": str(event.id),
                    "replaced_at": utc_now().isoformat(),
                }
            )
            replaced_metadata["work_block_conflict"] = conflict
            replaced_event.metadata_ = replaced_metadata
            await self.calendar.cancel_internal_event(
                user,
                replaced_event,
                actor="user",
            )
        await self.session.flush()
        await self.session.refresh(event, attribute_names=["updated_at"])
        return WorkBlockResult(WorkBlockResultStatus.CONFIRMED, event=event)
