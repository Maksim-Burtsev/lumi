"""GET /api/me, /api/settings, /api/messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi import __version__
from lumi.api.deps import get_current_user, get_db
from lumi.api.serializers import message_to_dict, user_to_dict
from lumi.config import get_settings
from lumi.connectors.google.auth import connection_status
from lumi.db.models import Message, MessageRole, User
from lumi.i18n import (
    ReplyLanguageMode,
    ensure_language_settings,
    normalize_reply_language,
    normalize_reply_language_mode,
    validate_app_locale,
    validate_theme_mode,
    validate_time_format,
)
from lumi.services.realtime import RealtimeEventService
from lumi.utils.time import selectable_timezone_names, validate_timezone_name

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


@router.get("/timezones")
async def list_timezones() -> dict:
    return {"items": [{"id": tz} for tz in selectable_timezone_names()]}


class SettingsPatch(BaseModel):
    timezone: str | None = None
    locale: str | None = None
    reply_language_mode: ReplyLanguageMode | None = None
    reply_language: str | None = None
    time_format: str | None = None
    theme_mode: str | None = None
    settings: dict | None = None

    @field_validator("locale")
    @classmethod
    def locale_supported(cls, value: str | None) -> str | None:
        return validate_app_locale(value) if value else None


@router.patch("/settings")
async def patch_settings(
    payload: SettingsPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    if payload.timezone:
        try:
            user.timezone = validate_timezone_name(payload.timezone)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_timezone") from exc
    if payload.locale:
        user.locale = payload.locale
        user.settings = {**ensure_language_settings(user.settings), "locale_source": "manual"}
    else:
        user.settings = ensure_language_settings(user.settings)
    if payload.reply_language_mode:
        user.settings = {
            **ensure_language_settings(user.settings),
            "reply_language_mode": normalize_reply_language_mode(payload.reply_language_mode),
        }
    if payload.reply_language:
        user.settings = {
            **ensure_language_settings(user.settings),
            "reply_language": normalize_reply_language(payload.reply_language),
        }
    if payload.time_format is not None:
        try:
            user.settings = {
                **ensure_language_settings(user.settings),
                "time_format": validate_time_format(payload.time_format),
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_time_format") from exc
    if payload.theme_mode is not None:
        try:
            user.settings = {
                **ensure_language_settings(user.settings),
                "theme_mode": validate_theme_mode(payload.theme_mode),
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_theme_mode") from exc
    if payload.settings is not None:
        merged_settings = {**user.settings, **payload.settings}
        if "time_format" in payload.settings:
            try:
                merged_settings["time_format"] = validate_time_format(
                    str(payload.settings["time_format"] or "")
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid_time_format") from exc
        if "theme_mode" in payload.settings:
            try:
                merged_settings["theme_mode"] = validate_theme_mode(
                    str(payload.settings["theme_mode"] or "")
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid_theme_mode") from exc
        if "reply_language" in payload.settings:
            merged_settings["reply_language"] = normalize_reply_language(
                str(payload.settings["reply_language"] or "")
            )
        user.settings = ensure_language_settings(merged_settings)
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
