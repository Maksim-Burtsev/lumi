from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from lumi.connectors.google import auth


def test_web_oauth_disables_incremental_legacy_grants(monkeypatch):
    captured: dict = {}

    class FakeFlow:
        def authorization_url(self, **kwargs):
            captured.update(kwargs)
            return "https://accounts.example/authorize", "state"

    monkeypatch.setattr(auth, "_build_flow", lambda: FakeFlow())

    assert auth.build_auth_url("single-use-state") == "https://accounts.example/authorize"
    assert captured == {
        "access_type": "offline",
        "include_granted_scopes": "false",
        "prompt": "consent",
        "state": "single-use-state",
    }


async def test_connection_status_filters_legacy_gmail_grant(monkeypatch):
    calendar_scopes = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    async def fake_load_credentials():
        return SimpleNamespace(
            scopes=["https://www.googleapis.com/auth/gmail.readonly", *calendar_scopes]
        )

    monkeypatch.setattr(auth, "token_file_exists", lambda: True)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(google_scopes=calendar_scopes))
    monkeypatch.setattr(auth, "load_credentials", fake_load_credentials)

    status = await auth.connection_status()

    assert status == {
        "status": "connected",
        "scopes": calendar_scopes,
        "calendar_available": True,
        "last_error": None,
    }


def test_host_oauth_script_requests_calendar_scopes_only():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "google_auth_local.py"
    spec = importlib.util.spec_from_file_location("google_auth_local", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.SCOPES == [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]
