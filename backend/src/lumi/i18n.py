"""Language preferences shared by bot, API, and assistant runtime."""

from __future__ import annotations

from typing import Literal

DEFAULT_APP_LOCALE = "en"
SUPPORTED_APP_LOCALES = ("en", "ru")
DEFAULT_REPLY_LANGUAGE_MODE = "auto"
DEFAULT_TIME_FORMAT = "auto"
SUPPORTED_TIME_FORMATS = ("auto", "24h", "12h")
ReplyLanguageMode = Literal["auto", "app_locale"]
TimeFormat = Literal["auto", "24h", "12h"]


def primary_language_tag(value: str | None) -> str | None:
    if not value:
        return None
    primary = value.replace("_", "-").split("-", 1)[0].strip().lower()
    if not primary or primary == "other":
        return None
    if len(primary) < 2 or len(primary) > 8:
        return None
    if not primary.isalpha():
        return None
    return primary


def normalize_app_locale(value: str | None) -> str:
    primary = primary_language_tag(value)
    return primary if primary in SUPPORTED_APP_LOCALES else DEFAULT_APP_LOCALE


def validate_app_locale(value: str | None) -> str:
    primary = primary_language_tag(value)
    if primary not in SUPPORTED_APP_LOCALES:
        supported = ", ".join(SUPPORTED_APP_LOCALES)
        raise ValueError(f"unsupported locale; expected one of: {supported}")
    return primary


def normalize_reply_language(value: str | None) -> str:
    return primary_language_tag(value) or DEFAULT_APP_LOCALE


def normalize_reply_language_mode(value: str | None) -> ReplyLanguageMode:
    if value == "app_locale":
        return "app_locale"
    return DEFAULT_REPLY_LANGUAGE_MODE


def normalize_time_format(value: str | None) -> TimeFormat:
    if value == "auto":
        return "auto"
    if value == "12h":
        return "12h"
    if value == "24h":
        return "24h"
    return DEFAULT_TIME_FORMAT


def validate_time_format(value: str | None) -> TimeFormat:
    if value in SUPPORTED_TIME_FORMATS:
        return value
    supported = ", ".join(SUPPORTED_TIME_FORMATS)
    raise ValueError(f"unsupported time format; expected one of: {supported}")


def ensure_language_settings(settings: dict | None) -> dict:
    merged = dict(settings or {})
    merged.setdefault("locale_source", "telegram")
    merged.setdefault("reply_language_mode", DEFAULT_REPLY_LANGUAGE_MODE)
    merged.setdefault("time_format", DEFAULT_TIME_FORMAT)
    merged["reply_language_mode"] = normalize_reply_language_mode(
        str(merged.get("reply_language_mode") or "")
    )
    merged["time_format"] = normalize_time_format(str(merged.get("time_format") or ""))
    return merged


def app_locale_name(locale: str, *, language: str | None = None) -> str:
    locale = normalize_app_locale(locale)
    english = normalize_reply_language(language).startswith("en")
    if locale == "ru":
        return "Russian" if english else "русский"
    return "English" if english else "английский"


def format_language_settings_reply(
    *,
    app_locale: str,
    reply_language_mode: str,
    language: str | None,
) -> str:
    english = normalize_reply_language(language).startswith("en")
    mode = normalize_reply_language_mode(reply_language_mode)
    name = app_locale_name(app_locale, language=language)
    if english:
        if mode == "app_locale":
            return f"Language updated: {name}. Replies now use the app language."
        return f"Language updated: {name}. Replies now match each message."
    if mode == "app_locale":
        return f"Язык обновлен: {name}. Ответы теперь на языке приложения."
    return f"Язык обновлен: {name}. Ответы теперь на языке каждого сообщения."
