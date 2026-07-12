"""Safe bootstrap seed: allowed user and main conversation only.

Run: python -m lumi.scripts.seed_local

Deliberately does not create or delete user-authored tasks or focus sessions. Use
``python -m lumi.scripts.seed_focus_demo`` for explicit local demo data.
"""

from __future__ import annotations

import asyncio

from lumi.config import get_settings
from lumi.db.session import dispose_engine, session_scope
from lumi.services.users import UserService


async def seed() -> None:
    settings = get_settings()
    if not settings.allowed_telegram_user_ids:
        print("ALLOWED_TELEGRAM_USER_IDS пуст — заполни .env и повтори. Ничего не создано.")
        return

    telegram_user_id = settings.allowed_telegram_user_ids[0]
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(telegram_user_id)
        await users.ensure_main_conversation(user)

    print("Seed готов. Создано/проверено:")
    print(f"  • user telegram_id={telegram_user_id}")
    print("  • main conversation")
    await dispose_engine()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
