"""Memory API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import memory_to_dict
from lumi.assistant.memory_service import MemoryService
from lumi.db.models import User

router = APIRouter()


class MemoryPatch(BaseModel):
    status: str | None = None
    text: str | None = None
    importance: int | None = Field(default=None, ge=1, le=5)


@router.get("/memories")
async def list_memories(
    kind: str | None = None,
    status: str = Query(default="active"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        memories = await MemoryService(session).list_memories(user, kind=kind, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bad_filter") from exc
    return {"items": [memory_to_dict(m) for m in memories]}


async def _get_or_404(session: AsyncSession, user: User, memory_id: str):
    try:
        parsed = uuid.UUID(memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    memory = await MemoryService(session).get(user, parsed)
    if memory is None:
        raise HTTPException(status_code=404, detail="not_found")
    return memory


@router.patch("/memories/{memory_id}")
async def patch_memory(
    memory_id: str,
    payload: MemoryPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    memory = await _get_or_404(session, user, memory_id)
    service = MemoryService(session)
    if payload.status == "archived":
        memory = await service.archive_memory(user, memory)
    elif payload.status == "active":
        from lumi.db.models import MemoryStatus

        memory.status = MemoryStatus.ACTIVE
    if payload.text:
        memory.text_ = payload.text.strip()[:2000]
    if payload.importance is not None:
        memory.importance = payload.importance
    return {"memory": memory_to_dict(memory)}


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    memory = await _get_or_404(session, user, memory_id)
    await MemoryService(session).delete_memory(user, memory)
    return {"ok": True}
