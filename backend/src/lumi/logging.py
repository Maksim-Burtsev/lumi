"""Structured JSON-lines logging with correlation ids."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Correlation ids propagated through async call chains.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
agent_run_id_var: ContextVar[str | None] = ContextVar("agent_run_id", default=None)
telegram_update_id_var: ContextVar[int | None] = ContextVar("telegram_update_id", default=None)

_SECRET_HINTS = ("token", "key", "secret", "password", "authorization", "credential")


def redact_secret(value: str) -> str:
    """Show only a safe prefix of a secret for logs."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-2:]}"


def _scrub(obj: Any) -> Any:
    """Recursively redact values whose keys look secret-ish."""
    if isinstance(obj, dict):
        return {
            k: ("***" if any(h in str(k).lower() for h in _SECRET_HINTS) else _scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        if agent_run_id := agent_run_id_var.get():
            payload["agent_run_id"] = agent_run_id
        if update_id := telegram_update_id_var.get():
            payload["telegram_update_id"] = update_id
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(_scrub(extra))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class LumiLogger(logging.LoggerAdapter):
    """Logger adapter that routes kwargs into structured extra fields."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, dict[str, Any]]:
        extra_fields = kwargs.pop("fields", None) or {}
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Quieten noisy libraries
    for noisy in ("httpx", "httpcore", "aiogram.event", "googleapiclient"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> LumiLogger:
    return LumiLogger(logging.getLogger(name), {})
