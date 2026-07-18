"""User planning rhythm settings used by calendar/task suggestions."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from typing import Any

from lumi.utils.time import get_zone

DEFAULT_PLANNING_SETTINGS: dict[str, Any] = {
    "work_days": [0, 1, 2, 3, 4],
    "work_hours": {"start": "09:00", "end": "19:00"},
    "quiet_hours": {"start": "21:00", "end": "09:00"},
    "proactive_level": "balanced",
    "micro_slots_enabled": True,
    "micro_slots": {"min_minutes": 5},
    "auto_enrich_tasks": True,
    "suggestion_notifications": "important",
}

_TIME_RE = re.compile(r"^[0-9]{2}:[0-9]{2}$")
_PROACTIVE_LEVELS = {"calm", "balanced", "active"}
_NOTIFICATION_LEVELS = {"important", "none", "all"}


def _time_value(value: object, fallback: str) -> str:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        return fallback
    hour, minute = value.split(":", 1)
    if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
        return value
    return fallback


def _time_parts(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def _strict_time_value(value: object) -> str:
    if not isinstance(value, str) or _time_value(value, "") != value:
        raise ValueError("invalid_work_hours")
    return value


def _bool_value(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _string_choice(value: object, choices: set[str], fallback: str) -> str:
    return value if isinstance(value, str) and value in choices else fallback


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_planning_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict((settings or {}).get("planning") or {})
    defaults = DEFAULT_PLANNING_SETTINGS

    work_days = list(dict.fromkeys(
        day for day in raw.get("work_days", defaults["work_days"])
        if type(day) is int and 0 <= day <= 6
    ))
    if not work_days:
        work_days = list(defaults["work_days"])

    raw_work = _dict_value(raw.get("work_hours"))
    raw_quiet = _dict_value(raw.get("quiet_hours"))
    raw_micro = _dict_value(raw.get("micro_slots"))

    micro_min = raw_micro.get("min_minutes", defaults["micro_slots"]["min_minutes"])
    if not isinstance(micro_min, int):
        micro_min = defaults["micro_slots"]["min_minutes"]

    work_start = _time_value(raw_work.get("start"), defaults["work_hours"]["start"])
    work_end = _time_value(raw_work.get("end"), defaults["work_hours"]["end"])
    if _time_parts(work_start) >= _time_parts(work_end):
        work_start = defaults["work_hours"]["start"]
        work_end = defaults["work_hours"]["end"]

    return {
        "work_days": work_days,
        "work_hours": {
            "start": work_start,
            "end": work_end,
        },
        "quiet_hours": {
            "start": _time_value(raw_quiet.get("start"), defaults["quiet_hours"]["start"]),
            "end": _time_value(raw_quiet.get("end"), defaults["quiet_hours"]["end"]),
        },
        "proactive_level": _string_choice(raw.get("proactive_level"), _PROACTIVE_LEVELS, defaults["proactive_level"]),
        "micro_slots_enabled": _bool_value(raw.get("micro_slots_enabled"), defaults["micro_slots_enabled"]),
        "micro_slots": {"min_minutes": max(5, min(micro_min, 60))},
        "auto_enrich_tasks": _bool_value(raw.get("auto_enrich_tasks"), defaults["auto_enrich_tasks"]),
        "suggestion_notifications": _string_choice(
            raw.get("suggestion_notifications"),
            _NOTIFICATION_LEVELS,
            defaults["suggestion_notifications"],
        ),
    }


def merge_planning_settings(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    if "planning" not in patch:
        return merged
    planning_patch = patch.get("planning")
    if not isinstance(planning_patch, dict):
        raise ValueError("invalid_planning_settings")

    current = normalize_planning_settings(merged)
    next_planning = {**current, **planning_patch}
    for key in ("work_hours", "quiet_hours", "micro_slots"):
        if key not in planning_patch:
            continue
        nested_patch = planning_patch[key]
        if not isinstance(nested_patch, dict):
            raise ValueError("invalid_work_hours" if key == "work_hours" else "invalid_planning_settings")
        next_planning[key] = {**current[key], **nested_patch}

    if "work_days" in planning_patch:
        work_days = planning_patch["work_days"]
        if (
            not isinstance(work_days, list)
            or not work_days
            or any(type(day) is not int or not 0 <= day <= 6 for day in work_days)
            or len(set(work_days)) != len(work_days)
        ):
            raise ValueError("invalid_work_days")

    if "work_hours" in planning_patch:
        work_hours = next_planning["work_hours"]
        start = _strict_time_value(work_hours.get("start"))
        end = _strict_time_value(work_hours.get("end"))
        if _time_parts(start) >= _time_parts(end):
            raise ValueError("invalid_work_hours")

    merged["planning"] = normalize_planning_settings({"planning": next_planning})
    return merged


def planning_work_window(
    settings: dict[str, Any] | None,
    day: datetime,
    timezone: str,
) -> tuple[datetime, datetime] | None:
    """Return the user's local work window as a safe UTC interval."""
    planning = normalize_planning_settings(settings)
    zone = get_zone(timezone)
    local_day = day.astimezone(zone) if day.tzinfo else day.replace(tzinfo=zone)
    if local_day.weekday() not in planning["work_days"]:
        return None

    start_hour, start_minute = _time_parts(planning["work_hours"]["start"])
    end_hour, end_minute = _time_parts(planning["work_hours"]["end"])
    start_local = datetime.combine(
        local_day.date(),
        time(start_hour, start_minute),
        tzinfo=zone,
    )
    end_local = datetime.combine(
        local_day.date(),
        time(end_hour, end_minute),
        tzinfo=zone,
    )
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    if (
        start_utc.astimezone(zone).replace(tzinfo=None) != start_local.replace(tzinfo=None)
        or end_utc.astimezone(zone).replace(tzinfo=None) != end_local.replace(tzinfo=None)
        or end_utc <= start_utc
    ):
        return None
    return start_utc, end_utc
