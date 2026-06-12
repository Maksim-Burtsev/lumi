"""Agent runs API (observability)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import llm_call_to_dict, run_to_dict, tool_call_to_dict
from lumi.db.models import AgentRun, AgentRunType, LLMCall, ToolCall, User

router = APIRouter()


@router.get("/agent-runs")
async def list_runs(
    limit: int = Query(default=30, le=200),
    type: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(AgentRun).where(AgentRun.user_id == user.id)
    if type:
        try:
            stmt = stmt.where(AgentRun.type == AgentRunType(type))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="bad_type") from exc
    stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return {"items": [run_to_dict(r) for r in result.scalars()]}


@router.get("/agent-runs/{run_id}")
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        parsed = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    result = await session.execute(
        select(AgentRun).where(AgentRun.id == parsed, AgentRun.user_id == user.id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="not_found")

    tool_calls = await session.execute(
        select(ToolCall).where(ToolCall.agent_run_id == run.id).order_by(ToolCall.created_at)
    )
    llm_calls = await session.execute(
        select(LLMCall).where(LLMCall.agent_run_id == run.id).order_by(LLMCall.created_at)
    )
    return {
        "run": run_to_dict(run),
        "tool_calls": [tool_call_to_dict(c) for c in tool_calls.scalars()],
        "llm_calls": [llm_call_to_dict(c) for c in llm_calls.scalars()],
    }
