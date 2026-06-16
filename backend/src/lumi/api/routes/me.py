"""GET /api/me, /api/settings, /api/messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi import __version__
from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import message_to_dict, user_to_dict
from lumi.config import get_settings
from lumi.connectors.google.auth import connection_status
from lumi.db.models import Message, MessageRole, User
from lumi.services.realtime import RealtimeEventService

router = APIRouter()


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict:
    return {"user": user_to_dict(user)}


@router.get("/settings")
async def get_app_settings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from lumi.api.routes.connectors import _yandex_status_payload
    from lumi.connectors.yandex.caldav_client import get_yandex_connector_row

    settings = get_settings()
    google = await connection_status()
    yandex = _yandex_status_payload(await get_yandex_connector_row(session, user))
    return {
        "user": user_to_dict(user),
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.minimax_model if settings.llm_provider == "minimax" else "mock-1",
            "configured": settings.llm_configured,
        },
        "google": google,
        "yandex": yandex,
        "flags": {
            "store_email_bodies": settings.store_email_bodies,
            "store_llm_debug_payloads": settings.store_llm_debug_payloads,
            "dev_auth": settings.dev_auth_enabled,
        },
        "app": {"public_url": settings.app_public_url, "env": settings.app_env,
                "version": __version__},
    }


class SettingsPatch(BaseModel):
    timezone: str | None = None
    locale: str | None = None
    settings: dict | None = None


@router.patch("/settings")
async def patch_settings(
    payload: SettingsPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if payload.timezone:
        from lumi.utils.time import get_zone

        get_zone(payload.timezone)  # validates / falls back
        user.timezone = payload.timezone
    if payload.locale:
        user.locale = payload.locale
    if payload.settings is not None:
        user.settings = {**user.settings, **payload.settings}
    session.add(user)
    await RealtimeEventService(session).emit(
        user_id=user.id,
        topics=["settings"],
        event_type="settings.updated",
        payload={},
    )
    return {"user": user_to_dict(user)}


@router.get("/messages")
async def list_messages(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    result = await session.execute(
        select(Message)
        .where(
            Message.user_id == user.id,
            Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    items = [message_to_dict(m) for m in result.scalars()]
    items.reverse()
    return {"items": items}
