"""Outbound Telegram notifications (used by worker/scheduler, not the bot loop)."""

from __future__ import annotations

from lumi.bot.formatting import telegram_plain_text
from lumi.config import get_settings
from lumi.db.models import User
from lumi.logging import get_logger
from lumi.utils.text import chunk_telegram

log = get_logger(__name__)


async def send_telegram_message(
    user: User,
    text: str,
    *,
    reply_markup=None,
    capture_message_ids: bool = False,
) -> bool | list[int]:
    """Send a message to the user's private chat. Returns False on failure."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.warning("cannot notify: TELEGRAM_BOT_TOKEN is not set")
        return False
    chat_id = user.telegram_chat_id or user.telegram_user_id

    from aiogram import Bot

    bot = Bot(token=settings.telegram_bot_token)
    try:
        chunks = chunk_telegram(telegram_plain_text(text))
        message_ids: list[int] = []
        for i, chunk in enumerate(chunks):
            sent = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                # Buttons only on the last chunk.
                reply_markup=reply_markup if i == len(chunks) - 1 else None,
            )
            if capture_message_ids:
                message_ids.append(sent.message_id)
        return message_ids if capture_message_ids else True
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
