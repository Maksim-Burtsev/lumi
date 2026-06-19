import pytest
from pydantic import ValidationError

from lumi.api.routes.me import SettingsPatch, patch_settings
from lumi.i18n import (
    DEFAULT_APP_LOCALE,
    DEFAULT_REPLY_LANGUAGE_MODE,
    DEFAULT_TIME_FORMAT,
    normalize_app_locale,
    normalize_reply_language,
)
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


def test_default_time_format_is_automatic():
    assert DEFAULT_TIME_FORMAT == "auto"


def test_normalize_app_locale_supports_only_english_and_russian():
    assert normalize_app_locale("en-US") == "en"
    assert normalize_app_locale("ru-RU") == "ru"
    assert normalize_app_locale("es") == DEFAULT_APP_LOCALE
    assert normalize_app_locale(None) == DEFAULT_APP_LOCALE


def test_normalize_reply_language_keeps_detected_language_for_auto_mode():
    assert normalize_reply_language("en-US") == "en"
    assert normalize_reply_language("ru") == "ru"
    assert normalize_reply_language("es-MX") == "es"
    assert normalize_reply_language("other") == DEFAULT_APP_LOCALE


async def test_new_user_locale_comes_from_telegram_or_defaults_to_english(db_session):
    service = UserService(db_session)

    english = await service.ensure_user(777001, language_code="en-US")
    russian = await service.ensure_user(777002, language_code="ru")
    unsupported = await service.ensure_user(777003, language_code="es")
    missing = await service.ensure_user(777004)

    assert english.language_code == "en-US"
    assert english.locale == "en"
    assert english.settings["locale_source"] == "telegram"
    assert english.settings["reply_language_mode"] == DEFAULT_REPLY_LANGUAGE_MODE
    assert english.settings["time_format"] == DEFAULT_TIME_FORMAT
    assert russian.locale == "ru"
    assert unsupported.locale == "en"
    assert missing.locale == "en"


async def test_telegram_language_refreshes_locale_until_manual_override(db_session):
    service = UserService(db_session)
    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="ru")
    assert user.locale == "ru"

    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="en-US")
    assert user.language_code == "en-US"
    assert user.locale == "en"

    user.locale = "ru"
    user.settings = {**user.settings, "locale_source": "manual"}
    await db_session.flush()

    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="en-US")
    assert user.language_code == "en-US"
    assert user.locale == "ru"
    assert user.settings["locale_source"] == "manual"


async def test_patch_settings_validates_locale_and_reply_mode(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID, language_code="en-US")

    response = await patch_settings(
        SettingsPatch(locale="ru", reply_language_mode="app_locale"),
        user=user,
        session=db_session,
    )

    assert response["user"]["locale"] == "ru"
    assert response["user"]["settings"]["locale_source"] == "manual"
    assert response["user"]["settings"]["reply_language_mode"] == "app_locale"

    with pytest.raises(ValidationError):
        SettingsPatch(locale="es")

    with pytest.raises(ValidationError):
        SettingsPatch(reply_language_mode="always")
