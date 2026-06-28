"""Language preferences shared by bot, API, and assistant runtime."""

from __future__ import annotations

from typing import Literal

DEFAULT_APP_LOCALE = "en"
SUPPORTED_APP_LOCALES = ("en", "ru")
DEFAULT_REPLY_LANGUAGE_MODE = "auto"
DEFAULT_REPLY_LANGUAGE = "en"
DEFAULT_TIME_FORMAT = "auto"
DEFAULT_THEME_MODE = "telegram"
SUPPORTED_TIME_FORMATS = ("auto", "24h", "12h")
SUPPORTED_THEME_MODES = ("telegram", "light", "dark")
ReplyLanguageMode = Literal["auto", "fixed", "app_locale"]
TimeFormat = Literal["auto", "24h", "12h"]
ThemeMode = Literal["telegram", "light", "dark"]


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
    if value == "fixed":
        return "fixed"
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


def normalize_theme_mode(value: str | None) -> ThemeMode:
    if value == "light":
        return "light"
    if value == "dark":
        return "dark"
    return DEFAULT_THEME_MODE


def validate_time_format(value: str | None) -> TimeFormat:
    if value in SUPPORTED_TIME_FORMATS:
        return value
    supported = ", ".join(SUPPORTED_TIME_FORMATS)
    raise ValueError(f"unsupported time format; expected one of: {supported}")


def validate_theme_mode(value: str | None) -> ThemeMode:
    if value in SUPPORTED_THEME_MODES:
        return value
    supported = ", ".join(SUPPORTED_THEME_MODES)
    raise ValueError(f"unsupported theme mode; expected one of: {supported}")


def ensure_language_settings(settings: dict | None) -> dict:
    merged = dict(settings or {})
    merged.setdefault("locale_source", "telegram")
    merged.setdefault("reply_language_mode", DEFAULT_REPLY_LANGUAGE_MODE)
    merged.setdefault("reply_language", DEFAULT_REPLY_LANGUAGE)
    merged.setdefault("time_format", DEFAULT_TIME_FORMAT)
    merged.setdefault("theme_mode", DEFAULT_THEME_MODE)
    merged["reply_language_mode"] = normalize_reply_language_mode(
        str(merged.get("reply_language_mode") or "")
    )
    merged["reply_language"] = normalize_reply_language(
        str(merged.get("reply_language") or DEFAULT_REPLY_LANGUAGE)
    )
    merged["time_format"] = normalize_time_format(str(merged.get("time_format") or ""))
    merged["theme_mode"] = normalize_theme_mode(str(merged.get("theme_mode") or ""))
    return merged


def app_locale_name(locale: str) -> str:
    locale = normalize_app_locale(locale)
    if locale == "ru":
        return "Russian"
    return "English"


def format_language_settings_reply(
    *,
    app_locale: str,
    reply_language_mode: str,
    reply_language: str | None = None,
    language: str | None,
) -> str:
    mode = normalize_reply_language_mode(reply_language_mode)
    name = app_locale_name(app_locale)
    if mode == "app_locale":
        return f"Language updated: {name}. Replies now use the app language."
    if mode == "fixed":
        return (
            f"Language updated: {name}. "
            f"Replies now use {normalize_reply_language(reply_language or language)}."
        )
    return f"Language updated: {name}. Replies now match each message."
