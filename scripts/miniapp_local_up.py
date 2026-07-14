#!/usr/bin/env python3
"""Build and expose the local Telegram Mini App with a fresh tunnel."""

from __future__ import annotations

import json
import os
import re
import shutil
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TUNNEL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True)


def compose_project_name() -> str:
    return os.environ.get("COMPOSE_PROJECT_NAME", "").strip() or "lumi"


def local_api_port() -> str:
    return os.environ.get("LUMI_API_PORT", "").strip() or "8000"


def tunnel_session_name() -> str:
    return os.environ.get("LUMI_TUNNEL_SESSION", "").strip() or f"{compose_project_name()}-cloudflared"


def tunnel_log_path() -> Path:
    value = os.environ.get("LUMI_TUNNEL_LOG", "").strip()
    if value:
        return Path(value)
    return Path(f"/tmp/{tunnel_session_name()}.log")


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
    session = tunnel_session_name()
    log_path = tunnel_log_path()
    run(["tmux", "kill-session", "-t", session], check=False)
    log_path.unlink(missing_ok=True)
    command = (
        f"cloudflared tunnel --url http://localhost:{local_api_port()} --no-autoupdate "
        f">{shlex.quote(str(log_path))} 2>&1"
    )
    run(["tmux", "new-session", "-d", "-s", session, command])

    for _ in range(45):
        if log_path.exists():
            match = TUNNEL_RE.search(log_path.read_text(errors="ignore"))
            if match:
                return match.group(0)
        time.sleep(1)
    tail = log_path.read_text(errors="ignore")[-2000:] if log_path.exists() else ""
    raise SystemExit(f"Tunnel URL was not created. Log tail:\n{tail}")


def http_get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def wait_for_json(url: str, *, attempts: int = 12, delay_seconds: int = 5) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return http_get_json(url)
        except Exception as exc:  # noqa: BLE001 — quick tunnel DNS can lag behind log output
            last_error = exc
            time.sleep(delay_seconds)
    raise SystemExit(f"{url} did not become reachable: {last_error}") from last_error


def wait_for_http_ok(url: str, *, attempts: int = 12, delay_seconds: int = 5) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                if response.status == 200:
                    return
                last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001 — quick tunnel DNS can lag behind log output
            last_error = exc
        time.sleep(delay_seconds)
    raise SystemExit(f"{url} did not become reachable: {last_error}") from last_error


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
    run(["docker", "compose", "run", "--rm", "api", "alembic", "upgrade", "head"])
    tunnel_url = start_tunnel()
    set_env_values({"APP_PUBLIC_URL": tunnel_url, "FRONTEND_PUBLIC_PATH": "/app/"})
    run(["docker", "compose", "up", "-d", "--force-recreate", "api", "bot"])

    expected_mini_app_url = tunnel_url.rstrip("/") + "/app/"
    health = wait_for_json(tunnel_url.rstrip("/") + "/health")
    print("health:", health)
    wait_for_http_ok(expected_mini_app_url)
    verify_telegram_menu(expected_mini_app_url)
    print(f"Mini App: {expected_mini_app_url}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
