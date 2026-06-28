from lumi.services.planning_settings import normalize_planning_settings


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
            "work_days": [0, 2, 7, -1],
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
