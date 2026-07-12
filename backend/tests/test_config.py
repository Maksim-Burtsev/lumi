import pytest
from pydantic import ValidationError

from lumi.config import Settings

TELEGRAM_TIMING_FIELDS = (
    "telegram_stream_edit_interval_seconds",
    "telegram_progress_heartbeat_interval_seconds",
    "telegram_chat_action_interval_seconds",
    "telegram_progress_stale_after_seconds",
    "telegram_progress_long_after_seconds",
)


@pytest.mark.parametrize("field_name", TELEGRAM_TIMING_FIELDS)
@pytest.mark.parametrize("value", [0, -1])
def test_telegram_timing_settings_require_positive_values(field_name: str, value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: value})


@pytest.mark.parametrize("field_name", TELEGRAM_TIMING_FIELDS)
@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_telegram_timing_settings_require_finite_values(field_name: str, value: float):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: value})


@pytest.mark.parametrize("value", [256, 4000])
def test_telegram_stream_max_chars_accepts_boundaries(value: int):
    settings = Settings(_env_file=None, telegram_stream_max_chars=value)

    assert settings.telegram_stream_max_chars == value


@pytest.mark.parametrize("value", [255, 4001])
def test_telegram_stream_max_chars_rejects_out_of_range_values(value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_stream_max_chars=value)


def test_telegram_progress_long_threshold_cannot_precede_stale_threshold():
    with pytest.raises(ValidationError, match="must be greater than or equal"):
        Settings(
            _env_file=None,
            telegram_progress_stale_after_seconds=30,
            telegram_progress_long_after_seconds=12,
        )


def test_telegram_progress_thresholds_allow_equal_values():
    settings = Settings(
        _env_file=None,
        telegram_progress_stale_after_seconds=12,
        telegram_progress_long_after_seconds=12,
    )

    assert settings.telegram_progress_stale_after_seconds == 12
    assert settings.telegram_progress_long_after_seconds == 12
