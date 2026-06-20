"""Timezone helpers. The DB stores UTC; users live in their own timezone."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError, available_timezones

DEFAULT_TZ = "Europe/Moscow"
_EXCLUDED_TZ_PREFIXES = ("posix/", "right/", "Etc/", "SystemV/")
_EXCLUDED_TZ_NAMES = {"Factory", "localtime"}


def _is_selectable_timezone(tz_name: str) -> bool:
    return (
        (tz_name == "UTC" or "/" in tz_name)
        and not tz_name.startswith(_EXCLUDED_TZ_PREFIXES)
        and tz_name not in _EXCLUDED_TZ_NAMES
    )


def _zone_tab_timezones() -> set[str]:
    zones: set[str] = set()
    for root in TZPATH:
        for filename in ("zone1970.tab", "zone.tab"):
            path = Path(root) / filename
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    zones.add(parts[2])
            if zones:
                return zones
    return zones


@lru_cache(maxsize=1)
def selectable_timezone_names() -> tuple[str, ...]:
    source = _zone_tab_timezones() or available_timezones()
    zones = {tz for tz in source if _is_selectable_timezone(tz)}
    zones.add("UTC")
    return tuple(sorted(zones))


def validate_timezone_name(tz_name: str | None) -> str:
    candidate = (tz_name or "").strip()
    if not _is_selectable_timezone(candidate):
        raise ValueError("invalid_timezone")
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid_timezone") from exc
    return candidate


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
