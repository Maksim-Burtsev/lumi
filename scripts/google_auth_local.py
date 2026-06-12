#!/usr/bin/env python3
"""Local Google OAuth flow (runs on the HOST, not in Docker).

Usage:
  1. Create an OAuth client (Desktop app) in Google Cloud Console,
     enable Gmail API + Google Calendar API, add yourself as a test user.
  2. Save the client secret JSON to ./data/secrets/google_client_secret.json
  3. pip install google-auth-oauthlib   (or: uv pip install google-auth-oauthlib)
  4. python3 scripts/google_auth_local.py
  5. A browser opens; grant access. Token lands in ./data/secrets/google_token.json
     (mounted into containers at /app/data/secrets/google_token.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_SECRET = REPO_ROOT / "data" / "secrets" / "google_client_secret.json"
TOKEN_PATH = REPO_ROOT / "data" / "secrets" / "google_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def main() -> int:
    if not CLIENT_SECRET.exists():
        print(f"Не найден client secret: {CLIENT_SECRET}")
        print("Скачай OAuth client (Desktop app) из Google Cloud Console и положи туда.")
        return 1
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Не установлен google-auth-oauthlib. Поставь: pip install google-auth-oauthlib")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"\nГотово. Токен сохранен: {TOKEN_PATH}")
    print("Контейнеры видят его автоматически (data/secrets смонтирован).")
    print("Проверь статус: Mini App → Settings → Google.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
