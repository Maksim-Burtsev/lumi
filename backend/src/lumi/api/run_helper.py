"""Shared helper: create an agent run and enqueue its worker job."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.db.models import AgentRunType, User
from lumi.services.realtime import commit_with_realtime
from lumi.services.runs import RunService
from lumi.worker.queue import enqueue_job

_BACKGROUND_RUNS = {
    "daily_planning": (AgentRunType.DAILY_PLANNING, "run_daily_planning"),
    "calendar_sync": (AgentRunType.CALENDAR_SYNC, "run_calendar_sync"),
}


async def start_background_run(
    session: AsyncSession,
    user: User,
    automation_type: str,
    *,
    trigger: str = "manual_api",
    scheduled_task_id=None,
    notify: bool = True,
    **job_kwargs,
) -> dict:
    """Create the run, COMMIT, then enqueue — the worker must see the row."""
    try:
        run_type, job_name = _BACKGROUND_RUNS[automation_type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unsupported_background_run") from exc
    run = await RunService(session).create(
        user_id=user.id,
        type_=run_type,
        trigger=trigger,
        scheduled_task_id=scheduled_task_id,
    )
    run_id = str(run.id)
    await commit_with_realtime(session)

    job_id = await enqueue_job(
        job_name,
        str(user.id),
        agent_run_id=run_id,
        scheduled_task_id=str(scheduled_task_id) if scheduled_task_id else None,
        trigger=trigger,
        notify=notify,
        **job_kwargs,
    )
    if job_id is None:
        raise HTTPException(status_code=503, detail="queue_unavailable")
    return {"run_id": run_id, "status": "queued"}
