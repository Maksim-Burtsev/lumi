"""Connectors API: Google + Yandex status / connect / disconnect."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.api.deps import get_current_user, get_db
from lumi.connectors.google import auth as google_auth
from lumi.db.models import Connector, ConnectorStatus, ConnectorType, User
from lumi.services.audit import AuditService
from lumi.services.automations import AutomationService
from lumi.services.realtime import RealtimeEventService

router = APIRouter()


@router.get("/connectors/google/status")
async def google_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    status = await google_auth.connection_status()
    # Mirror status into the connectors table for history/visibility.
    result = await session.execute(
        select(Connector).where(
            Connector.user_id == user.id, Connector.type == ConnectorType.GOOGLE
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        connector = Connector(user_id=user.id, type=ConnectorType.GOOGLE)
        session.add(connector)
    connector.status = ConnectorStatus(status["status"])
    connector.scopes = status["scopes"]
    connector.last_error = status["last_error"]
    status["last_sync_at"] = (
        connector.last_sync_at.isoformat() if connector.last_sync_at else None
    )
    return status


@router.post("/connectors/google/disconnect")
async def google_disconnect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    removed = google_auth.disconnect()
    result = await session.execute(
        select(Connector).where(
            Connector.user_id == user.id, Connector.type == ConnectorType.GOOGLE
        )
    )
    connector = result.scalar_one_or_none()
    if connector is not None:
        connector.status = ConnectorStatus.DISCONNECTED
        connector.scopes = []
    await AuditService(session).log(
        user_id=user.id, actor="user", entity_type="connector",
        action="disconnected", details={"removed_token": removed},
    )
    await RealtimeEventService(session).emit(
        user_id=user.id,
        topics=["settings", "calendar"],
        event_type="connector.disconnected",
        payload={"type": "google"},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Google web OAuth: one-tap connect from the Mini App
# ---------------------------------------------------------------------------

_OAUTH_STATE_PREFIX = "lumi:google_oauth_state:"
_OAUTH_STATE_TTL = 600  # seconds


@router.get("/connectors/google/auth-url")
async def google_auth_url(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    import secrets as _secrets

    from lumi.connectors.google.auth import (
        GoogleNotConnectedError,
        build_auth_url,
        client_secret_exists,
        redirect_uri,
    )
    from lumi.worker.queue import get_queue

    if not client_secret_exists():
        raise HTTPException(status_code=409, detail="client_secret_missing")
    if redirect_uri() is None:
        raise HTTPException(status_code=409, detail="public_url_missing")

    state = _secrets.token_urlsafe(32)
    redis = await get_queue()
    await redis.setex(_OAUTH_STATE_PREFIX + state, _OAUTH_STATE_TTL, str(user.id))
    try:
        url = build_auth_url(state)
    except GoogleNotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"url": url, "redirect_uri": redirect_uri()}


@router.get("/connectors/google/callback")
async def google_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """Google redirects the browser here — no initData auth by design;
    the request is authenticated by the single-use state token."""
    import uuid as _uuid

    from fastapi.responses import HTMLResponse

    from lumi.connectors.google.auth import exchange_code
    from lumi.worker.queue import get_queue

    def page(title: str, body: str) -> HTMLResponse:
        return HTMLResponse(
            "<html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>body{font-family:-apple-system,system-ui;display:flex;align-items:center;"
            "justify-content:center;min-height:90vh;background:#f3f5f8;color:#0f1420;margin:0}"
            ".c{max-width:340px;text-align:center;padding:32px;background:#fff;border-radius:22px;"
            "box-shadow:0 12px 32px rgba(15,20,32,.07)}h2{font-size:20px;margin:0 0 8px}"
            "p{color:#6f7787;font-size:14px;line-height:1.5;margin:0}</style></head>"
            f"<body><div class='c'><h2>{title}</h2><p>{body}</p></div></body></html>"
        )

    if error:
        return page("Доступ не выдан", "Можно закрыть это окно и попробовать снова из Lumi.")
    if not code or not state:
        return page("Что-то не так", "Не хватает параметров. Запусти подключение из Lumi заново.")

    redis = await get_queue()
    key = _OAUTH_STATE_PREFIX + state
    user_id_raw = await redis.get(key)
    if not user_id_raw:
        return page("Ссылка устарела", "Запусти подключение из Lumi ещё раз — ссылка живет 10 минут.")
    await redis.delete(key)

    try:
        await exchange_code(code)
    except Exception:  # noqa: BLE001 — show a calm page, log the details
        from lumi.logging import get_logger

        get_logger(__name__).exception("google oauth code exchange failed")
        return page("Не получилось", "Google не принял обмен кодом. Попробуй ещё раз из Lumi.")

    # Mark the connector and kick the first sync for this user.
    user_id = _uuid.UUID(
        user_id_raw.decode() if isinstance(user_id_raw, bytes) else user_id_raw
    )
    result = await session.execute(select(Connector).where(
        Connector.user_id == user_id, Connector.type == ConnectorType.GOOGLE
    ))
    connector = result.scalar_one_or_none()
    if connector is None:
        connector = Connector(user_id=user_id, type=ConnectorType.GOOGLE)
        session.add(connector)
    connector.status = ConnectorStatus.CONNECTED
    connector.last_error = None
    from lumi.db.models import User as UserModel

    user_row = (await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )).scalar_one_or_none()
    if user_row is not None:
        await AutomationService(session).ensure_system_calendar_sync(user_row)
    await AuditService(session).log(
        user_id=user_id, actor="user", entity_type="connector",
        action="connected", details={"type": "google", "flow": "web_oauth"},
    )
    await RealtimeEventService(session).emit(
        user_id=user_id,
        topics=["settings", "calendar"],
        event_type="connector.connected",
        payload={"type": "google"},
    )
    if user_row is not None:
        from lumi.api.run_helper import start_background_run

        try:
            await start_background_run(session, user_row, "calendar_sync", notify=False)
        except HTTPException:
            pass  # queue down — user can sync manually

    return page("Google подключен ✓", "Почта и календарь доступны. Вернись в Lumi — статус уже обновился.")


@router.post("/connectors/google/webhook")
async def google_calendar_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Google Calendar push callback: validate channel and enqueue sync.

    Google sends only a change notification, not the changed event payload.
    """
    channel_id = request.headers.get("X-Goog-Channel-ID")
    channel_token = request.headers.get("X-Goog-Channel-Token")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    if not channel_id or not channel_token:
        raise HTTPException(status_code=400, detail="bad_channel")

    result = await session.execute(
        select(Connector).where(
            Connector.type == ConnectorType.GOOGLE,
            Connector.credentials_encrypted.is_(None),
        )
    )
    connector = None
    for candidate in result.scalars():
        watch = (candidate.metadata_ or {}).get("calendar_watch") or {}
        if (
            watch.get("channel_id") == channel_id
            and watch.get("token") == channel_token
            and (not resource_id or not watch.get("resource_id") or watch.get("resource_id") == resource_id)
        ):
            connector = candidate
            break
    if connector is None:
        raise HTTPException(status_code=404, detail="unknown_channel")

    from lumi.api.run_helper import start_background_run
    from lumi.db.models import User as UserModel

    user = (await session.execute(select(UserModel).where(UserModel.id == connector.user_id))).scalar_one()
    try:
        await start_background_run(session, user, "calendar_sync", trigger="google_webhook", notify=False)
    except HTTPException:
        connector.last_error = "queue_unavailable"
        return {"ok": False}
    return {"ok": True}


# ---------------------------------------------------------------------------
# Yandex Calendar (CalDAV, read-only)
# ---------------------------------------------------------------------------

class YandexConnectBody(BaseModel):
    username: str = Field(min_length=3, max_length=200, description="Логин Яндекса (например, user@yandex.ru)")
    app_password: str = Field(min_length=8, max_length=200, description="Пароль приложения для CalDAV")


def _yandex_status_payload(connector: Connector | None) -> dict:
    if connector is None or not connector.credentials_encrypted:
        return {"status": "disconnected", "username": None, "last_sync_at": None, "last_error": None}
    return {
        "status": connector.status.value,
        "username": (connector.metadata_ or {}).get("username"),
        "last_sync_at": connector.last_sync_at.isoformat() if connector.last_sync_at else None,
        "last_error": connector.last_error,
    }


@router.get("/connectors/yandex/status")
async def yandex_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from lumi.connectors.yandex.caldav_client import get_yandex_connector_row

    connector = await get_yandex_connector_row(session, user)
    return _yandex_status_payload(connector)


@router.post("/connectors/yandex/connect")
async def yandex_connect(
    payload: YandexConnectBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from lumi.connectors.yandex.caldav_client import (
        YandexCalendarConnector,
        save_yandex_credentials,
    )

    client = YandexCalendarConnector(payload.username.strip(), payload.app_password.strip())
    try:
        calendars = await client.verify()
    except Exception as exc:  # noqa: BLE001 — surface a calm, actionable error
        raise HTTPException(
            status_code=422,
            detail="yandex_auth_failed",
        ) from exc
    connector = await save_yandex_credentials(
        session, user, username=payload.username.strip(), app_password=payload.app_password.strip()
    )
    await AutomationService(session).ensure_system_calendar_sync(user)
    await AuditService(session).log(
        user_id=user.id, actor="user", entity_type="connector",
        entity_id=connector.id, action="connected",
        details={"type": "yandex", "calendars": calendars},
    )
    await RealtimeEventService(session).emit(
        user_id=user.id,
        topics=["settings", "calendar"],
        event_type="connector.connected",
        payload={"type": "yandex"},
    )
    # First sync starts immediately — the user should see events without extra clicks.
    from lumi.api.run_helper import start_background_run

    run = await start_background_run(session, user, "calendar_sync", notify=False)
    return {**_yandex_status_payload(connector), "calendars": calendars, "run_id": run["run_id"]}


@router.post("/connectors/yandex/disconnect")
async def yandex_disconnect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from lumi.connectors.yandex.caldav_client import get_yandex_connector_row

    connector = await get_yandex_connector_row(session, user)
    if connector is not None:
        connector.credentials_encrypted = None
        connector.status = ConnectorStatus.DISCONNECTED
        connector.scopes = []
        connector.metadata_ = {}
    await AuditService(session).log(
        user_id=user.id, actor="user", entity_type="connector",
        action="disconnected", details={"type": "yandex"},
    )
    await RealtimeEventService(session).emit(
        user_id=user.id,
        topics=["settings", "calendar"],
        event_type="connector.disconnected",
        payload={"type": "yandex"},
    )
    return {"ok": True}
