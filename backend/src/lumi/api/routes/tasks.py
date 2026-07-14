"""Tasks API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import task_to_dict
from lumi.db.models import User
from lumi.services.tasks import TaskService
from lumi.utils.time import utc_now

router = APIRouter()


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: str = "medium"
    project: str | None = None
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)
    due_at: datetime | None = None
    planned_for: datetime | None = None
    target_at: datetime | None = None
    reminder_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    estimate_source: str | None = None

    @model_validator(mode="after")
    def planned_for_matches_legacy_alias(self) -> Self:
        if (
            "planned_for" in self.model_fields_set
            and "target_at" in self.model_fields_set
            and self.planned_for != self.target_at
        ):
            raise ValueError("planned_for_conflicts_with_target_at")
        return self


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    project: str | None = None
    project_id: uuid.UUID | None = None
    tags: list[str] | None = None
    due_at: datetime | None = None
    planned_for: datetime | None = None
    target_at: datetime | None = None
    reminder_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    estimate_source: str | None = None
    status: str | None = None
    review_skips: dict[str, bool] | None = None

    @model_validator(mode="after")
    def planned_for_matches_legacy_alias(self) -> Self:
        if (
            "planned_for" in self.model_fields_set
            and "target_at" in self.model_fields_set
            and self.planned_for != self.target_at
        ):
            raise ValueError("planned_for_conflicts_with_target_at")
        return self


class SnoozeBody(BaseModel):
    preset: str | None = None
    until: datetime | None = None


@router.get("/tasks")
async def list_tasks(
    filter: str = Query(
        default="all",
        pattern="^(today|upcoming|inbox|this_week|later|review|done|all)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    now = utc_now()
    tasks, has_more, next_offset = await TaskService(session).list_task_page(
        user,
        filter_=filter,
        limit=limit,
        offset=offset,
        q=q,
        project_id=project_id,
        now=now,
    )
    return {
        "items": [task_to_dict(task, timezone=user.timezone, now=now) for task in tasks],
        "has_more": has_more,
        "next_offset": next_offset,
    }


@router.post("/tasks", status_code=201)
async def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        task = await TaskService(session).create_task(
            user,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            project=payload.project,
            project_id=payload.project_id,
            tags=payload.tags,
            due_at=payload.due_at,
            target_at=(
                payload.planned_for
                if "planned_for" in payload.model_fields_set
                else payload.target_at
            ),
            reminder_at=payload.reminder_at,
            estimated_minutes=payload.estimated_minutes,
            estimate_source=payload.estimate_source,
            source="manual",
            created_by="user",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"task": task_to_dict(task, timezone=user.timezone)}


async def _get_task_or_404(session: AsyncSession, user: User, task_id: str):
    try:
        parsed = uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    task = await TaskService(session).get(user, parsed)
    if task is None:
        raise HTTPException(status_code=404, detail="not_found")
    return task


@router.patch("/tasks/{task_id}")
async def patch_task(
    task_id: str,
    payload: TaskPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    task = await _get_task_or_404(session, user, task_id)
    updates = payload.model_dump(exclude_unset=True)
    if "planned_for" in updates:
        updates["target_at"] = updates.pop("planned_for")
    try:
        task = await TaskService(session).update_task(user, task, updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"task": task_to_dict(task, timezone=user.timezone)}


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    task = await _get_task_or_404(session, user, task_id)
    task = await TaskService(session).complete_task(user, task)
    return {"task": task_to_dict(task, timezone=user.timezone)}


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(
    task_id: str,
    payload: SnoozeBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    task = await _get_task_or_404(session, user, task_id)
    task = await TaskService(session).snooze_task(
        user, task, preset=payload.preset, until=payload.until
    )
    return {"task": task_to_dict(task, timezone=user.timezone)}
