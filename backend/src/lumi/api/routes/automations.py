"""Automations API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.run_helper import start_background_run
from lumi.api.serializers import automation_to_dict
from lumi.db.models import User
from lumi.services.automations import AutomationService

router = APIRouter()

VALID_TYPES = {"morning_brief", "news_digest", "email_triage", "daily_planning", "calendar_sync",
               "task_review", "custom_prompt"}


class AutomationCreate(BaseModel):
    type: str
    title: str = Field(min_length=1, max_length=200)
    cron_expression: str = ""
    timezone: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    # One-shot run: fire once at this moment instead of a cron schedule.
    run_at: datetime | None = None


class AutomationPatch(BaseModel):
    title: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


@router.get("/automations")
async def list_automations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    automations = await AutomationService(session).list_for_user(user)
    return {"items": [automation_to_dict(a) for a in automations]}


@router.post("/automations", status_code=201)
async def create_automation(
    payload: AutomationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if payload.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail="bad_type")
    if not payload.cron_expression and payload.run_at is None:
        raise HTTPException(status_code=422, detail="need_cron_or_run_at")
    try:
        automation = await AutomationService(session).create(
            user,
            type_=payload.type,
            title=payload.title,
            cron_expression=payload.cron_expression,
            timezone=payload.timezone,
            config=payload.config,
            enabled=payload.enabled,
            run_at=payload.run_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"automation": automation_to_dict(automation)}


async def _get_or_404(session: AsyncSession, user: User, automation_id: str):
    try:
        parsed = uuid.UUID(automation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    automation = await AutomationService(session).get(user, parsed)
    if automation is None:
        raise HTTPException(status_code=404, detail="not_found")
    return automation


@router.patch("/automations/{automation_id}")
async def patch_automation(
    automation_id: str,
    payload: AutomationPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    automation = await _get_or_404(session, user, automation_id)
    try:
        automation = await AutomationService(session).update(
            user, automation, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"automation": automation_to_dict(automation)}


@router.post("/automations/{automation_id}/run")
async def run_automation(
    automation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    automation = await _get_or_404(session, user, automation_id)
    job_kwargs: dict[str, Any] = {}
    if automation.type.value == "custom_prompt":
        job_kwargs["prompt"] = (automation.config or {}).get("prompt", "")
    return await start_background_run(
        session, user, automation.type.value,
        scheduled_task_id=automation.id, **job_kwargs,
    )
