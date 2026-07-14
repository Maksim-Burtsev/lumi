"""Short-lived Telegram web login and revocable standalone sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from fastapi import Request

from lumi.config import get_settings
from lumi.logging import get_logger
from lumi.worker.queue import get_queue

log = get_logger(__name__)

LOGIN_NONCE_TTL_SECONDS = 5 * 60
WEB_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
WEB_SESSION_COOKIE = "lumi_web_session"
WEB_CSRF_COOKIE = "lumi_web_csrf"
CSRF_HEADER = "X-CSRF-Token"
_LOGIN_PREFIX = "lumi:web_login:"
_SESSION_PREFIX = "lumi:web_session:"


class WebAuthNotConfigured(Exception):
    pass


class WebAuthUnavailable(Exception):
    pass


class InvalidWebLogin(Exception):
    pass


class InvalidWebSession(Exception):
    pass


class InvalidWebOrigin(Exception):
    pass


class InvalidCsrfToken(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WebSession:
    session_id: str
    user_id: uuid.UUID
    expires_at: int
    csrf_token: str


def _secret() -> bytes:
    value = get_settings().web_session_secret
    if not value:
        raise WebAuthNotConfigured
    return value.encode()


def configured_web_origin() -> str:
    raw = get_settings().app_public_url
    if not raw:
        raise WebAuthNotConfigured
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise WebAuthNotConfigured
    return f"https://{parsed.netloc}"


def validate_web_origin(request: Request) -> None:
    if request.headers.get("Origin") != configured_web_origin():
        raise InvalidWebOrigin


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _encode_mac(value: str, *, purpose: str = "session") -> str:
    digest = hmac.new(_secret(), f"{purpose}:{value}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _login_key(nonce: str) -> str:
    return _LOGIN_PREFIX + _digest(nonce)


def _session_key(session_id: str) -> str:
    return _SESSION_PREFIX + _digest(session_id)


async def _redis():
    try:
        return await get_queue()
    except Exception as exc:  # noqa: BLE001 - authentication must fail closed
        log.exception("web auth redis unavailable")
        raise WebAuthUnavailable from exc


async def issue_web_login(user_id: uuid.UUID) -> str:
    """Return a regular browser URL carrying a one-time nonce in the fragment."""
    _secret()
    configured_web_origin()
    redis = await _redis()
    for _ in range(3):
        nonce = secrets.token_urlsafe(32)
        try:
            stored = await redis.set(
                _login_key(nonce),
                str(user_id),
                ex=LOGIN_NONCE_TTL_SECONDS,
                nx=True,
            )
        except Exception as exc:  # noqa: BLE001 - authentication must fail closed
            log.exception("web login nonce storage failed")
            raise WebAuthUnavailable from exc
        if stored:
            base = get_settings().mini_app_url
            if not base:  # guarded by configured_web_origin; keeps the type narrow
                raise WebAuthNotConfigured
            return f"{base.rstrip('/')}/#/web-login?nonce={quote(nonce)}"
    raise WebAuthUnavailable


async def consume_web_login(nonce: str) -> uuid.UUID:
    if not nonce or len(nonce) > 128:
        raise InvalidWebLogin
    redis = await _redis()
    try:
        raw_user_id = await redis.getdel(_login_key(nonce))
    except Exception as exc:  # noqa: BLE001 - authentication must fail closed
        log.exception("web login nonce exchange failed")
        raise WebAuthUnavailable from exc
    if not raw_user_id:
        raise InvalidWebLogin
    if isinstance(raw_user_id, bytes):
        raw_user_id = raw_user_id.decode()
    try:
        return uuid.UUID(str(raw_user_id))
    except ValueError as exc:
        raise InvalidWebLogin from exc


async def issue_web_session(
    user_id: uuid.UUID,
    *,
    _now: float | None = None,
) -> tuple[str, WebSession]:
    now = int(time.time() if _now is None else _now)
    expires_at = now + WEB_SESSION_TTL_SECONDS
    redis = await _redis()
    for _ in range(3):
        session_id = secrets.token_urlsafe(32)
        try:
            stored = await redis.set(
                _session_key(session_id),
                str(user_id),
                ex=WEB_SESSION_TTL_SECONDS,
                nx=True,
            )
        except Exception as exc:  # noqa: BLE001 - authentication must fail closed
            log.exception("web session storage failed")
            raise WebAuthUnavailable from exc
        if not stored:
            continue
        payload = f"{session_id}.{expires_at}"
        cookie = f"{payload}.{_encode_mac(payload)}"
        session = WebSession(
            session_id=session_id,
            user_id=user_id,
            expires_at=expires_at,
            csrf_token=_encode_mac(session_id, purpose="csrf"),
        )
        return cookie, session
    raise WebAuthUnavailable


def _parse_session_cookie(cookie: str, *, now: int) -> tuple[str, int]:
    try:
        session_id, raw_expiry, signature = cookie.split(".")
        expires_at = int(raw_expiry)
    except (TypeError, ValueError) as exc:
        raise InvalidWebSession from exc
    if len(session_id) < 32 or len(session_id) > 128:
        raise InvalidWebSession
    payload = f"{session_id}.{expires_at}"
    if not hmac.compare_digest(signature, _encode_mac(payload)) or expires_at <= now:
        raise InvalidWebSession
    return session_id, expires_at


async def resolve_web_session(cookie: str, *, _now: float | None = None) -> WebSession:
    now = int(time.time() if _now is None else _now)
    session_id, expires_at = _parse_session_cookie(cookie, now=now)
    redis = await _redis()
    try:
        raw_user_id = await redis.get(_session_key(session_id))
    except Exception as exc:  # noqa: BLE001 - authentication must fail closed
        log.exception("web session lookup failed")
        raise WebAuthUnavailable from exc
    if not raw_user_id:
        raise InvalidWebSession
    if isinstance(raw_user_id, bytes):
        raw_user_id = raw_user_id.decode()
    try:
        user_id = uuid.UUID(str(raw_user_id))
    except ValueError as exc:
        raise InvalidWebSession from exc
    return WebSession(
        session_id=session_id,
        user_id=user_id,
        expires_at=expires_at,
        csrf_token=_encode_mac(session_id, purpose="csrf"),
    )


def validate_web_csrf(request: Request, web_session: WebSession) -> None:
    validate_web_origin(request)
    header = request.headers.get(CSRF_HEADER, "")
    cookie = request.cookies.get(WEB_CSRF_COOKIE, "")
    if (
        not header
        or not cookie
        or not hmac.compare_digest(header, cookie)
        or not hmac.compare_digest(header, web_session.csrf_token)
    ):
        raise InvalidCsrfToken


async def revoke_web_session(web_session: WebSession) -> None:
    redis = await _redis()
    try:
        await redis.delete(_session_key(web_session.session_id))
    except Exception as exc:  # noqa: BLE001 - authentication must fail closed
        log.exception("web session revocation failed")
        raise WebAuthUnavailable from exc
