"""Calendar API: events, free slots, plan-day, sync, confirm blocks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.run_helper import start_background_run
from lumi.api.serializers import event_to_dict
from lumi.connectors.google.auth import token_file_exists
from lumi.db.models import AgentRun, AgentRunType, CalendarEventStatus, Connector, ConnectorType, User
from lumi.services.automations import AutomationService
from lumi.services.calendar import CalendarService
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import utc_now

router = APIRouter()


class EventCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    description: str | None = None
    location: str | None = None
    meeting_url: str | None = None
    external_url: str | None = None
    links: list[str] | None = None


class PlanDayBody(BaseModel):
    date: str | None = None


async def _external_calendar_sync_state(session: AsyncSession, user: User) -> dict:
    from lumi.connectors.yandex.caldav_client import get_yandex_connector_row

    rows = []
    if token_file_exists():
        google = (await session.execute(select(Connector).where(
            Connector.user_id == user.id, Connector.type == ConnectorType.GOOGLE
        ))).scalar_one_or_none()
        rows.append(google)
    yandex = await get_yandex_connector_row(session, user)
    if yandex is not None and yandex.credentials_encrypted:
        rows.append(yandex)

    connected = bool(rows)
    if connected:
        await AutomationService(session).ensure_system_calendar_sync(user)
    last_syncs = [row.last_sync_at for row in rows if row is not None and row.last_sync_at]
    last_sync_at = max(last_syncs) if last_syncs else None
    stale = connected and (
        last_sync_at is None or utc_now() - last_sync_at > timedelta(minutes=2)
    )
    return {
        "connected": connected,
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "stale": stale,
        "refresh_queued": False,
    }


async def _maybe_enqueue_stale_calendar_sync(
    session: AsyncSession, user: User, sync_state: dict
) -> None:
    if not sync_state["stale"]:
        return
    recent = await session.execute(
        select(AgentRun).where(
            AgentRun.user_id == user.id,
            AgentRun.type == AgentRunType.CALENDAR_SYNC,
            AgentRun.created_at > utc_now() - timedelta(minutes=2),
        ).limit(1)
    )
    if recent.scalar_one_or_none() is not None:
        return
    try:
        await start_background_run(
            session, user, "calendar_sync", trigger="calendar_open_stale", notify=False
        )
        sync_state["refresh_queued"] = True
    except HTTPException:
        sync_state["refresh_queued"] = False


@router.get("/calendar/events")
async def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    start = start or utc_now()
    end = end or (start + timedelta(days=1))
    events = await CalendarService(session).list_events(user, start, end)
    sync_state = await _external_calendar_sync_state(session, user)
    await _maybe_enqueue_stale_calendar_sync(session, user, sync_state)
    return {"items": [event_to_dict(e) for e in events], "sync": sync_state}


@router.post("/calendar/events", status_code=201)
async def create_event(
    payload: EventCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="end_before_start")
    event = await CalendarService(session).create_internal_block(
        user,
        title=payload.title,
        start_at=payload.start_at,
        end_at=payload.end_at,
        description=payload.description,
        location=payload.location,
        meeting_url=payload.meeting_url,
        external_url=payload.external_url,
        links=payload.links,
        created_by="user",
    )
    return {"event": event_to_dict(event)}


@router.get("/calendar/free-slots")
async def free_slots(
    date: str | None = None,
    duration: int = Query(default=60, ge=15, le=480),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    day = utc_now()
    if date:
        try:
            day = datetime.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="bad_date") from exc
        if day.tzinfo is None:
            from lumi.utils.time import get_zone

            day = day.replace(tzinfo=get_zone(user.timezone))
    slots = await CalendarService(session).find_free_slots(
        user, day=day, duration_minutes=duration
    )
    return {"items": [{"start_at": s.isoformat(), "end_at": e.isoformat()} for s, e in slots]}


@router.post("/calendar/plan-day")
async def plan_day(
    payload: PlanDayBody | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    kwargs = {}
    if payload and payload.date:
        kwargs["plan_date"] = payload.date  # YYYY-MM-DD, плановать можно любой день
    return await start_background_run(session, user, "daily_planning", **kwargs)


@router.post("/calendar/blocks/{block_id}/confirm")
async def confirm_block(
    block_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    calendar = CalendarService(session)
    try:
        event = await calendar.get_event(user, uuid.UUID(block_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    if event is None:
        raise HTTPException(status_code=404, detail="not_found")
    if event.status != CalendarEventStatus.PROPOSED:
        raise HTTPException(status_code=409, detail="not_proposed")
    event = await calendar.confirm_proposed_block(user, event)
    return {"event": event_to_dict(event)}


@router.delete("/calendar/events/{event_id}")
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    calendar = CalendarService(session)
    try:
        event = await calendar.get_event(user, uuid.UUID(event_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    if event is None:
        raise HTTPException(status_code=404, detail="not_found")
    from lumi.db.models import CalendarSource

    if event.source != CalendarSource.INTERNAL:
        # External calendars are read-only mirrors — removing them here would
        # just resurrect on the next sync.
        raise HTTPException(status_code=409, detail="read_only_source")
    event.status = CalendarEventStatus.CANCELLED
    await RealtimeEventService(session).emit(
        user_id=user.id,
        topics=["calendar"],
        event_type="calendar_event.cancelled",
        payload={"event_id": str(event.id)},
    )
    return {"ok": True}


@router.post("/calendar/sync")
async def sync_calendar(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from lumi.connectors.yandex.caldav_client import get_yandex_connector_row

    yandex_row = await get_yandex_connector_row(session, user)
    yandex_ok = yandex_row is not None and bool(yandex_row.credentials_encrypted)
    if not token_file_exists() and not yandex_ok:
        raise HTTPException(status_code=409, detail="calendar_not_connected")
    return await start_background_run(session, user, "calendar_sync", notify=False)
