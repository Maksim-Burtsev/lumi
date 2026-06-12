"""Seed: user, main conversation, default news topics, default automations.

Run: python -m lumi.scripts.seed_local
"""

from __future__ import annotations

import asyncio

from lumi.config import get_settings
from lumi.db.session import dispose_engine, session_scope
from lumi.services.users import UserService

# Automations and news topics are user-created in the Mini App — no defaults on purpose.


async def seed() -> None:
    settings = get_settings()
    if not settings.allowed_telegram_user_ids:
        print("ALLOWED_TELEGRAM_USER_IDS пуст — заполни .env и повтори. Ничего не создано.")
        return

    telegram_user_id = settings.allowed_telegram_user_ids[0]
    created: list[str] = []

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(telegram_user_id)
        await users.ensure_main_conversation(user)
        created.append(f"user telegram_id={telegram_user_id}")
        created.append("main conversation")

    print("Seed готов. Создано/проверено:")
    for line in created:
        print(f"  • {line}")
    await dispose_engine()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
