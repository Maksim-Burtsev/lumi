"""Bot entrypoint: `python -m lumi.bot.runner` — aiogram long polling."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from lumi.bot.handlers import router
from lumi.config import get_settings
from lumi.db.session import dispose_engine
from lumi.logging import get_logger, setup_logging
from lumi.worker.queue import close_queue

log = get_logger(__name__)


async def run_bot() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather and put it into .env"
        )
    if settings.telegram_webhook_enabled:
        log.info("telegram webhook enabled; polling bot process is idle")
        await asyncio.Event().wait()
    if not settings.allowed_telegram_user_ids:
        log.warning(
            "ALLOWED_TELEGRAM_USER_IDS is empty — the bot will ignore everyone. "
            "Send /start and check logs for your id, then add it to .env"
        )

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    # Polling and webhook are mutually exclusive — clear any stale webhook.
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("webhook cleared, starting long polling")
    except Exception:  # noqa: BLE001
        log.exception("could not delete webhook — polling may conflict")

    # Keep the chat menu button pointing at the Mini App (syncs on every start).
    if settings.mini_app_url and settings.mini_app_url.startswith("https://"):
        from aiogram.types import MenuButtonWebApp, WebAppInfo

        menu_button = MenuButtonWebApp(text="Lumi", web_app=WebAppInfo(url=settings.mini_app_url))
        try:
            await bot.set_chat_menu_button(menu_button=menu_button)
            log.info("mini app menu button set", fields={"url": settings.mini_app_url})
        except Exception:  # noqa: BLE001
            log.exception("could not set menu button")

        for telegram_user_id in settings.allowed_telegram_user_ids:
            try:
                await bot.set_chat_menu_button(chat_id=telegram_user_id, menu_button=menu_button)
                log.info(
                    "mini app chat menu button set",
                    fields={"chat_id": telegram_user_id, "url": settings.mini_app_url},
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "could not set chat menu button", fields={"chat_id": telegram_user_id}
                )

    me = await bot.get_me()
    log.info("lumi bot started", fields={"bot_username": me.username})

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        await close_queue()
        await dispose_engine()
        await bot.session.close()
        log.info("lumi bot stopped")


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
