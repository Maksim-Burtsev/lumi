"""Outbound Telegram notifications (used by worker/scheduler, not the bot loop)."""

from __future__ import annotations

from typing import Any

import httpx

from lumi.bot.formatting import rich_html_requires_rich_message, telegram_plain_text
from lumi.config import get_settings
from lumi.db.models import User
from lumi.logging import get_logger
from lumi.utils.text import chunk_telegram

log = get_logger(__name__)


def _telegram_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value


async def _telegram_api_post(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=5, read=20, write=10, pool=5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Telegram {method} returned non-JSON response") from exc
    if response.status_code >= 400 or data.get("ok") is not True:
        description = data.get("description") or response.text[:200]
        raise RuntimeError(f"Telegram {method} failed: {description}")
    return data


def _rich_message_payload(html: str) -> dict[str, Any]:
    return {"html": html, "skip_entity_detection": True}


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _reply_markup_payload(*, reply_markup=None, open_app_button: bool = False, open_app_button_label: str | None = None):
    from aiogram.types import InlineKeyboardMarkup

    payload = _telegram_json(reply_markup)
    inline_keyboard = list((payload or {}).get("inline_keyboard") or [])
    if open_app_button:
        settings = get_settings()
        url = getattr(settings, "mini_app_url", None)
        if url and str(url).startswith("https://"):
            inline_keyboard.append([{
                "text": open_app_button_label or "✨ Открыть Lumi",
                "web_app": {"url": url},
            }])
    if not inline_keyboard:
        return reply_markup, None
    api_payload = {"inline_keyboard": inline_keyboard}
    if reply_markup is None and not open_app_button:
        return None, None
    if reply_markup is not None and not open_app_button:
        return reply_markup, payload
    return InlineKeyboardMarkup.model_validate(api_payload), api_payload


async def send_telegram_message(
    user: User,
    text: str,
    *,
    reply_markup=None,
    rich_html: str | None = None,
    open_app_button: bool = False,
    open_app_button_label: str | None = None,
) -> bool:
    """Send a message to the user's private chat. Returns False on failure."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("cannot notify: TELEGRAM_BOT_TOKEN is not set")
        return False
    chat_id = user.telegram_chat_id or user.telegram_user_id

    from aiogram import Bot

    bot = Bot(token=settings.telegram_bot_token)
    try:
        markup, markup_payload = _reply_markup_payload(
            reply_markup=reply_markup,
            open_app_button=open_app_button,
            open_app_button_label=open_app_button_label,
        )
        use_bot_api_rich = bool(getattr(settings, "telegram_use_rich_messages", False))
        if rich_html:
            if use_bot_api_rich:
                try:
                    await _telegram_api_post(
                        settings.telegram_bot_token,
                        "sendRichMessage",
                        _without_none({
                            "chat_id": chat_id,
                            "rich_message": _rich_message_payload(rich_html),
                            "reply_markup": markup_payload,
                        }),
                    )
                    return True
                except Exception:  # noqa: BLE001 — rich messages are new; plain fallback must work
                    log.exception("telegram rich notification failed; falling back to send_message")
            if not rich_html_requires_rich_message(rich_html):
                await bot.send_message(
                    chat_id=chat_id,
                    text=rich_html,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return True
            plain_chunks = chunk_telegram(telegram_plain_text(text))
            for i, chunk in enumerate(plain_chunks):
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_markup=markup if i == len(plain_chunks) - 1 else None,
                )
            return True
        chunks = chunk_telegram(telegram_plain_text(text))
        for i, chunk in enumerate(chunks):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                # Buttons only on the last chunk.
                reply_markup=markup if i == len(chunks) - 1 else None,
            )
        return True
    except Exception:  # noqa: BLE001
        log.exception("telegram notification failed")
        return False
    finally:
        await bot.session.close()


async def send_telegram_document(
    user: User,
    *,
    file_name: str,
    content: bytes,
    caption: str | None = None,
) -> bool:
    """Send a generated document (digest/report) to the user's chat."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("cannot send document: TELEGRAM_BOT_TOKEN is not set")
        return False
    chat_id = user.telegram_chat_id or user.telegram_user_id

    from aiogram import Bot
    from aiogram.types import BufferedInputFile

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(content, filename=file_name),
            caption=caption[:1000] if caption else None,
        )
        return True
    except Exception:  # noqa: BLE001
        log.exception("telegram document send failed")
        return False
    finally:
        await bot.session.close()
