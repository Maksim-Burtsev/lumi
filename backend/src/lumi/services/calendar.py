"""CalendarService: internal events, free slots, proposed blocks, external writes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    User,
)
from lumi.services.audit import AuditService
from lumi.utils.time import get_zone, local_day_bounds, utc_now

DEFAULT_DAY_START_HOUR = 9
DEFAULT_DAY_END_HOUR = 19
MEETING_BUFFER = timedelta(minutes=10)


def merge_busy_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Merge overlapping/touching intervals into a sorted, disjoint list."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def subtract_intervals(
    window: tuple[datetime, datetime],
    busy: list[tuple[datetime, datetime]],
    *,
    min_duration: timedelta,
    buffer: timedelta = MEETING_BUFFER,
) -> list[tuple[datetime, datetime]]:
    """Free intervals = window minus busy (with a buffer around busy blocks)."""
    cursor, window_end = window
    free: list[tuple[datetime, datetime]] = []
    for start, end in merge_busy_intervals(busy):
        padded_start = start - buffer
        padded_end = end + buffer
        if padded_start > cursor:
            candidate_end = min(padded_start, window_end)
            if candidate_end - cursor >= min_duration:
                free.append((cursor, candidate_end))
        cursor = max(cursor, padded_end)
        if cursor >= window_end:
            break
    if window_end - cursor >= min_duration:
        free.append((cursor, window_end))
    return free


class CalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def list_events(self, user: User, start: datetime, end: datetime) -> list[CalendarEvent]:
        result = await self.session.execute(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.start_at < end,
                CalendarEvent.end_at > start,
                CalendarEvent.status != CalendarEventStatus.CANCELLED,
            )
            .order_by(CalendarEvent.start_at)
        )
        return list(result.scalars())

    async def get_event(self, user: User, event_id: uuid.UUID) -> CalendarEvent | None:
        result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id, CalendarEvent.user_id == user.id
            )
        )
        return result.scalar_one_or_none()

    async def create_internal_block(
        self,
        user: User,
        *,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        status: CalendarEventStatus = CalendarEventStatus.CONFIRMED,
        created_by: str = "user",
        source_task_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        busy: bool = True,
    ) -> CalendarEvent:
        event = CalendarEvent(
            user_id=user.id,
            source=CalendarSource.INTERNAL,
            title=title.strip()[:300],
            description=description,
            start_at=start_at,
            end_at=end_at,
            timezone=user.timezone,
            busy=busy,
            status=status,
            created_by=created_by,
            source_task_id=source_task_id,
            agent_run_id=agent_run_id,
        )
        self.session.add(event)
        await self.session.flush()
        await self.audit.log(
            user_id=user.id, actor=created_by if created_by != "external_sync" else "system",
            entity_type="calendar_event", entity_id=event.id,
            action="created" if status != CalendarEventStatus.PROPOSED else "proposed",
            details={"title": event.title},
        )
        return event

    async def cancel_proposed_blocks(self, user: User, *, day: datetime) -> int:
        """Cancel all agent-proposed (still unaccepted) blocks for the given day."""
        day_start, day_end = local_day_bounds(day, user.timezone)
        result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == CalendarSource.INTERNAL,
                CalendarEvent.status == CalendarEventStatus.PROPOSED,
                CalendarEvent.start_at < day_end,
                CalendarEvent.end_at > day_start,
            )
        )
        cancelled = 0
        for event in result.scalars():
            event.status = CalendarEventStatus.CANCELLED
            cancelled += 1
        return cancelled

    async def confirm_proposed_block(self, user: User, event: CalendarEvent) -> CalendarEvent:
        event.status = CalendarEventStatus.CONFIRMED
        await self.audit.log(user_id=user.id, actor="user", entity_type="calendar_event",
                             entity_id=event.id, action="confirmed", details={})
        return event

    # ------------------------------------------------------------------

    async def find_free_slots(
        self,
        user: User,
        *,
        day: datetime,
        duration_minutes: int = 60,
        day_start_hour: int | None = None,
        day_end_hour: int | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Free windows in the user's working day, UTC tuples."""
        zone = get_zone(user.timezone)
        day_utc_start, day_utc_end = local_day_bounds(day, user.timezone)
        local_date = day_utc_start.astimezone(zone).date()

        settings = user.settings or {}
        start_hour = day_start_hour or settings.get("day_start_hour", DEFAULT_DAY_START_HOUR)
        end_hour = day_end_hour or settings.get("day_end_hour", DEFAULT_DAY_END_HOUR)

        window_start = datetime(local_date.year, local_date.month, local_date.day,
                                start_hour, tzinfo=zone).astimezone(day_utc_start.tzinfo)
        window_end = datetime(local_date.year, local_date.month, local_date.day,
                              end_hour, tzinfo=zone).astimezone(day_utc_start.tzinfo)

        # Don't propose slots in the past.
        now = utc_now()
        if window_start < now < window_end:
            window_start = now + timedelta(minutes=5)
        if window_start >= window_end:
            return []

        events = await self.list_events(user, day_utc_start, day_utc_end)
        busy = [
            (e.start_at, e.end_at)
            for e in events
            # Pending proposals hold their slot too — otherwise a re-plan
            # double-books the same window.
            if e.busy and e.status in (
                CalendarEventStatus.CONFIRMED,
                CalendarEventStatus.TENTATIVE,
                CalendarEventStatus.PROPOSED,
            )
        ]
        return subtract_intervals(
            (window_start, window_end), busy, min_duration=timedelta(minutes=duration_minutes)
        )

    # ------------------------------------------------------------------

    async def upsert_external_event(
        self,
        user: User,
        *,
        source: CalendarSource = CalendarSource.GOOGLE,
        external_calendar_id: str,
        external_event_id: str,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        all_day: bool = False,
        busy: bool = True,
        status: CalendarEventStatus = CalendarEventStatus.CONFIRMED,
    ) -> CalendarEvent:
        result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == source,
                CalendarEvent.external_calendar_id == external_calendar_id,
                CalendarEvent.external_event_id == external_event_id,
            )
        )
        event = result.scalar_one_or_none()
        if event is None:
            event = CalendarEvent(
                user_id=user.id,
                source=source,
                external_calendar_id=external_calendar_id,
                external_event_id=external_event_id,
                timezone=user.timezone,
                created_by="external_sync",
                title=title, start_at=start_at, end_at=end_at,
            )
            self.session.add(event)
        event.title = title
        event.description = description
        event.start_at = start_at
        event.end_at = end_at
        event.all_day = all_day
        event.busy = busy
        event.status = status
        event.last_synced_at = utc_now()
        await self.session.flush()
        return event
