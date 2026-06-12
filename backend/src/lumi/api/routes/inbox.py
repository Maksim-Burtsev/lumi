"""Inbox (email) API."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.run_helper import start_background_run
from lumi.api.serializers import task_to_dict, thread_to_dict
from lumi.connectors.google.auth import token_file_exists
from lumi.db.models import User
from lumi.services.email import EmailService
from lumi.services.tasks import TaskService
from lumi.utils.time import local_to_utc

router = APIRouter()


@router.get("/inbox/summary")
async def inbox_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    summary = await EmailService(session).inbox_summary(user)
    return {
        "connected": token_file_exists(),
        "last_triage_at": summary["last_triage_at"].isoformat() if summary["last_triage_at"] else None,
        "counts": summary["counts"],
        "threads": [thread_to_dict(t) for t in summary["threads"]],
    }


@router.post("/inbox/triage/run")
async def run_triage(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if not token_file_exists():
        raise HTTPException(status_code=409, detail="google_not_connected")
    return await start_background_run(session, user, "email_triage")


@router.post("/inbox/threads/{thread_id}/create-task")
async def create_task_from_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    email_service = EmailService(session)
    try:
        thread = await email_service.get_thread(user, uuid.UUID(thread_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    if thread is None:
        raise HTTPException(status_code=404, detail="not_found")

    candidate = (thread.metadata_ or {}).get("task_candidate") or {}
    title = candidate.get("title") or thread.subject or "Письмо: ответить"
    due_at = None
    if candidate.get("due_at_local"):
        try:
            due_at = local_to_utc(datetime.fromisoformat(candidate["due_at_local"]), user.timezone)
        except ValueError:
            due_at = None
    task = await TaskService(session).create_task(
        user,
        title=title,
        priority=candidate.get("priority", "medium"),
        due_at=due_at,
        source="email",
        created_by="user",
    )
    thread.metadata_ = {**thread.metadata_, "task_created": str(task.id)}
    return {"task": task_to_dict(task)}
