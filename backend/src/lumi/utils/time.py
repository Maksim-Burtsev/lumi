"""Timezone helpers. The DB stores UTC; users live in their own timezone."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Europe/Moscow"


def get_zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or DEFAULT_TZ)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TZ)


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_now(tz_name: str | None) -> datetime:
    return datetime.now(get_zone(tz_name))


def local_to_utc(naive_local: datetime, tz_name: str | None) -> datetime:
    """Interpret a naive datetime (e.g. from LLM extraction) as user-local time."""
    if naive_local.tzinfo is not None:
        return naive_local.astimezone(UTC)
    return naive_local.replace(tzinfo=get_zone(tz_name)).astimezone(UTC)


def utc_to_local(dt: datetime, tz_name: str | None) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(get_zone(tz_name))


def local_day_bounds(day: datetime, tz_name: str | None) -> tuple[datetime, datetime]:
    """UTC bounds [start, end) of the user-local calendar day containing ``day``."""
    zone = get_zone(tz_name)
    local = day.astimezone(zone) if day.tzinfo else day.replace(tzinfo=zone)
    start_local = datetime.combine(local.date(), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)


def fmt_local(dt: datetime | None, tz_name: str | None, fmt: str = "%d.%m %H:%M") -> str:
    if dt is None:
        return "—"
    return utc_to_local(dt, tz_name).strftime(fmt)


def greeting_for(dt_local: datetime, locale: str | None = "ru") -> str:
    hour = dt_local.hour
    if str(locale or "").lower().startswith("en"):
        if 5 <= hour < 12:
            return "Good morning"
        if 12 <= hour < 18:
            return "Good afternoon"
        if 18 <= hour < 23:
            return "Good evening"
        return "Good night"
    if 5 <= hour < 12:
        return "Доброе утро"
    if 12 <= hour < 18:
        return "Добрый день"
    if 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"
