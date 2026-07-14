"""FastAPI dependencies: DB session, authenticated user."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.config import get_settings
from lumi.db.models import User
from lumi.db.session import get_session_factory
from lumi.logging import get_logger
from lumi.security.telegram_auth import InitDataError, validate_init_data
from lumi.security.web_auth import (
    WEB_SESSION_COOKIE,
    InvalidCsrfToken,
    InvalidWebOrigin,
    InvalidWebSession,
    WebAuthNotConfigured,
    WebAuthUnavailable,
    resolve_web_session,
    revoke_web_session,
    validate_web_csrf,
)
from lumi.services.users import UserService

log = get_logger(__name__)

INIT_DATA_HEADER = "X-Telegram-Init-Data"


async def get_db() -> AsyncIterator[AsyncSession]:
    from lumi.services.realtime import commit_with_realtime, rollback_with_realtime

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await commit_with_realtime(session)
        except BaseException:
            await rollback_with_realtime(session)
            raise


async def resolve_current_user(request: Request, session: AsyncSession) -> User:
    settings = get_settings()
    init_data = request.headers.get(INIT_DATA_HEADER, "")

    if init_data:
        try:
            tg_user = validate_init_data(init_data, settings.telegram_bot_token)
        except InitDataError as exc:
            log.warning("initData rejected", fields={"reason": str(exc)})
            raise HTTPException(status_code=401, detail="unauthorized") from exc
        if tg_user.id not in settings.allowed_telegram_user_ids:
            existing = await UserService(session).get_by_telegram_id(tg_user.id)
            if existing is None or not existing.is_allowed:
                if settings.log_unauthorized_telegram_ids:
                    log.warning("mini app: user not allowlisted",
                                fields={"telegram_user_id": tg_user.id})
                raise HTTPException(status_code=401, detail="unauthorized")
        users = UserService(session)
        user = await users.ensure_user(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        await users.ensure_main_conversation(user)
        return user

    session_cookie = request.cookies.get(WEB_SESSION_COOKIE)
    if session_cookie:
        try:
            web_session = await resolve_web_session(session_cookie)
        except WebAuthUnavailable as exc:
            raise HTTPException(status_code=503, detail="auth_unavailable") from exc
        except (InvalidWebSession, WebAuthNotConfigured) as exc:
            raise HTTPException(status_code=401, detail="unauthorized") from exc

        web_user = await session.get(User, web_session.user_id)
        if web_user is None or (
            web_user.telegram_user_id not in settings.allowed_telegram_user_ids
            and not web_user.is_allowed
        ):
            try:
                await revoke_web_session(web_session)
            except WebAuthUnavailable:
                pass
            raise HTTPException(status_code=401, detail="unauthorized")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                validate_web_csrf(request, web_session)
            except InvalidWebOrigin as exc:
                raise HTTPException(status_code=403, detail="invalid_origin") from exc
            except InvalidCsrfToken as exc:
                raise HTTPException(status_code=403, detail="csrf_failed") from exc
            except WebAuthNotConfigured as exc:
                raise HTTPException(status_code=503, detail="web_auth_not_configured") from exc
        return web_user

    # Local-dev fallback: explicit opt-in only.
    if settings.dev_auth_enabled and settings.is_local and settings.dev_auth_telegram_user_id:
        users = UserService(session)
        user = await users.ensure_user(settings.dev_auth_telegram_user_id)
        await users.ensure_main_conversation(user)
        return user

    raise HTTPException(status_code=401, detail="unauthorized")


async def get_current_user(request: Request, session: AsyncSession = Depends(get_db)) -> User:
    return await resolve_current_user(request, session)
