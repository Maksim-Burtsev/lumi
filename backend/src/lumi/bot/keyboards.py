"""Inline keyboard builders."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from lumi.assistant.orchestrator import Button
from lumi.config import get_settings


def mini_app_button() -> InlineKeyboardButton | None:
    """WebApp button if APP_PUBLIC_URL is configured with HTTPS."""
    settings = get_settings()
    url = settings.mini_app_url
    if url and url.startswith("https://"):
        return InlineKeyboardButton(text="✨ Открыть Lumi", web_app=WebAppInfo(url=url))
    return None


def markup_from_buttons(
    rows: list[list[Button]], *, with_app_button: bool = False
) -> InlineKeyboardMarkup | None:
    keyboard: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=b.text, callback_data=b.callback_data) for b in row]
        for row in rows
        if row
    ]
    if with_app_button:
        app_btn = mini_app_button()
        if app_btn:
            keyboard.append([app_btn])
    if not keyboard:
        return None
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def start_keyboard() -> InlineKeyboardMarkup | None:
    app_btn = mini_app_button()
    if app_btn is None:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[app_btn]])
