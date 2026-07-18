"""CalendarService: internal events, free slots, proposed blocks, external writes."""

from __future__ import annotations

import re
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
from lumi.services.assistant_suggestions import AssistantSuggestionService
from lumi.services.audit import AuditService
from lumi.services.planning_settings import planning_work_window
from lumi.services.realtime import RealtimeEventService
from lumi.utils.links import extract_links
from lumi.utils.time import local_day_bounds, utc_now

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


class ExternalCalendarMutationError(ValueError):
    """Raised when a write tries to mutate a synced external calendar event."""


class CalendarConflictError(ValueError):
    """Raised when a proposed calendar update overlaps another busy event."""

    def __init__(self, conflict: CalendarEvent) -> None:
        super().__init__("calendar_conflict")
        self.conflict = conflict


def _same_url(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.rstrip("/").lower() == b.rstrip("/").lower())


def _planning_proposal_expired(
    event: CalendarEvent,
    *,
    now: datetime | None = None,
) -> bool:
    if event.status != CalendarEventStatus.PROPOSED:
        return False
    raw_expiry = (event.metadata_ or {}).get("proposal_expires_at")
    if not isinstance(raw_expiry, str):
        return False
    try:
        expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        expires_at.tzinfo is not None
        and expires_at.utcoffset() is not None
        and expires_at <= (now or utc_now())
    )


def _is_replaceable_planning_proposal(event: CalendarEvent) -> bool:
    metadata = event.metadata_ or {}
    return bool(metadata.get("plan_batch_id")) and not metadata.get(
        "alternative_for_event_id"
    )


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


def truncate_private_note_summary(summary: str, limit: int = PRIVATE_NOTE_SUMMARY_MAX_CHARS) -> str:
    normalized = normalize_private_note_for_threshold(summary)
    if len(normalized) <= limit:
        return normalized
    head = normalized[: limit - 1].rstrip()
    boundary = head.rfind(" ")
    if boundary >= limit // 2:
        head = head[:boundary].rstrip()
    return f"{head}…" if head else normalized[:limit]


_SUMMARY_PREFIX_RE = re.compile(r"^(?:ai\s+summary|summary|резюме|саммари)\s*[:—-]\s*", re.I)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:first|second|third|fourth|первое|второе|третье|четвертое)\s*[:—-]\s*",
    re.I,
)


def fallback_private_note_summary(note: str) -> str:
    normalized = normalize_private_note_for_threshold(note)
    if not normalized:
        return ""
    parts = [part.strip(" -•\t") for part in _SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    candidates: list[str] = []
    for part in parts:
        cleaned = _ORDINAL_PREFIX_RE.sub("", part).strip()
        if ":" in cleaned and len(cleaned.split(":", 1)[0]) <= 32:
            cleaned = cleaned.split(":", 1)[1].strip()
        if cleaned:
            candidates.append(cleaned)
        if len(candidates) >= 3:
            break
    return truncate_private_note_summary("; ".join(candidates or [normalized]))


def clean_private_note_summary(note: str, summary: str) -> str:
    candidate = normalize_private_note_for_threshold(summary).strip("\"'“”«»")
    while True:
        cleaned = _SUMMARY_PREFIX_RE.sub("", candidate).strip()
        if cleaned == candidate:
            break
        candidate = cleaned

    note_normalized = normalize_private_note_for_threshold(note)
    candidate_prefix = candidate.rstrip("…").strip()
    repeats_note_start = (
        len(candidate_prefix) >= 80
        and note_normalized[: len(candidate_prefix)].casefold() == candidate_prefix.casefold()
    )
    too_long = len(candidate) > 2000
    contains_prompt = "personal note:" in candidate.casefold()
    if not candidate or repeats_note_start or too_long or contains_prompt:
        return fallback_private_note_summary(note)
    return truncate_private_note_summary(candidate)


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
    return truncate_private_note_summary(note)


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

    async def _lock_user(self, user: User) -> None:
        await self.session.execute(
            select(User.id).where(User.id == user.id).with_for_update()
        )

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
        now = utc_now()
        return [
            event
            for event in result.scalars()
            if not _planning_proposal_expired(event, now=now)
        ]

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
        await self.session.refresh(event, attribute_names=["updated_at"])
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
        await self.session.refresh(event, attribute_names=["updated_at"])
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
        existing_summary = metadata.get("private_note_summary")
        if (
            metadata.get("private_note_summary_status") == "ready"
            and isinstance(existing_summary, str)
            and existing_summary.strip()
        ):
            return event
        if not private_note_needs_summary(note):
            metadata["private_note_summary_status"] = "not_needed"
            metadata.pop("private_note_summary", None)
            metadata.pop("private_note_summary_updated_at", None)
        else:
            clean_summary = clean_private_note_summary(note, summary)
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
            if metadata.get("private_note_summary_status") == "ready" and metadata.get("private_note_summary"):
                return event
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
        await self._lock_user(user)
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

    async def cancel_proposed_blocks(
        self,
        user: User,
        *,
        day: datetime,
        future_only: bool = False,
        planning_only: bool = False,
        now: datetime | None = None,
    ) -> int:
        """Cancel all agent-proposed (still unaccepted) blocks for the given day."""
        await self._lock_user(user)
        day_start, day_end = local_day_bounds(day, user.timezone)
        stmt = select(CalendarEvent).where(
            CalendarEvent.user_id == user.id,
            CalendarEvent.source == CalendarSource.INTERNAL,
            CalendarEvent.status == CalendarEventStatus.PROPOSED,
            CalendarEvent.source_task_id.is_not(None),
            CalendarEvent.start_at < day_end,
            CalendarEvent.end_at > day_start,
        )
        if future_only:
            stmt = stmt.where(CalendarEvent.start_at >= (now or utc_now()))
        result = await self.session.execute(stmt)
        cancelled = 0
        for event in result.scalars():
            if planning_only and not _is_replaceable_planning_proposal(event):
                continue
            event.status = CalendarEventStatus.CANCELLED
            cancelled += 1
        if cancelled:
            await RealtimeEventService(self.session).emit(
                user_id=user.id,
                topics=["calendar"],
                event_type="calendar_events.cancelled",
                payload={"count": cancelled},
            )
            await self._queue_opportunity_refresh(
                user,
                reason="calendar_events.cancelled",
                payload={"count": cancelled},
            )
        return cancelled

    async def confirm_proposed_block(self, user: User, event: CalendarEvent) -> CalendarEvent:
        await self._lock_user(user)
        event.status = CalendarEventStatus.CONFIRMED
        await self.audit.log(user_id=user.id, actor="user", entity_type="calendar_event",
                             entity_id=event.id, action="confirmed", details={})
        await self._emit_calendar_changed(event, "calendar_event.confirmed")
        await self.session.flush()
        await self.session.refresh(event, attribute_names=["updated_at"])
        return event

    async def update_internal_event(
        self,
        user: User,
        event: CalendarEvent,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        title: str | None = None,
        description: str | None = None,
        actor: str = "agent",
    ) -> CalendarEvent:
        """Update a Lumi-owned block. Synced external events are read-only in v1."""
        if event.user_id != user.id:
            raise ValueError("event_not_found")
        if event.source != CalendarSource.INTERNAL:
            raise ExternalCalendarMutationError("external_calendar_update_unsupported")
        await self._lock_user(user)
        new_start_at = start_at or event.start_at
        new_end_at = end_at or event.end_at
        if new_end_at <= new_start_at:
            raise ValueError("end_at_must_be_after_start_at")
        conflicts = await self.list_events(user, new_start_at, new_end_at)
        busy_conflicts = [
            candidate for candidate in conflicts
            if (
                candidate.id != event.id
                and candidate.busy
                and candidate.status in (
                    CalendarEventStatus.CONFIRMED,
                    CalendarEventStatus.TENTATIVE,
                    CalendarEventStatus.PROPOSED,
                )
            )
        ]
        if busy_conflicts:
            raise CalendarConflictError(busy_conflicts[0])

        before = {
            "title": event.title,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
        }
        event.start_at = new_start_at
        event.end_at = new_end_at
        if title is not None:
            event.title = title.strip()[:300] or event.title
        if description is not None:
            event.description = description
            event.metadata_ = {
                **(event.metadata_ or {}),
                "links": _clean_links(extract_links(description)),
            }
        await self.audit.log(
            user_id=user.id,
            actor=actor,
            entity_type="calendar_event",
            entity_id=event.id,
            action="updated",
            details={
                "before": before,
                "after": {
                    "title": event.title,
                    "start_at": event.start_at.isoformat(),
                    "end_at": event.end_at.isoformat(),
                },
            },
        )
        await self._emit_calendar_changed(event, "calendar_event.updated")
        return event

    async def cancel_internal_event(
        self,
        user: User,
        event: CalendarEvent,
        *,
        actor: str = "agent",
    ) -> CalendarEvent:
        if event.user_id != user.id:
            raise ValueError("event_not_found")
        if event.source != CalendarSource.INTERNAL:
            raise ExternalCalendarMutationError("external_calendar_cancel_unsupported")
        await self._lock_user(user)
        event.status = CalendarEventStatus.CANCELLED
        await self.audit.log(
            user_id=user.id,
            actor=actor,
            entity_type="calendar_event",
            entity_id=event.id,
            action="cancelled",
            details={"title": event.title},
        )
        await self._emit_calendar_changed(event, "calendar_event.cancelled")
        return event

    # ------------------------------------------------------------------

    async def find_free_slots(
        self,
        user: User,
        *,
        day: datetime,
        duration_minutes: int = 60,
        ignore_future_planning_proposals: bool = False,
    ) -> list[tuple[datetime, datetime]]:
        """Free windows in the user's working day, UTC tuples."""
        work_window = planning_work_window(user.settings, day, user.timezone)
        if work_window is None:
            return []
        window_start, window_end = work_window
        day_utc_start, day_utc_end = local_day_bounds(day, user.timezone)

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
            and not (
                ignore_future_planning_proposals
                and e.status == CalendarEventStatus.PROPOSED
                and e.source == CalendarSource.INTERNAL
                and e.source_task_id is not None
                and _is_replaceable_planning_proposal(e)
                and e.start_at >= now
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
        await self._lock_user(user)
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
        await self._reconcile_work_block_conflicts(user, event)
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
        await self._lock_user(user)
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
            await self._reconcile_work_block_conflicts(user, event)
            cancelled += 1
        if cancelled:
            await self.session.flush()
            await RealtimeEventService(self.session).emit(
                user_id=user.id,
                topics=["calendar"],
                event_type="calendar_events.reconciled",
                payload={"count": cancelled, "source": source.value},
            )
            await self._queue_opportunity_refresh(
                user,
                reason="calendar_events.reconciled",
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

    async def _reconcile_work_block_conflicts(
        self,
        user: User,
        external_event: CalendarEvent,
    ) -> None:
        """Keep external events fixed and represent recovery as an explicit proposal."""
        from lumi.services.work_blocks import (  # local import avoids a service cycle
            WorkBlockResultStatus,
            WorkBlockService,
        )

        result = await self.session.execute(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.source == CalendarSource.INTERNAL,
                CalendarEvent.source_task_id.is_not(None),
                CalendarEvent.status.in_(
                    (CalendarEventStatus.CONFIRMED, CalendarEventStatus.PROPOSED)
                ),
            )
            .with_for_update()
        )
        work_blocks = [
            event
            for event in result.scalars()
            if not (
                event.status == CalendarEventStatus.PROPOSED
                and (
                    (event.metadata_ or {}).get("alternative_for_event_id")
                    or _planning_proposal_expired(event)
                )
            )
        ]
        external_id = str(external_event.id)
        external_is_busy = (
            external_event.busy
            and external_event.status
            in (CalendarEventStatus.CONFIRMED, CalendarEventStatus.TENTATIVE)
        )
        work_blocks_service = WorkBlockService(self.session)

        for block in work_blocks:
            metadata = dict(block.metadata_ or {})
            raw_conflict = metadata.get("work_block_conflict")
            conflict = dict(raw_conflict) if isinstance(raw_conflict, dict) else {}
            raw_ids = conflict.get("external_event_ids")
            external_ids = [
                value for value in raw_ids if isinstance(value, str)
            ] if isinstance(raw_ids, list) else []
            legacy_external_id = conflict.get("external_event_id")
            if isinstance(legacy_external_id, str) and legacy_external_id not in external_ids:
                external_ids.append(legacy_external_id)

            overlaps = (
                external_is_busy
                and block.start_at < external_event.end_at + MEETING_BUFFER
                and block.end_at > external_event.start_at - MEETING_BUFFER
            )
            changed = False
            if overlaps:
                was_impacted = (
                    conflict.get("status") == "impacted"
                    and external_id in external_ids
                )
                if external_id not in external_ids:
                    external_ids.append(external_id)
                conflict.update(
                    {
                        "status": "impacted",
                        "external_event_id": external_ids[0],
                        "external_event_ids": external_ids,
                    }
                )
                conflict.setdefault("detected_at", utc_now().isoformat())
                metadata["work_block_conflict"] = conflict
                block.metadata_ = metadata
                changed = not was_impacted
            elif external_id in external_ids:
                external_ids.remove(external_id)
                if external_ids:
                    conflict.update(
                        {
                            "status": "impacted",
                            "external_event_id": external_ids[0],
                            "external_event_ids": external_ids,
                        }
                    )
                else:
                    conflict.update(
                        {
                            "status": "resolved",
                            "external_event_id": external_id,
                            "external_event_ids": [],
                            "resolved_at": utc_now().isoformat(),
                        }
                    )
                    alternative = await self._conflict_alternative(user, block, conflict)
                    if (
                        alternative is not None
                        and alternative.status == CalendarEventStatus.PROPOSED
                    ):
                        await self.cancel_internal_event(
                            user,
                            alternative,
                            actor="external_sync",
                        )
                metadata["work_block_conflict"] = conflict
                block.metadata_ = metadata
                changed = True

            if conflict.get("status") == "impacted":
                alternative = await self._conflict_alternative(user, block, conflict)
                if alternative is None:
                    duration = block.end_at - block.start_at
                    duration_minutes = max(
                        1,
                        int((duration.total_seconds() + 59) // 60),
                    )
                    slots = await self.find_free_slots(
                        user,
                        day=block.start_at,
                        duration_minutes=duration_minutes,
                    )
                    for slot_start, slot_end in slots:
                        alternative_end = slot_start + duration
                        if alternative_end > slot_end:
                            continue
                        assert block.source_task_id is not None
                        proposed = await work_blocks_service.create(
                            user,
                            task_id=block.source_task_id,
                            title=block.title,
                            description=block.description,
                            start_at=slot_start,
                            end_at=alternative_end,
                            status=CalendarEventStatus.PROPOSED,
                            created_by="external_sync",
                            metadata={
                                **{
                                    key: value
                                    for key in (
                                        "plan_batch_id",
                                        "planning_request_id",
                                        "planning_mode",
                                        "planning_context_hash",
                                        "proposal_expires_at",
                                    )
                                    if (value := metadata.get(key)) is not None
                                },
                                "alternative_for_event_id": str(block.id),
                                "conflict_external_event_id": conflict.get(
                                    "external_event_id"
                                ),
                            },
                        )
                        if (
                            proposed.status == WorkBlockResultStatus.PROPOSED
                            and proposed.event is not None
                        ):
                            conflict["alternative_event_id"] = str(proposed.event.id)
                            metadata["work_block_conflict"] = conflict
                            block.metadata_ = metadata
                            changed = True
                            break
                    if not conflict.get("alternative_event_id"):
                        conflict["alternative_event_id"] = None
                        metadata["work_block_conflict"] = conflict
                        block.metadata_ = metadata

                if (
                    block.status == CalendarEventStatus.PROPOSED
                    and metadata.get("plan_batch_id")
                ):
                    await self.cancel_internal_event(
                        user,
                        block,
                        actor="external_sync",
                    )
                    changed = True

            if changed:
                await self.session.flush()
                await self._emit_calendar_changed(
                    block,
                    "calendar_event.work_block_impacted",
                )

    async def _conflict_alternative(
        self,
        user: User,
        block: CalendarEvent,
        conflict: dict[str, Any],
    ) -> CalendarEvent | None:
        alternative_id = conflict.get("alternative_event_id")
        if not isinstance(alternative_id, str):
            return None
        try:
            parsed_id = uuid.UUID(alternative_id)
        except ValueError:
            return None
        alternative = await self.get_event(user, parsed_id)
        if (
            alternative is None
            or alternative.source != CalendarSource.INTERNAL
            or alternative.source_task_id != block.source_task_id
            or (alternative.metadata_ or {}).get("alternative_for_event_id")
            != str(block.id)
            or alternative.status
            not in (CalendarEventStatus.PROPOSED, CalendarEventStatus.CONFIRMED)
        ):
            return None
        work_window = planning_work_window(
            user.settings,
            alternative.start_at,
            user.timezone,
        )
        conflict_event = await self.session.scalar(
            select(CalendarEvent.id)
            .where(
                CalendarEvent.user_id == user.id,
                CalendarEvent.id != alternative.id,
                CalendarEvent.busy.is_(True),
                CalendarEvent.status.in_(
                    (
                        CalendarEventStatus.CONFIRMED,
                        CalendarEventStatus.TENTATIVE,
                        CalendarEventStatus.PROPOSED,
                    )
                ),
                CalendarEvent.start_at < alternative.end_at + MEETING_BUFFER,
                CalendarEvent.end_at > alternative.start_at - MEETING_BUFFER,
            )
            .limit(1)
        )
        valid = (
            alternative.start_at >= utc_now()
            and work_window is not None
            and alternative.start_at >= work_window[0]
            and alternative.end_at <= work_window[1]
            and conflict_event is None
        )
        if not valid:
            if alternative.status == CalendarEventStatus.PROPOSED:
                await self.cancel_internal_event(
                    user,
                    alternative,
                    actor="external_sync",
                )
            return None
        return alternative

    async def _emit_calendar_changed(self, event: CalendarEvent, event_type: str) -> None:
        await RealtimeEventService(self.session).emit(
            user_id=event.user_id,
            topics=["calendar"],
            event_type=event_type,
            payload={"event_id": str(event.id), "source": event.source.value},
        )
        user = await self.session.get(User, event.user_id)
        if user is not None:
            await self._queue_opportunity_refresh(
                user,
                reason=event_type,
                payload={"event_id": str(event.id), "source": event.source.value},
            )

    async def _queue_opportunity_refresh(
        self,
        user: User,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await AssistantSuggestionService(self.session).enqueue_opportunity(
            user,
            kind="slot_suggestions",
            scope_key="today",
            reason=reason,
            payload=payload,
            delay_seconds=20,
        )
