"""Conversation compaction: old messages -> structured summary."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.prompts import COMPACTION_SYSTEM
from lumi.config import get_settings
from lumi.db.models import (
    Conversation,
    ConversationSummary,
    Message,
    MessageRole,
    User,
)
from lumi.llm.base import LLMMessage, estimate_tokens
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger

log = get_logger(__name__)

PROTECTED_RECENT_MESSAGES = 30


class CompactionService:
    def __init__(self, session: AsyncSession, *, llm: LLMGateway | None = None) -> None:
        self.session = session
        self.llm = llm or LLMGateway()

    async def needs_compaction(self, conversation: Conversation) -> bool:
        settings = get_settings()
        result = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(Message.char_count), 0)).where(
                Message.conversation_id == conversation.id,
                Message.is_compacted.is_(False),
                Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
            )
        )
        count, chars = result.one()
        return (
            count > settings.compact_after_messages + PROTECTED_RECENT_MESSAGES
            or chars > settings.compact_after_chars
        )

    async def compact(
        self, user: User, conversation: Conversation, *, agent_run_id: uuid.UUID | None = None
    ) -> ConversationSummary | None:
        """Summarize everything except the protected recent tail."""
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.is_compacted.is_(False),
                Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
            )
            .order_by(Message.created_at)
        )
        messages = list(result.scalars())
        if len(messages) <= PROTECTED_RECENT_MESSAGES:
            return None
        to_compact = messages[:-PROTECTED_RECENT_MESSAGES]

        previous = await self.session.execute(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation.id)
            .order_by(ConversationSummary.created_at.desc())
            .limit(1)
        )
        previous_summary = previous.scalar_one_or_none()

        settings = get_settings()
        parts: list[str] = []
        parts.append(f"Target language: {user.locale or 'en'}")
        if previous_summary:
            parts.append("Previous summary:\n" + previous_summary.summary_text)
        history_lines = []
        for msg in to_compact:
            speaker = "User" if msg.role == MessageRole.USER else "Lumi"
            history_lines.append(f"{speaker}: {msg.content}")
        history = "\n".join(history_lines)
        # Stay within a sane input budget.
        max_history = settings.llm_context_max_chars - 6000
        if len(history) > max_history:
            history = history[-max_history:]
        parts.append("History to compact:\n" + history)
        parts.append(f"Target summary length: up to {settings.summary_target_chars} characters.")

        response = await self.llm.complete(
            messages=[LLMMessage(role="user", content="\n\n".join(parts))],
            system=COMPACTION_SYSTEM,
            temperature=0.1,
            max_tokens=4096,
            request_kind="compaction",
            user_id=user.id,
            agent_run_id=agent_run_id,
            session=self.session,
        )
        summary_text = response.text.strip()
        if not summary_text:
            log.warning("compaction produced empty summary, skipping")
            return None

        summary = ConversationSummary(
            conversation_id=conversation.id,
            user_id=user.id,
            summary_text=summary_text[: settings.summary_target_chars * 2],
            from_message_id=to_compact[0].id,
            to_message_id=to_compact[-1].id,
            message_count=len(to_compact),
            token_estimate=estimate_tokens(summary_text),
            version=(previous_summary.version + 1) if previous_summary else 1,
        )
        self.session.add(summary)
        await self.session.flush()

        ids = [m.id for m in to_compact]
        await self.session.execute(
            update(Message).where(Message.id.in_(ids)).values(is_compacted=True)
        )
        conversation.summary_current_id = summary.id
        conversation.compacted_until_message_id = to_compact[-1].id
        log.info(
            "conversation compacted",
            fields={"messages": len(to_compact), "summary_version": summary.version},
        )
        return summary
