"""User planning rhythm settings used by calendar/task suggestions."""

from __future__ import annotations

import re
from typing import Any

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

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_PROACTIVE_LEVELS = {"calm", "balanced", "active"}
_NOTIFICATION_LEVELS = {"important", "none", "all"}


def _time_value(value: object, fallback: str) -> str:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        return fallback
    hour, minute = value.split(":", 1)
    if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
        return value
    return fallback


def _bool_value(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _string_choice(value: object, choices: set[str], fallback: str) -> str:
    return value if isinstance(value, str) and value in choices else fallback


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_planning_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict((settings or {}).get("planning") or {})
    defaults = DEFAULT_PLANNING_SETTINGS

    work_days = [
        day for day in raw.get("work_days", defaults["work_days"])
        if isinstance(day, int) and 0 <= day <= 6
    ]
    if not work_days:
        work_days = list(defaults["work_days"])

    raw_work = _dict_value(raw.get("work_hours"))
    raw_quiet = _dict_value(raw.get("quiet_hours"))
    raw_micro = _dict_value(raw.get("micro_slots"))

    micro_min = raw_micro.get("min_minutes", defaults["micro_slots"]["min_minutes"])
    if not isinstance(micro_min, int):
        micro_min = defaults["micro_slots"]["min_minutes"]

    return {
        "work_days": work_days,
        "work_hours": {
            "start": _time_value(raw_work.get("start"), defaults["work_hours"]["start"]),
            "end": _time_value(raw_work.get("end"), defaults["work_hours"]["end"]),
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
    merged["planning"] = normalize_planning_settings({"planning": patch.get("planning")})
    return merged
