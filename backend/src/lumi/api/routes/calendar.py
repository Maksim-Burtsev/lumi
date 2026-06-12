"""Calendar API: events, free slots, plan-day, sync, confirm blocks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.run_helper import start_background_run
from lumi.api.serializers import event_to_dict
from lumi.connectors.google.auth import token_file_exists
from lumi.db.models import CalendarEventStatus, User
from lumi.services.calendar import CalendarService
from lumi.utils.time import utc_now

router = APIRouter()


class EventCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    description: str | None = None


class PlanDayBody(BaseModel):
    date: str | None = None


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
    return {"items": [event_to_dict(e) for e in events]}


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
