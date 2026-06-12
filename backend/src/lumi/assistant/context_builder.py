"""ContextBuilder: assembles the full stateless prompt for every LLM call.

Sections (spec 06): identity, runtime metadata, profile, permissions,
active state (tasks/calendar/email/automations), relevant memories,
conversation summary, recent messages, action results, current message.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.memory_service import MemoryService
from lumi.assistant.prompts import CONTEXT_PREAMBLE, LUMI_SYSTEM_PROMPT
from lumi.config import get_settings
from lumi.db.models import (
    Conversation,
    ConversationSummary,
    EmailCategory,
    EmailThread,
    Message,
    MessageRole,
    ScheduledTask,
    User,
)
from lumi.llm.base import LLMMessage
from lumi.services.calendar import CalendarService
from lumi.services.tasks import TaskService
from lumi.utils.time import fmt_local, local_day_bounds, local_now, utc_now


@dataclass(slots=True)
class BuiltContext:
    system_prompt: str
    messages: list[LLMMessage]
    debug_snapshot: dict = field(default_factory=dict)
    estimated_chars: int = 0


class ContextBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskService(session)
        self.calendar = CalendarService(session)
        self.memory = MemoryService(session)

    async def build(
        self,
        *,
        user: User,
        conversation: Conversation,
        current_text: str,
        action_results: list[str] | None = None,
    ) -> BuiltContext:
        settings = get_settings()
        sections: list[str] = []

        # 2. Runtime metadata
        now_local = local_now(user.timezone)
        sections.append(
            "Current datetime: " + now_local.strftime("%Y-%m-%d %H:%M") + "\n"
            f"Timezone: {user.timezone}\n"
            f"User locale: {user.locale}\n"
            "Channel: telegram_private_chat"
        )

        # 3. User profile
        profile_lines = ["User:"]
        name = " ".join(filter(None, [user.first_name, user.last_name])) or "—"
        profile_lines.append(f"- Name: {name}")
        if user.username:
            profile_lines.append(f"- Telegram username: @{user.username}")
        profile_lines.append(f"- Timezone: {user.timezone}")
        sections.append("\n".join(profile_lines))

        # 4. Permissions
        sections.append(
            "Permissions:\n"
            "- Can create internal Lumi tasks automatically when user intent is clear.\n"
            "- Can create internal reminders automatically when user intent is clear.\n"
            "- Can store non-sensitive memory when user explicitly says «запомни» or intent is very clear.\n"
            "- Must ask confirmation before writing to external Google Calendar.\n"
            "- Must ask confirmation before sending, deleting, archiving, or modifying email.\n"
            "- Must never access local filesystem/shell as a tool."
        )

        # 5. Active state: tasks (+ the user's project structure)
        active_tasks = await self.tasks.list_active(user, limit=15)
        all_projects = sorted({
            t.project for t in await self.tasks.list_active(user, limit=200) if t.project
        })
        if all_projects:
            sections.append("Projects (области задач пользователя): " + ", ".join(all_projects))
        if active_tasks:
            lines = ["Active tasks:"]
            now = utc_now()
            for t in active_tasks:
                line = f"- [{t.priority.value}] {t.title}"
                if t.due_at:
                    overdue = " (ПРОСРОЧЕНО)" if t.due_at < now else ""
                    line += f" — срок {fmt_local(t.due_at, user.timezone)}{overdue}"
                if t.reminder_at:
                    line += f", напоминание {fmt_local(t.reminder_at, user.timezone)}"
                lines.append(line)
            sections.append("\n".join(lines))
        else:
            sections.append("Active tasks: нет активных задач.")

        # 6-7. Calendar today
        day_start, day_end = local_day_bounds(utc_now(), user.timezone)
        events = await self.calendar.list_events(user, day_start, day_end)
        if events:
            lines = ["Calendar today:"]
            for e in events:
                marker = {"proposed": " (предложено, не подтверждено)"}.get(e.status.value, "")
                lines.append(
                    f"- {fmt_local(e.start_at, user.timezone, '%H:%M')}–"
                    f"{fmt_local(e.end_at, user.timezone, '%H:%M')} {e.title}{marker}"
                )
            sections.append("\n".join(lines))
        else:
            sections.append("Calendar today: встреч нет.")

        # Email snapshot (counts only — cheap and useful)
        needs_reply = await self.session.execute(
            select(func.count()).select_from(EmailThread).where(
                EmailThread.user_id == user.id,
                EmailThread.category == EmailCategory.NEEDS_REPLY,
            )
        )
        needs_reply_count = needs_reply.scalar_one()
        if needs_reply_count:
            sections.append(f"Recent email triage: {needs_reply_count} писем ждут ответа.")

        # Automations
        automations = await self.session.execute(
            select(ScheduledTask).where(
                ScheduledTask.user_id == user.id, ScheduledTask.enabled.is_(True)
            )
        )
        automation_rows = list(automations.scalars())
        if automation_rows:
            lines = ["Active automations:"]
            for a in automation_rows[:8]:
                lines.append(f"- {a.title} ({a.cron_expression}, {a.timezone})")
            sections.append("\n".join(lines))

        # 8. Relevant memories
        memories = await self.memory.retrieve_relevant(user, current_text, limit=10)
        if memories:
            lines = ["Relevant memory:"]
            for m in memories:
                lines.append(f"- {m.text_}")
            sections.append("\n".join(lines))

        # 9. Conversation summary
        summary = await self._latest_summary(conversation.id)
        if summary:
            sections.append("Conversation summary:\n" + summary.summary_text)

        # 11. Action results
        if action_results:
            sections.append(
                "Backend actions already performed for this message:\n"
                + "\n".join(f"- {r}" for r in action_results)
            )

        # 10. Recent messages (fit into remaining budget)
        context_block = CONTEXT_PREAMBLE + "\n\n" + "\n\n".join(sections)
        budget = settings.llm_context_max_chars
        used = len(LUMI_SYSTEM_PROMPT) + len(context_block) + len(current_text)
        recent = await self._recent_messages(
            conversation.id, limit=settings.recent_messages_limit,
            char_budget=max(4000, budget - used - 2000),
        )

        messages: list[LLMMessage] = [LLMMessage(role="user", content=context_block)]
        messages.append(LLMMessage(
            role="assistant",
            content="Принял контекст. Готов отвечать как Lumi с учетом этого состояния.",
        ))
        for msg in recent:
            role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
            messages.append(LLMMessage(role=role, content=msg.content))
        messages.append(LLMMessage(role="user", content=current_text))

        estimated = sum(len(m.content) for m in messages) + len(LUMI_SYSTEM_PROMPT)
        return BuiltContext(
            system_prompt=LUMI_SYSTEM_PROMPT,
            messages=messages,
            debug_snapshot={
                "sections": sections,
                "recent_messages": len(recent),
                "memories_used": len(memories),
                "summary_used": bool(summary),
                "estimated_chars": estimated,
            },
            estimated_chars=estimated,
        )

    # ------------------------------------------------------------------

    async def _latest_summary(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        result = await self.session.execute(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(ConversationSummary.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _recent_messages(
        self, conversation_id: uuid.UUID, *, limit: int, char_budget: int
    ) -> list[Message]:
        """Last N non-compacted chat messages, newest last, trimmed to budget."""
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.is_compacted.is_(False),
                Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        newest_first = list(result.scalars())
        picked: list[Message] = []
        used = 0
        for msg in newest_first:
            if used + len(msg.content) > char_budget and picked:
                break
            picked.append(msg)
            used += len(msg.content)
        picked.reverse()
        return picked
