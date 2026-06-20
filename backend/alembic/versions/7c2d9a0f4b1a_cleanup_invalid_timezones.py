"""cleanup invalid timezones

Revision ID: 7c2d9a0f4b1a
Revises: b8f6d2a91c4e
Create Date: 2026-06-17 12:45:00.000000

"""
from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alembic import op
from croniter import croniter
from sqlalchemy import text
from sqlalchemy.engine import Connection

revision: str = "7c2d9a0f4b1a"
down_revision: str | None = "b8f6d2a91c4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TZ = os.environ.get("DEFAULT_TIMEZONE", "Europe/Moscow")
_EXCLUDED_TZ_PREFIXES = ("posix/", "right/")
_EXCLUDED_TZ_NAMES = {"Factory", "localtime"}


def _valid_timezone(tz_name: str | None) -> bool:
    candidate = (tz_name or "").strip()
    if (
        not candidate
        or candidate.startswith(_EXCLUDED_TZ_PREFIXES)
        or candidate in _EXCLUDED_TZ_NAMES
    ):
        return False
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return False
    return True


def _default_timezone() -> str:
    return DEFAULT_TZ if _valid_timezone(DEFAULT_TZ) else "Europe/Moscow"


def _next_run_at(cron_expression: str, timezone: str) -> datetime | None:
    if not croniter.is_valid(cron_expression):
        return None
    zone = ZoneInfo(timezone)
    base = datetime.now(UTC).astimezone(zone)
    next_local: datetime = croniter(cron_expression, base).get_next(datetime)
    return next_local.astimezone(UTC)


def cleanup_invalid_timezones(connection: Connection) -> None:
    default_tz = _default_timezone()
    user_timezones: dict[object, str] = {}
    users = connection.execute(text("select id, timezone from users")).mappings().all()
    for row in users:
        timezone = row["timezone"] if _valid_timezone(row["timezone"]) else default_tz
        user_timezones[row["id"]] = timezone
        if timezone != row["timezone"]:
            connection.execute(
                text("update users set timezone = :timezone where id = :id"),
                {"timezone": timezone, "id": row["id"]},
            )

    tasks = connection.execute(
        text(
            "select id, user_id, timezone, cron_expression, enabled, config "
            "from scheduled_tasks"
        )
    ).mappings().all()
    for row in tasks:
        if _valid_timezone(row["timezone"]):
            continue
        timezone = user_timezones.get(row["user_id"], default_tz)
        params = {"timezone": timezone, "id": row["id"]}
        config = row["config"] or {}
        if row["enabled"] and not config.get("one_time"):
            next_run_at = _next_run_at(row["cron_expression"], timezone)
            if next_run_at is not None:
                params["next_run_at"] = next_run_at
                connection.execute(
                    text(
                        "update scheduled_tasks "
                        "set timezone = :timezone, next_run_at = :next_run_at "
                        "where id = :id"
                    ),
                    params,
                )
                continue
        connection.execute(
            text("update scheduled_tasks set timezone = :timezone where id = :id"),
            params,
        )

    events = connection.execute(
        text("select id, user_id, timezone from calendar_events")
    ).mappings().all()
    for row in events:
        if _valid_timezone(row["timezone"]):
            continue
        connection.execute(
            text("update calendar_events set timezone = :timezone where id = :id"),
            {"timezone": user_timezones.get(row["user_id"], default_tz), "id": row["id"]},
        )


def upgrade() -> None:
    cleanup_invalid_timezones(op.get_bind())


def downgrade() -> None:
    pass
