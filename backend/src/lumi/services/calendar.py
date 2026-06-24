"""CalendarService: internal events, free slots, proposed blocks, external writes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import (
    CalendarEvent,
    CalendarEventStatus,
    CalendarSource,
    User,
)
from lumi.services.audit import AuditService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.links import extract_links
from lumi.utils.time import get_zone, local_day_bounds, utc_now

DEFAULT_DAY_START_HOUR = 9
DEFAULT_DAY_END_HOUR = 19
MEETING_BUFFER = timedelta(minutes=10)
PRIVATE_NOTE_MAX_CHARS = 4000
PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS = 600
PRIVATE_NOTE_SUMMARY_MAX_CHARS = 160

PRIVATE_NOTE_KEYS = {
    "private_note",
    "private_note_hash",
    "private_note_updated_at",
    "private_note_summary",
    "private_note_summary_status",
    "private_note_summary_updated_at",
    "private_note_summary_error",
}


def _same_url(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.rstrip("/").lower() == b.rstrip("/").lower())


def _clean_links(
    links: list[str] | None, *, meeting_url: str | None = None, external_url: str | None = None
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for link in links or []:
        if _same_url(link, meeting_url) or _same_url(link, external_url):
            continue
        normalized = link.rstrip("/").lower()
        if normalized in seen:
            continue
        out.append(link)
        seen.add(normalized)
    return out


def normalize_private_note_for_threshold(note: str) -> str:
    return " ".join(note.split()).strip()


def private_note_hash(note: str) -> str:
    return sha256(normalize_private_note_for_threshold(note).encode("utf-8")).hexdigest()


def private_note_needs_summary(note: str) -> bool:
    return len(normalize_private_note_for_threshold(note)) >= PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS


def clean_private_note(note: str | None) -> str | None:
    if note is None:
        return None
    cleaned = note.strip()
    if not cleaned:
        return None
    if len(cleaned) > PRIVATE_NOTE_MAX_CHARS:
        raise ValueError("private_note_too_long")
    return cleaned


def calendar_private_note_summary_text(event: CalendarEvent) -> str | None:
    metadata = event.metadata_ or {}
    note = metadata.get("private_note")
    if not isinstance(note, str) or not note.strip():
        return None
    if not private_note_needs_summary(note):
        return note
    summary = metadata.get("private_note_summary")
    if metadata.get("private_note_summary_status") == "ready" and isinstance(summary, str) and summary.strip():
        return summary.strip()
    return normalize_private_note_for_threshold(note)[:180].rstrip() + "…"


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

    async def set_private_note(
        self,
        user: User,
        event: CalendarEvent,
        note: str | None,
    ) -> CalendarEvent:
        cleaned = clean_private_note(note)
        if cleaned is None:
            return await self.delete_private_note(user, event)

        digest = private_note_hash(cleaned)
        now = utc_now().isoformat()
        metadata = dict(event.metadata_ or {})
        previous_hash = metadata.get("private_note_hash")
        previous_status = metadata.get("private_note_summary_status")
        previous_summary = metadata.get("private_note_summary")

        metadata["private_note"] = cleaned
        metadata["private_note_hash"] = digest
        metadata["private_note_updated_at"] = now
        metadata.pop("private_note_summary_error", None)

        if private_note_needs_summary(cleaned):
            if previous_hash == digest and previous_status == "ready" and previous_summary:
                metadata["private_note_summary_status"] = "ready"
            elif previous_hash == digest and previous_status in {"pending", "failed"}:
                metadata["private_note_summary_status"] = previous_status
            else:
                metadata["private_note_summary_status"] = "pending"
                metadata.pop("private_note_summary", None)
                metadata.pop("private_note_summary_updated_at", None)
        else:
            metadata["private_note_summary_status"] = "not_needed"
            metadata.pop("private_note_summary", None)
            metadata.pop("private_note_summary_updated_at", None)

        event.metadata_ = metadata
        await self.session.flush()
        await self.audit.log(
            user_id=user.id,
            actor="user",
            entity_type="calendar_event",
            entity_id=event.id,
            action="private_note.updated",
            details={"summary_status": metadata.get("private_note_summary_status")},
        )
        await self._emit_calendar_changed(event, "calendar_event.private_note.updated")
        return event

    async def delete_private_note(self, user: User, event: CalendarEvent) -> CalendarEvent:
        metadata = {
            key: value
            for key, value in dict(event.metadata_ or {}).items()
            if key not in PRIVATE_NOTE_KEYS
        }
        event.metadata_ = metadata
        await self.session.flush()
        await self.audit.log(
            user_id=user.id,
            actor="user",
            entity_type="calendar_event",
            entity_id=event.id,
            action="private_note.deleted",
            details={},
        )
        await self._emit_calendar_changed(event, "calendar_event.private_note.deleted")
        return event

    async def write_private_note_summary(
        self,
        user: User,
        event: CalendarEvent,
        *,
        note_hash: str,
        summary: str,
    ) -> CalendarEvent:
        metadata = dict(event.metadata_ or {})
        note = metadata.get("private_note")
        if (
            event.user_id != user.id
            or metadata.get("private_note_hash") != note_hash
            or not isinstance(note, str)
        ):
            return event
        if not private_note_needs_summary(note):
            metadata["private_note_summary_status"] = "not_needed"
            metadata.pop("private_note_summary", None)
            metadata.pop("private_note_summary_updated_at", None)
        else:
            clean_summary = normalize_private_note_for_threshold(summary)[:PRIVATE_NOTE_SUMMARY_MAX_CHARS]
            metadata["private_note_summary"] = clean_summary or calendar_private_note_summary_text(event)
            metadata["private_note_summary_status"] = "ready"
            metadata["private_note_summary_updated_at"] = utc_now().isoformat()
            metadata.pop("private_note_summary_error", None)
        event.metadata_ = metadata
        await self.session.flush()
        await self._emit_calendar_changed(event, "calendar_event.private_note.summary_ready")
        return event

    async def mark_private_note_summary_failed(
        self,
        user: User,
        event: CalendarEvent,
        *,
        note_hash: str,
        error: str,
    ) -> CalendarEvent:
        metadata = dict(event.metadata_ or {})
        if event.user_id == user.id and metadata.get("private_note_hash") == note_hash:
            metadata["private_note_summary_status"] = "failed"
            metadata["private_note_summary_error"] = error[:300]
            event.metadata_ = metadata
            await self.session.flush()
            await self._emit_calendar_changed(event, "calendar_event.private_note.summary_failed")
        return event

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
        location: str | None = None,
        meeting_url: str | None = None,
        external_url: str | None = None,
        links: list[str] | None = None,
        organizer: dict[str, Any] | None = None,
        attendees: list[dict[str, Any]] | None = None,
        user_response_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CalendarEvent:
        detail_links = _clean_links(
            links if links is not None else extract_links(description, meeting_url, external_url),
            meeting_url=meeting_url,
            external_url=external_url,
        )
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
            metadata_={
                key: value
                for key, value in {
                    **(metadata or {}),
                    "location": location,
                    "meeting_url": meeting_url,
                    "external_url": external_url,
                    "links": detail_links,
                    "organizer": organizer,
                    "attendees": attendees or [],
                    "attendee_count": len(attendees or []),
                    "user_response_status": user_response_status,
                }.items()
                if value not in (None, "", [])
            },
        )
        self.session.add(event)
        await self.session.flush()
        await self.audit.log(
            user_id=user.id, actor=created_by if created_by != "external_sync" else "system",
            entity_type="calendar_event", entity_id=event.id,
            action="created" if status != CalendarEventStatus.PROPOSED else "proposed",
            details={"title": event.title},
        )
        await self._emit_calendar_changed(event, "calendar_event.created")
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
        if cancelled:
            await RealtimeEventService(self.session).emit(
                user_id=user.id,
                topics=["calendar"],
                event_type="calendar_events.cancelled",
                payload={"count": cancelled},
            )
        return cancelled

    async def confirm_proposed_block(self, user: User, event: CalendarEvent) -> CalendarEvent:
        event.status = CalendarEventStatus.CONFIRMED
        await self.audit.log(user_id=user.id, actor="user", entity_type="calendar_event",
                             entity_id=event.id, action="confirmed", details={})
        await self._emit_calendar_changed(event, "calendar_event.confirmed")
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
        location: str | None = None,
        meeting_url: str | None = None,
        external_url: str | None = None,
        links: list[str] | None = None,
        external_updated_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        creator: dict[str, Any] | None = None,
        organizer: dict[str, Any] | None = None,
        attendees: list[dict[str, Any]] | None = None,
        user_response_status: str | None = None,
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
        detail_links = _clean_links(
            links if links is not None else extract_links(description, meeting_url, external_url),
            meeting_url=meeting_url,
            external_url=external_url,
        )
        detail_metadata: dict[str, Any] = {
            **(event.metadata_ or {}),
            **(metadata or {}),
            "location": location,
            "meeting_url": meeting_url,
            "external_url": external_url,
            "links": detail_links,
            "creator": creator,
            "organizer": organizer,
            "attendees": attendees or [],
            "attendee_count": len(attendees or []),
            "user_response_status": user_response_status,
        }
        if external_updated_at is not None:
            detail_metadata["external_updated_at"] = external_updated_at.isoformat()
        event.metadata_ = {
            key: value
            for key, value in detail_metadata.items()
            if value not in (None, "", [])
        }
        await self.session.flush()
        await self._emit_calendar_changed(event, "calendar_event.upserted")
        return event

    async def reconcile_external_events(
        self,
        user: User,
        *,
        source: CalendarSource,
        external_calendar_id: str,
        start_at: datetime,
        end_at: datetime,
        seen_event_ids: set[str],
    ) -> int:
        """Cancel external events in a sync window that the provider no longer returns."""
        result = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == source,
                CalendarEvent.external_calendar_id == external_calendar_id,
                CalendarEvent.external_event_id.is_not(None),
                CalendarEvent.start_at < end_at,
                CalendarEvent.end_at > start_at,
                CalendarEvent.status != CalendarEventStatus.CANCELLED,
            )
        )
        cancelled = 0
        for event in result.scalars():
            if event.external_event_id in seen_event_ids:
                continue
            event.status = CalendarEventStatus.CANCELLED
            event.last_synced_at = utc_now()
            event.metadata_ = {
                **(event.metadata_ or {}),
                "cancelled_by_sync": True,
                "cancelled_by_sync_at": event.last_synced_at.isoformat(),
            }
            cancelled += 1
        if cancelled:
            await self.session.flush()
            await RealtimeEventService(self.session).emit(
                user_id=user.id,
                topics=["calendar"],
                event_type="calendar_events.reconciled",
                payload={"count": cancelled, "source": source.value},
            )
        return cancelled

    async def external_calendar_ids_in_window(
        self,
        user: User,
        *,
        source: CalendarSource,
        start_at: datetime,
        end_at: datetime,
    ) -> set[str]:
        result = await self.session.execute(
            select(CalendarEvent.external_calendar_id).where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == source,
                CalendarEvent.external_calendar_id.is_not(None),
                CalendarEvent.start_at < end_at,
                CalendarEvent.end_at > start_at,
            )
        )
        return {calendar_id for calendar_id in result.scalars() if calendar_id}

    async def _emit_calendar_changed(self, event: CalendarEvent, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=event.user_id,
            topics=["calendar"],
            event_type=event_type,
            payload={"event_id": str(event.id), "source": event.source.value},
        )
