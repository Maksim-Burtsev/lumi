#!/usr/bin/env python3
"""Build and expose the local Telegram Mini App with a fresh tunnel."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TUNNEL_SESSION = "lumi-cloudflared"
TUNNEL_LOG = Path("/tmp/lumi-cloudflared.log")
TUNNEL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True)


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        raise SystemExit("Missing .env. Run: make setup")
    for raw_line in ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def set_env_values(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text().splitlines()
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            if key in updates:
                next_lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        next_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(next_lines) + "\n")


def require_tools() -> None:
    missing = [tool for tool in ("docker", "tmux", "cloudflared") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"Missing required tools: {', '.join(missing)}")


def start_tunnel() -> str:
    run(["tmux", "kill-session", "-t", TUNNEL_SESSION], check=False)
    TUNNEL_LOG.unlink(missing_ok=True)
    command = f"cloudflared tunnel --url http://localhost:8000 --no-autoupdate >{TUNNEL_LOG} 2>&1"
    run(["tmux", "new-session", "-d", "-s", TUNNEL_SESSION, command])

    for _ in range(45):
        if TUNNEL_LOG.exists():
            match = TUNNEL_RE.search(TUNNEL_LOG.read_text(errors="ignore"))
            if match:
                return match.group(0)
        time.sleep(1)
    tail = TUNNEL_LOG.read_text(errors="ignore")[-2000:] if TUNNEL_LOG.exists() else ""
    raise SystemExit(f"Tunnel URL was not created. Log tail:\n{tail}")


def http_get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def verify_telegram_menu(expected_url: str) -> None:
    env = read_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    user_ids = [item.strip() for item in env.get("ALLOWED_TELEGRAM_USER_IDS", "").split(",") if item.strip()]
    if not token or not user_ids:
        print("Skipping Telegram menu verification: TELEGRAM_BOT_TOKEN/ALLOWED_TELEGRAM_USER_IDS missing")
        return

    base = f"https://api.telegram.org/bot{token}/getChatMenuButton"
    checks = [("default", base)]
    checks.extend(
        (f"chat:{user_id}", base + "?" + urllib.parse.urlencode({"chat_id": user_id}))
        for user_id in user_ids
    )
    mismatches: list[str] = []
    for label, url in checks:
        data = http_get_json(url)
        web_app_url = (
            data.get("result", {})
            if isinstance(data.get("result"), dict)
            else {}
        ).get("web_app", {})
        actual_url = web_app_url.get("url") if isinstance(web_app_url, dict) else None
        print(f"{label} menu: {actual_url}")
        if actual_url != expected_url:
            mismatches.append(f"{label}: {actual_url}")
    if mismatches:
        raise SystemExit("Telegram menu URL mismatch:\n" + "\n".join(mismatches))


def main() -> None:
    require_tools()
    env = read_env()
    if not env.get("TELEGRAM_BOT_TOKEN"):
        raise SystemExit("TELEGRAM_BOT_TOKEN is empty in .env")
    if not env.get("ALLOWED_TELEGRAM_USER_IDS"):
        raise SystemExit("ALLOWED_TELEGRAM_USER_IDS is empty in .env")

    run(["make", "frontend-build"])
    run(["docker", "compose", "up", "-d", "--build"])
    tunnel_url = start_tunnel()
    set_env_values({"APP_PUBLIC_URL": tunnel_url, "FRONTEND_PUBLIC_PATH": "/app/"})
    run(["docker", "compose", "up", "-d", "--force-recreate", "api", "bot"])

    expected_mini_app_url = tunnel_url.rstrip("/") + "/app/"
    health = http_get_json(tunnel_url.rstrip("/") + "/health")
    print("health:", health)
    with urllib.request.urlopen(expected_mini_app_url, timeout=15) as response:
        if response.status != 200:
            raise SystemExit(f"Mini App returned HTTP {response.status}")
    verify_telegram_menu(expected_mini_app_url)
    print(f"Mini App: {expected_mini_app_url}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
