from datetime import timedelta

from lumi.assistant.context_builder import ContextBuilder
from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import MemoryCandidate
from lumi.db.models import Message, MessageRole
from lumi.db.session import session_scope
from lumi.services.calendar import CalendarService
from lumi.services.tasks import TaskService
from lumi.services.users import UserService
from lumi.utils.time import utc_now

from .conftest import TEST_TELEGRAM_ID


async def _seed_state():
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID, first_name="Макс", username="tester")
        conversation = await users.ensure_main_conversation(u)
        await TaskService(session).create_task(
            u, title="Архитектура Lumi", priority="high", due_at=utc_now() + timedelta(hours=5)
        )
        from lumi.utils.time import local_day_bounds

        _, day_end = local_day_bounds(utc_now(), u.timezone)
        standup_start = min(utc_now() + timedelta(hours=1), day_end - timedelta(minutes=30))
        await CalendarService(session).create_internal_block(
            u, title="Standup", start_at=standup_start,
            end_at=standup_start + timedelta(minutes=25),
        )
        await MemoryService(session).store_candidate(
            u, MemoryCandidate(kind="preference", text="Дайджесты до 09:30", importance=4,
                               confidence=0.9),
        )
        for i in range(3):
            session.add(Message(
                conversation_id=conversation.id, user_id=u.id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"сообщение {i}", char_count=11,
            ))
        # Compacted message must never reach the context.
        session.add(Message(
            conversation_id=conversation.id, user_id=u.id, role=MessageRole.USER,
            content="СТАРОЕ-СЖАТОЕ-СООБЩЕНИЕ", char_count=20, is_compacted=True,
        ))
        return u.id, conversation.id


async def test_context_contains_all_sections(user):
    await _seed_state()
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(u)
        context = await ContextBuilder(session).build(
            user=u, conversation=conversation,
            current_text="Когда присылать дайджест?",
            action_results=["Создана задача: «тест»"],
        )

    joined = "\n".join(s for s in context.debug_snapshot["sections"])
    assert "Макс" in joined                      # profile
    assert "Архитектура Lumi" in joined          # active tasks
    assert "Standup" in joined                   # calendar
    assert "Дайджесты до 09:30" in joined        # memory
    assert "Создана задача" in joined            # action results
    assert "Permissions:" in joined
    assert "СТАРОЕ-СЖАТОЕ-СООБЩЕНИЕ" not in joined

    # Recent messages present, compacted excluded.
    all_text = "\n".join(m.content for m in context.messages)
    assert "сообщение 2" in all_text
    assert "СТАРОЕ-СЖАТОЕ-СООБЩЕНИЕ" not in all_text

    # Last message is the current user text.
    assert context.messages[-1].content == "Когда присылать дайджест?"
    assert context.messages[-1].role == "user"


async def test_context_respects_char_budget(user, monkeypatch):
    from lumi.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_context_max_chars", 9000)

    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(u)
        # 40 long messages, far over budget.
        for i in range(40):
            session.add(Message(
                conversation_id=conversation.id, user_id=u.id,
                role=MessageRole.USER, content=f"длинное сообщение {i} " + "x" * 800,
                char_count=820,
            ))

    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(u)
        context = await ContextBuilder(session).build(
            user=u, conversation=conversation, current_text="привет",
        )
    # Recent block respects what's left of the budget instead of dumping all 40.
    assert context.debug_snapshot["recent_messages"] < 40
