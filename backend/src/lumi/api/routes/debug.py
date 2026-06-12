"""Local-only debug endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.config import get_settings
from lumi.db.models import AgentRun, AgentRunType, User

router = APIRouter()


@router.get("/debug/context/latest")
async def latest_context(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if not get_settings().is_local:
        raise HTTPException(status_code=404, detail="not_found")
    result = await session.execute(
        select(AgentRun)
        .where(
            AgentRun.user_id == user.id,
            AgentRun.type == AgentRunType.CHAT,
            AgentRun.metadata_["context_snapshot"].astext.is_not(None),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return {"snapshot": None, "hint": "напиши боту сообщение — появится снапшот контекста"}
    return {
        "run_id": str(run.id),
        "created_at": run.created_at.isoformat(),
        "snapshot": run.metadata_.get("context_snapshot"),
    }
