"""End-to-end smoke test with the mock LLM. No external keys needed.

Run: LLM_PROVIDER=mock python -m lumi.scripts.smoke
Checks: DB, user/conversation, orchestrator pipeline (extraction -> task ->
reply), context builder, scheduler due-query. Exits non-zero on failure.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from lumi.assistant.context_builder import ContextBuilder
from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.config import get_settings
from lumi.db.models import Message, MessageRole, Task, TaskStatus
from lumi.db.session import dispose_engine, session_scope
from lumi.llm.gateway import LLMGateway, reset_llm_provider
from lumi.llm.mock import MockLLMProvider
from lumi.services.automations import AutomationService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

SMOKE_TELEGRAM_ID = 990000001


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return ok


async def smoke() -> int:
    print("Lumi smoke test (mock LLM)\n")
    settings = get_settings()
    reset_llm_provider()
    gateway = LLMGateway(MockLLMProvider())
    ok = True

    # 1. DB connectivity + user/conversation
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(SMOKE_TELEGRAM_ID, first_name="Smoke")
        conversation = await users.ensure_main_conversation(user)
        ok &= check("database + user + main conversation", True,
                    f"user={user.telegram_user_id}")

    # 2. Orchestrator: message -> extraction -> task -> reply
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=gateway)
        result = await orchestrator.handle_user_message(
            telegram_user_id=SMOKE_TELEGRAM_ID,
            telegram_chat_id=SMOKE_TELEGRAM_ID,
            telegram_message_id=None,
            text="Напомни завтра в 10 написать Саше",
        )
        ok &= check("orchestrator reply", bool(result.reply_text), result.reply_text[:60])

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(SMOKE_TELEGRAM_ID)
        tasks_result = await session.execute(
            select(Task).where(
                Task.user_id == user.id,
                Task.status == TaskStatus.ACTIVE,
                Task.title.ilike("%саш%"),
            )
        )
        task = tasks_result.scalars().first()
        ok &= check("task created from chat", task is not None,
                    task.title if task else "not found")
        ok &= check("reminder set", bool(task and task.reminder_at),
                    str(task.reminder_at) if task else "")

        messages_result = await session.execute(
            select(Message).where(
                Message.user_id == user.id, Message.role == MessageRole.ASSISTANT
            )
        )
        ok &= check("assistant message saved", messages_result.scalars().first() is not None)

    # 3. Context builder
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(SMOKE_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(user)
        context = await ContextBuilder(session).build(
            user=user, conversation=conversation, current_text="Что у меня сегодня?"
        )
        ok &= check(
            "context builder",
            context.estimated_chars > 0
            and context.estimated_chars <= settings.llm_context_max_chars,
            f"{context.estimated_chars} chars, {len(context.messages)} messages",
        )

    # 4. Scheduler due-query
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(SMOKE_TELEGRAM_ID)
        automations = AutomationService(session)
        automation = await automations.ensure_system_calendar_sync(user)
        automation.next_run_at = utc_now()
        await session.flush()
        due = await automations.find_due_tasks()
        ok &= check("scheduler finds due calendar sync",
                    any(t.id == automation.id for t in due))
        automation.enabled = False

    await dispose_engine()
    print("\n" + ("SMOKE OK" if ok else "SMOKE FAILED"))
    return 0 if ok else 1


def main() -> None:
    sys.exit(asyncio.run(smoke()))


if __name__ == "__main__":
    main()
