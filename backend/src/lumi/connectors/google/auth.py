"""Google OAuth credential management.

MVP flow: `make google-auth-local` runs an InstalledAppFlow in the host browser
and saves the token JSON to ./data/secrets/google_token.json (mounted into
containers). Backend reads/refreshes that token. No web OAuth needed locally.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from lumi.config import get_settings
from lumi.logging import get_logger

log = get_logger(__name__)


class GoogleNotConnectedError(Exception):
    """Raised when Google credentials are absent or unusable."""


def _token_path() -> Path | None:
    settings = get_settings()
    if not settings.google_oauth_token_file:
        return None
    return Path(settings.google_oauth_token_file)


def token_file_exists() -> bool:
    path = _token_path()
    return bool(path and path.exists())


def _load_credentials_sync():  # -> google.oauth2.credentials.Credentials
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    settings = get_settings()
    path = _token_path()
    if not path or not path.exists():
        raise GoogleNotConnectedError("Google token file not found — run `make google-auth-local`")

    try:
        creds = Credentials.from_authorized_user_file(str(path), settings.google_scopes)
    except (ValueError, json.JSONDecodeError) as exc:
        raise GoogleNotConnectedError(f"Google token file is unreadable: {exc}") from exc

    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            raise GoogleNotConnectedError(f"Google token refresh failed: {exc}") from exc
        try:
            path.write_text(creds.to_json())
        except OSError:
            log.warning("could not persist refreshed Google token")
        return creds
    raise GoogleNotConnectedError("Google token expired and cannot be refreshed — reauthorize")


async def load_credentials():
    """Async wrapper: returns valid Google credentials or raises GoogleNotConnectedError."""
    return await asyncio.to_thread(_load_credentials_sync)


async def connection_status() -> dict:
    """Cheap status summary for the Settings page."""
    settings = get_settings()
    if not token_file_exists():
        return {
            "status": "disconnected",
            "scopes": [],
            "calendar_available": False,
            "last_error": None,
        }
    try:
        creds = await load_credentials()
        configured_scopes = set(settings.google_scopes)
        scopes = [scope for scope in (creds.scopes or settings.google_scopes) if scope in configured_scopes]
        return {
            "status": "connected",
            "scopes": scopes,
            "calendar_available": any("calendar" in s for s in scopes),
            "last_error": None,
        }
    except GoogleNotConnectedError as exc:
        return {
            "status": "needs_reauth",
            "scopes": [],
            "calendar_available": False,
            "last_error": str(exc),
        }


def disconnect() -> bool:
    """Remove the stored token. Returns True if something was removed."""
    path = _token_path()
    if path and path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Web OAuth (Mini App "connect in one tap" flow)
# ---------------------------------------------------------------------------

def _client_secret_path() -> Path | None:
    settings = get_settings()
    if not settings.google_oauth_client_secret_file:
        return None
    return Path(settings.google_oauth_client_secret_file)


def client_secret_exists() -> bool:
    path = _client_secret_path()
    return bool(path and path.exists())


def redirect_uri() -> str | None:
    settings = get_settings()
    if not settings.app_public_url:
        return None
    return settings.app_public_url.rstrip("/") + "/api/connectors/google/callback"


def _build_flow():
    from google_auth_oauthlib.flow import Flow

    settings = get_settings()
    uri = redirect_uri()
    if uri is None:
        raise GoogleNotConnectedError("APP_PUBLIC_URL не настроен — нужен HTTPS-адрес")
    path = _client_secret_path()
    if path is None or not path.exists():
        raise GoogleNotConnectedError("client_secret.json не найден в data/secrets")
    return Flow.from_client_secrets_file(str(path), scopes=settings.google_scopes,
                                         redirect_uri=uri)


def build_auth_url(state: str) -> str:
    """Authorization URL for the browser redirect. Raises GoogleNotConnectedError."""
    flow = _build_flow()
    url, _ = flow.authorization_url(
        access_type="offline",            # refresh_token for long-lived access
        include_granted_scopes="false",
        prompt="consent",
        state=state,
    )
    return url


def _exchange_code_sync(code: str) -> None:
    flow = _build_flow()
    flow.fetch_token(code=code)
    token_path = _token_path()
    if token_path is None:
        raise GoogleNotConnectedError("GOOGLE_OAUTH_TOKEN_FILE не настроен")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(flow.credentials.to_json())


async def exchange_code(code: str) -> None:
    """Exchange the callback code for tokens and persist them."""
    await asyncio.to_thread(_exchange_code_sync, code)
