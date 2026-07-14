"""Standalone web authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_db
from lumi.config import get_settings
from lumi.db.models import User
from lumi.security.web_auth import (
    WEB_CSRF_COOKIE,
    WEB_SESSION_COOKIE,
    WEB_SESSION_TTL_SECONDS,
    InvalidCsrfToken,
    InvalidWebLogin,
    InvalidWebOrigin,
    InvalidWebSession,
    WebAuthNotConfigured,
    WebAuthUnavailable,
    consume_web_login,
    issue_web_session,
    resolve_web_session,
    revoke_web_session,
    validate_web_csrf,
    validate_web_origin,
)

router = APIRouter()


class WebLoginBody(BaseModel):
    nonce: str = Field(min_length=32, max_length=128)


def _is_allowed(user: User) -> bool:
    settings = get_settings()
    return user.telegram_user_id in settings.allowed_telegram_user_ids or user.is_allowed


def _set_auth_cookies(
    response: JSONResponse,
    session_cookie: str,
    csrf_token: str,
    expires_at: int,
) -> None:
    expires = datetime.fromtimestamp(expires_at, UTC)
    response.set_cookie(
        WEB_SESSION_COOKIE,
        session_cookie,
        max_age=WEB_SESSION_TTL_SECONDS,
        expires=expires,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        WEB_CSRF_COOKIE,
        csrf_token,
        max_age=WEB_SESSION_TTL_SECONDS,
        expires=expires,
        path="/",
        secure=True,
        httponly=False,
        samesite="strict",
    )


def _clear_auth_cookies(response: JSONResponse) -> None:
    response.delete_cookie(
        WEB_SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        WEB_CSRF_COOKIE,
        path="/",
        secure=True,
        httponly=False,
        samesite="strict",
    )


@router.post("/auth/web/exchange")
async def exchange_web_login(
    payload: WebLoginBody,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        validate_web_origin(request)
        user_id = await consume_web_login(payload.nonce)
        user = await session.get(User, user_id)
        if user is None or not _is_allowed(user):
            raise InvalidWebLogin
        session_cookie, web_session = await issue_web_session(user.id)
    except WebAuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail="web_auth_not_configured") from exc
    except WebAuthUnavailable as exc:
        raise HTTPException(status_code=503, detail="auth_unavailable") from exc
    except InvalidWebOrigin as exc:
        raise HTTPException(status_code=403, detail="invalid_origin") from exc
    except InvalidWebLogin as exc:
        raise HTTPException(status_code=401, detail="invalid_or_expired_login") from exc

    response = JSONResponse(
        {"authenticated": True},
        headers={"Cache-Control": "no-store"},
    )
    _set_auth_cookies(
        response,
        session_cookie,
        web_session.csrf_token,
        web_session.expires_at,
    )
    return response


@router.post("/auth/web/logout")
async def logout_web(request: Request) -> JSONResponse:
    try:
        validate_web_origin(request)
        cookie = request.cookies.get(WEB_SESSION_COOKIE)
        if cookie:
            web_session = await resolve_web_session(cookie)
            validate_web_csrf(request, web_session)
            await revoke_web_session(web_session)
    except WebAuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail="web_auth_not_configured") from exc
    except WebAuthUnavailable as exc:
        raise HTTPException(status_code=503, detail="auth_unavailable") from exc
    except InvalidWebOrigin as exc:
        raise HTTPException(status_code=403, detail="invalid_origin") from exc
    except InvalidCsrfToken as exc:
        raise HTTPException(status_code=403, detail="csrf_failed") from exc
    except InvalidWebSession:
        pass  # Idempotent logout still clears a stale browser cookie.

    response = JSONResponse(
        {"authenticated": False},
        headers={"Cache-Control": "no-store"},
    )
    _clear_auth_cookies(response)
    return response
