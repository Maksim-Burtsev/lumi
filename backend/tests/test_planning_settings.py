from datetime import UTC, datetime, timedelta

import pytest

from lumi.services.planning_settings import (
    merge_planning_settings,
    normalize_planning_settings,
    planning_work_window,
)
from lumi.utils.time import get_zone


def test_planning_settings_default_to_premium_low_noise_rhythm():
    settings = normalize_planning_settings({})

    assert settings["work_days"] == [0, 1, 2, 3, 4]
    assert settings["work_hours"] == {"start": "09:00", "end": "19:00"}
    assert settings["quiet_hours"] == {"start": "21:00", "end": "09:00"}
    assert settings["proactive_level"] == "balanced"
    assert settings["micro_slots_enabled"] is True
    assert settings["micro_slots"]["min_minutes"] == 5
    assert settings["auto_enrich_tasks"] is True
    assert settings["suggestion_notifications"] == "important"


def test_planning_settings_keep_safe_values_and_clamp_micro_slot_minimum():
    settings = normalize_planning_settings({
        "planning": {
            "work_days": [0, 2, 2, 7, -1],
            "work_hours": {"start": "10:30", "end": "18:15"},
            "quiet_hours": {"start": "22:00", "end": "08:30"},
            "proactive_level": "active",
            "micro_slots_enabled": False,
            "micro_slots": {"min_minutes": 1},
            "auto_enrich_tasks": False,
            "suggestion_notifications": "none",
        }
    })

    assert settings["work_days"] == [0, 2]
    assert settings["work_hours"] == {"start": "10:30", "end": "18:15"}
    assert settings["quiet_hours"] == {"start": "22:00", "end": "08:30"}
    assert settings["proactive_level"] == "active"
    assert settings["micro_slots_enabled"] is False
    assert settings["micro_slots"]["min_minutes"] == 5
    assert settings["auto_enrich_tasks"] is False
    assert settings["suggestion_notifications"] == "none"


def test_planning_settings_deep_merge_partial_work_hours_without_resetting():
    existing = {
        "theme_mode": "dark",
        "planning": {
            "work_days": [1, 2, 3],
            "work_hours": {"start": "08:30", "end": "17:45"},
            "quiet_hours": {"start": "22:30", "end": "07:15"},
            "proactive_level": "active",
            "micro_slots_enabled": False,
            "micro_slots": {"min_minutes": 20},
            "auto_enrich_tasks": False,
            "suggestion_notifications": "none",
        },
    }

    merged = merge_planning_settings(
        existing,
        {"planning": {"work_hours": {"start": "09:15"}}},
    )

    assert merged["theme_mode"] == "dark"
    assert merged["planning"] == {
        **existing["planning"],
        "work_hours": {"start": "09:15", "end": "17:45"},
    }


@pytest.mark.parametrize(
    ("planning_patch", "error"),
    [
        ({"work_days": []}, "invalid_work_days"),
        ({"work_days": [0, 0]}, "invalid_work_days"),
        ({"work_days": [0, 7]}, "invalid_work_days"),
        ({"work_days": [True, 1]}, "invalid_work_days"),
        ({"work_hours": {"start": "9:00"}}, "invalid_work_hours"),
        ({"work_hours": {"start": "19:00", "end": "09:00"}}, "invalid_work_hours"),
        ({"work_hours": None}, "invalid_work_hours"),
    ],
)
def test_planning_settings_reject_invalid_patches(planning_patch, error):
    with pytest.raises(ValueError, match=f"^{error}$"):
        merge_planning_settings({}, {"planning": planning_patch})


def test_planning_work_window_uses_local_weekday_and_minute_precision():
    timezone = "Pacific/Chatham"
    window = planning_work_window(
        {
            "planning": {
                "work_days": [2],
                "work_hours": {"start": "09:15", "end": "17:45"},
            }
        },
        datetime(2026, 7, 15, 12),
        timezone,
    )

    assert window is not None
    start, end = window
    assert start.tzinfo is UTC
    assert end.tzinfo is UTC
    assert start.astimezone(get_zone(timezone)).strftime("%Y-%m-%d %H:%M") == "2026-07-15 09:15"
    assert end.astimezone(get_zone(timezone)).strftime("%Y-%m-%d %H:%M") == "2026-07-15 17:45"

    assert planning_work_window(
        {"planning": {"work_days": [1]}},
        datetime(2026, 7, 15, 12),
        timezone,
    ) is None


def test_planning_work_window_roundtrips_dst_boundaries_and_rejects_gap():
    timezone = "America/New_York"
    settings = {
        "planning": {
            "work_days": [6],
            "work_hours": {"start": "01:30", "end": "04:30"},
        }
    }

    spring = planning_work_window(settings, datetime(2027, 3, 14, 12), timezone)
    fall = planning_work_window(
        {
            "planning": {
                "work_days": [6],
                "work_hours": {"start": "00:30", "end": "03:30"},
            }
        },
        datetime(2027, 11, 7, 12),
        timezone,
    )

    assert spring is not None
    assert spring[1] - spring[0] == timedelta(hours=2)
    assert fall is not None
    assert fall[1] - fall[0] == timedelta(hours=4)
    assert planning_work_window(
        {
            "planning": {
                "work_days": [6],
                "work_hours": {"start": "02:30", "end": "04:30"},
            }
        },
        datetime(2027, 3, 14, 12),
        timezone,
    ) is None
