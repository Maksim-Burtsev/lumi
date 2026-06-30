"""Language preferences shared by bot, API, and assistant runtime."""

from __future__ import annotations

from typing import Literal

ReplyLanguageMode = Literal["auto", "fixed", "app_locale"]
TimeFormat = Literal["auto", "24h", "12h"]
ThemeMode = Literal["telegram", "light", "dark"]

DEFAULT_APP_LOCALE = "en"
SUPPORTED_APP_LOCALES = ("en",)
DEFAULT_REPLY_LANGUAGE_MODE: ReplyLanguageMode = "auto"
DEFAULT_REPLY_LANGUAGE = "en"
DEFAULT_TIME_FORMAT: TimeFormat = "auto"
DEFAULT_THEME_MODE: ThemeMode = "telegram"
SUPPORTED_TIME_FORMATS: tuple[TimeFormat, ...] = ("auto", "24h", "12h")
SUPPORTED_THEME_MODES: tuple[ThemeMode, ...] = ("telegram", "light", "dark")


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
    return DEFAULT_APP_LOCALE


def validate_app_locale(value: str | None) -> str:
    primary = primary_language_tag(value)
    if primary not in SUPPORTED_APP_LOCALES:
        supported = ", ".join(SUPPORTED_APP_LOCALES)
        raise ValueError(f"unsupported locale; expected one of: {supported}")
    return primary


def normalize_reply_language(value: str | None) -> str:
    return primary_language_tag(value) or DEFAULT_APP_LOCALE


def normalize_reply_language_mode(value: str | None) -> ReplyLanguageMode:
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
    merged.setdefault("time_format", DEFAULT_TIME_FORMAT)
    merged.setdefault("theme_mode", DEFAULT_THEME_MODE)
    merged["locale_source"] = "telegram"
    merged["reply_language_mode"] = DEFAULT_REPLY_LANGUAGE_MODE
    merged["reply_language"] = DEFAULT_REPLY_LANGUAGE
    merged["time_format"] = normalize_time_format(str(merged.get("time_format") or ""))
    merged["theme_mode"] = normalize_theme_mode(str(merged.get("theme_mode") or ""))
    return merged


def app_locale_name(locale: str) -> str:
    return "English"


def format_language_settings_reply(
    *,
    app_locale: str,
    reply_language_mode: str,
    reply_language: str | None = None,
    language: str | None,
) -> str:
    return "Reply language settings are not configurable. Replies match each message."
