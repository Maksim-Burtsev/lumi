"""GET /api/today."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.db.models import User
from lumi.services.today import TodayService

router = APIRouter()


@router.get("/today")
async def get_today(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await TodayService(session).build_payload(user)
