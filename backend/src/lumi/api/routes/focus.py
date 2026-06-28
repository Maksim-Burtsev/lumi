"""Focus timer API."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import focus_session_to_dict
from lumi.db.models import User
from lumi.services.focus import FocusService

router = APIRouter()


class FocusStart(BaseModel):
    task_id: uuid.UUID | None = None
    project: str | None = Field(default=None, max_length=120)
    intention: str = Field(min_length=1, max_length=300)
    planned_minutes: int = Field(ge=1, le=240)


class FocusFinish(BaseModel):
    ended_at: datetime | None = None
    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


class FocusUpdate(BaseModel):
    task_id: uuid.UUID | None = None
    project: str | None = Field(default=None, max_length=120)
    intention: str | None = Field(default=None, min_length=1, max_length=300)
    accomplished_text: str | None = Field(default=None, max_length=2000)
    distraction_text: str | None = Field(default=None, max_length=2000)
    next_step_text: str | None = Field(default=None, max_length=1000)
    focus_score: int | None = Field(default=None, ge=1, le=5)


class FocusLog(BaseModel):
    task_id: uuid.UUID | None = None
    project: str | None = Field(default=None, max_length=120)
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


async def _with_task(service: FocusService, user: User, focus_session):
    task = await service.get_task(user, focus_session.task_id)
    return focus_session_to_dict(focus_session, task)


@router.get("/focus/state")
async def focus_state(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    active = await service.get_active(user)
    recent = await service.recent_sessions(user)
    return {
        "active_session": await _with_task(service, user, active) if active else None,
        "today": await service.today_totals(user),
        "recent_sessions": [await _with_task(service, user, item) for item in recent],
    }


@router.get("/focus/summary")
async def focus_summary(
    period: str = Query(default="week", pattern="^(week|month)$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    summary = await FocusService(session).summary(user, period=period)
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
    period: str = Query(default="week", pattern="^(week|month)$"),
    limit: int = Query(default=100, ge=1, le=300),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    sessions = await service.list_sessions(user, period=period, limit=limit)
    return {"items": [await _with_task(service, user, item) for item in sessions]}


@router.post("/focus/sessions", status_code=201)
async def start_focus_session(
    payload: FocusStart,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    try:
        focus_session = await service.start_session(
            user,
            task_id=payload.task_id,
            project=payload.project,
            intention=payload.intention,
            planned_minutes=payload.planned_minutes,
        )
    except ValueError as exc:
        code = str(exc)
        status = 409 if code == "active_focus_session_exists" else 404
        raise HTTPException(status_code=status, detail=code) from exc
    return {"session": await _with_task(service, user, focus_session)}


@router.post("/focus/sessions/log", status_code=201)
async def log_focus_session(
    payload: FocusLog,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    try:
        focus_session = await service.log_session(
            user,
            task_id=payload.task_id,
            project=payload.project,
            intention=payload.intention,
            logged_at=payload.logged_at,
            duration_minutes=payload.duration_minutes,
            accomplished_text=payload.accomplished_text,
            distraction_text=payload.distraction_text,
            next_step_text=payload.next_step_text,
            focus_score=payload.focus_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session": await _with_task(service, user, focus_session)}


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
            ended_at=payload.ended_at,
            accomplished_text=payload.accomplished_text,
            distraction_text=payload.distraction_text,
            next_step_text=payload.next_step_text,
            focus_score=payload.focus_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session": await _with_task(service, user, focus_session)}


@router.patch("/focus/sessions/{session_id}")
async def update_focus_session(
    session_id: str,
    payload: FocusUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = FocusService(session)
    focus_session = await _session_or_404(service, user, session_id)
    try:
        focus_session = await service.update_completed_session(
            user,
            focus_session,
            intention=payload.intention,
            task_id=payload.task_id,
            project=payload.project,
            accomplished_text=payload.accomplished_text,
            distraction_text=payload.distraction_text,
            next_step_text=payload.next_step_text,
            focus_score=payload.focus_score,
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "task_not_found" else 409
        raise HTTPException(status_code=status, detail=code) from exc
    return {"session": await _with_task(service, user, focus_session)}


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
    return {"session": await _with_task(service, user, focus_session)}
