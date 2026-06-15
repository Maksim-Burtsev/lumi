"""User and main-conversation lifecycle."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.config import get_settings
from lumi.db.models import Conversation, ConversationKind, User
from lumi.utils.time import utc_now


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def ensure_user(
        self,
        telegram_user_id: int,
        *,
        telegram_chat_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
        touch_last_seen: bool = True,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is None:
            settings = get_settings()
            try:
                async with self.session.begin_nested():
                    user = User(
                        telegram_user_id=telegram_user_id,
                        telegram_chat_id=telegram_chat_id or telegram_user_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        language_code=language_code,
                        timezone=settings.default_timezone,
                        # Start from the Telegram interface language; chat replies
                        # mirror the message language anyway (see system prompt).
                        locale=(language_code or "ru")[:2],
                    )
                    self.session.add(user)
                    await self.session.flush()
            except IntegrityError:
                user = await self.get_by_telegram_id(telegram_user_id)
                if user is None:
                    raise
        else:
            # Keep profile fresh, never blank out existing values.
            if telegram_chat_id:
                user.telegram_chat_id = telegram_chat_id
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
        if touch_last_seen:
            user.last_seen_at = utc_now()
        return user

    async def ensure_main_conversation(self, user: User) -> Conversation:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.user_id == user.id,
                Conversation.kind == ConversationKind.MAIN,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(user_id=user.id, kind=ConversationKind.MAIN, title="Lumi")
            self.session.add(conversation)
            await self.session.flush()
        return conversation
