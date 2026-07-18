"""Focus timer API."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import focus_session_to_dict
from lumi.db.models import User
from lumi.services.focus import FocusService

router = APIRouter()


class FocusStart(BaseModel):
    task_id: uuid.UUID | None = None
    planned_event_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("project_name", "project"),
    )
    intention: str = Field(min_length=1, max_length=300)
    planned_minutes: int = Field(ge=1, le=240)
    break_minutes: int = Field(default=0, ge=0, le=60)


class FocusFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


class FocusUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("project_name", "project"),
    )
    intention: str | None = Field(default=None, min_length=1, max_length=300)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


class FocusLog(BaseModel):
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("project_name", "project"),
    )
    intention: str = Field(min_length=1, max_length=300)
    logged_at: datetime
    duration_minutes: int = Field(ge=1, le=240)
    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


async def _session_or_404(service: FocusService, user: User, session_id: str):
    try:
        parsed = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    focus_session = await service.get_session(user, parsed)
    if focus_session is None:
        raise HTTPException(status_code=404, detail="not_found")
    return focus_session


async def _serialize_sessions(service: FocusService, user: User, focus_sessions: list) -> list[dict]:
    tasks, projects = await service.related_entities(user, focus_sessions)
    return [
        focus_session_to_dict(
            item,
            tasks.get(item.task_id),
            projects.get(item.project_id),
            timezone=user.timezone,
        )
        for item in focus_sessions
    ]


async def _serialize_session(service: FocusService, user: User, focus_session) -> dict:
    return (await _serialize_sessions(service, user, [focus_session]))[0]


@router.get("/focus/state")
async def focus_state(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    active = await service.get_active(user)
    active_break = await service.get_active_break(user)
    recent = await service.recent_sessions(user)
    serialized = await _serialize_sessions(service, user, ([active] if active else []) + recent)
    return {
        "active_session": serialized[0] if active else None,
        "active_break": (
            await _serialize_session(service, user, active_break) if active_break else None
        ),
        "today": await service.today_totals(user),
        "recent_sessions": serialized[1:] if active else serialized,
    }


@router.get("/focus/summary")
async def focus_summary(
    period: str = Query(default="week", pattern="^(week|month|custom)$"),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        summary = await FocusService(session).summary(
            user,
            period=period,
            from_date=from_date,
            to_date=to_date,
            q=q,
            project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "period": summary.period,
        "total_focus_seconds": summary.total_focus_seconds,
        "total_sessions": summary.total_sessions,
        "streak_days": summary.streak_days,
        "average_focus_score": summary.average_focus_score,
        "average_daily_focus_seconds": summary.average_daily_focus_seconds,
        "average_daily_focus_delta_percent": summary.average_daily_focus_delta_percent,
        "total_focus_delta_percent": summary.total_focus_delta_percent,
        "most_focused_daypart": summary.most_focused_daypart,
        "daypart_breakdown": summary.daypart_breakdown,
        "daily_activity": summary.daily_activity,
        "project_breakdown": summary.project_breakdown,
        "next_steps": summary.next_steps,
    }


@router.get("/focus/sessions")
async def list_focus_sessions(
    period: str = Query(default="week", pattern="^(week|month|custom)$"),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    try:
        sessions, has_more, next_offset = await service.list_sessions(
            user,
            period=period,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            q=q,
            project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": await _serialize_sessions(service, user, sessions),
        "has_more": has_more,
        "next_offset": next_offset,
    }


@router.get("/focus/sessions/{session_id}")
async def get_focus_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    return {"session": await _serialize_session(service, user, focus_session)}


@router.post("/focus/sessions", status_code=201)
async def start_focus_session(
    payload: FocusStart,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    project_fields = payload.model_dump(
        include={"project_id", "project_name"},
        exclude_unset=True,
    )
    try:
        focus_session = await service.start_session(
            user,
            task_id=payload.task_id,
            planned_event_id=payload.planned_event_id,
            intention=payload.intention,
            planned_minutes=payload.planned_minutes,
            break_minutes=payload.break_minutes,
            **project_fields,
        )
    except ValueError as exc:
        code = str(exc)
        status = 409 if code in {
            "active_focus_session_exists",
            "active_break_exists",
            "planned_event_conflicted",
        } else 404
        if code in {
            "invalid_focus_break",
            "invalid_focus_intention",
            "planned_event_not_confirmed",
            "planned_event_not_work_block",
            "planned_event_task_mismatch",
            "project_mismatch",
            "task_not_active",
        }:
            status = 422
        raise HTTPException(status_code=status, detail=code) from exc
    return {"session": await _serialize_session(service, user, focus_session)}


@router.post("/focus/sessions/log", status_code=201)
async def log_focus_session(
    payload: FocusLog,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    project_fields = payload.model_dump(
        include={"project_id", "project_name"},
        exclude_unset=True,
    )
    try:
        focus_session = await service.log_session(
            user,
            task_id=payload.task_id,
            intention=payload.intention,
            logged_at=payload.logged_at,
            duration_minutes=payload.duration_minutes,
            accomplished_text=payload.accomplished_text,
            distraction_text=payload.distraction_text,
            next_step_text=payload.next_step_text,
            focus_score=payload.focus_score,
            **project_fields,
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code in {"task_not_found", "project_not_found"} else 422
        raise HTTPException(status_code=status, detail=code) from exc
    return {"session": await _serialize_session(service, user, focus_session)}


@router.post("/focus/sessions/{session_id}/finish")
async def finish_focus_session(
    session_id: str,
    payload: FocusFinish,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    try:
        focus_session = await service.finish_session(
            user,
            focus_session,
            accomplished_text=payload.accomplished_text,
            distraction_text=payload.distraction_text,
            next_step_text=payload.next_step_text,
            focus_score=payload.focus_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session": await _serialize_session(service, user, focus_session)}


@router.post("/focus/sessions/{session_id}/break/finish")
async def finish_focus_break(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    try:
        focus_session = await service.finish_break(user, focus_session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session": await _serialize_session(service, user, focus_session)}


@router.patch("/focus/sessions/{session_id}")
async def update_focus_session(
    session_id: str,
    payload: FocusUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    updates = payload.model_dump(exclude_unset=True)
    try:
        focus_session = await service.update_completed_session(
            user,
            focus_session,
            updates=updates,
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"task_not_found", "project_not_found", "focus_session_not_found"}:
            status = 404
        elif code in {"focus_session_not_completed", "planned_event_task_locked"}:
            status = 409
        else:
            status = 422
        raise HTTPException(status_code=status, detail=code) from exc
    return {"session": await _serialize_session(service, user, focus_session)}


@router.delete("/focus/sessions/{session_id}", status_code=204)
async def delete_focus_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    try:
        await service.delete_session(user, focus_session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/focus/sessions/{session_id}/abandon")
async def abandon_focus_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    try:
        focus_session = await service.abandon_session(user, focus_session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session": await _serialize_session(service, user, focus_session)}
