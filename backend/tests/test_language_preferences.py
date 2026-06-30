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


def test_normalize_app_locale_always_uses_english_for_interface():
    assert normalize_app_locale("en-US") == "en"
    assert normalize_app_locale("ru-RU") == DEFAULT_APP_LOCALE
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
    italian = await service.ensure_user(777005, language_code="it")
    unsupported = await service.ensure_user(777003, language_code="es")
    missing = await service.ensure_user(777004)

    assert english.language_code == "en-US"
    assert english.locale == "en"
    assert english.settings["locale_source"] == "telegram"
    assert english.settings["reply_language_mode"] == DEFAULT_REPLY_LANGUAGE_MODE
    assert english.settings["reply_language"] == DEFAULT_APP_LOCALE
    assert english.settings["time_format"] == DEFAULT_TIME_FORMAT
    assert russian.language_code == "ru"
    assert russian.locale == "en"
    assert italian.language_code == "it"
    assert italian.locale == "en"
    assert unsupported.locale == "en"
    assert missing.locale == "en"


async def test_telegram_language_refresh_keeps_interface_locale_english(db_session):
    service = UserService(db_session)
    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="ru")
    assert user.locale == "en"

    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="it")
    assert user.language_code == "it"
    assert user.locale == "en"

    user.locale = "ru"
    user.settings = {**user.settings, "locale_source": "manual"}
    await db_session.flush()

    user = await service.ensure_user(TEST_TELEGRAM_ID, language_code="es")
    assert user.language_code == "es"
    assert user.locale == "en"
    assert user.settings["locale_source"] == "telegram"


async def test_patch_settings_rejects_interface_and_reply_language_fields(db_session):
    user = await UserService(db_session).ensure_user(TEST_TELEGRAM_ID, language_code="en-US")

    user.locale = "ru"
    user.settings = {
        **user.settings,
        "locale_source": "manual",
        "reply_language_mode": "fixed",
        "reply_language": "it",
    }
    await db_session.flush()

    response = await patch_settings(SettingsPatch(time_format="24h"), user=user, session=db_session)

    assert response["user"]["locale"] == "en"
    assert response["user"]["settings"]["locale_source"] == "telegram"
    assert response["user"]["settings"]["reply_language_mode"] == "auto"
    assert response["user"]["settings"]["reply_language"] == "en"

    with pytest.raises(ValidationError):
        SettingsPatch(locale="ru")

    with pytest.raises(ValidationError):
        SettingsPatch(reply_language_mode="fixed")
