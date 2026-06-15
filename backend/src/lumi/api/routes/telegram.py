"""Telegram webhook ingress for production."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request

from lumi.bot.handlers import router as bot_router
from lumi.config import get_settings

router = APIRouter()


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict[str, bool]:
    settings = get_settings()
    if not settings.telegram_webhook_enabled:
        raise HTTPException(status_code=404, detail="telegram_webhook_disabled")
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="forbidden")
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="telegram_bot_token_missing")

    payload = await request.json()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(bot_router)
    try:
        update = Update.model_validate(payload, context={"bot": bot})
        await dispatcher.feed_update(bot, update, telegram_update_id=update.update_id)
    finally:
        await bot.session.close()
    return {"ok": True}
