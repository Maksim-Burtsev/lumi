from datetime import timedelta

from lumi.assistant.context_builder import ContextBuilder, PlannerContextBuilder
from lumi.assistant.memory_service import MemoryService
from lumi.assistant.schemas import MemoryCandidate
from lumi.db.models import AgentRunType, Message, MessageRole
from lumi.db.session import session_scope
from lumi.services.calendar import CalendarService
from lumi.services.confirmations import ConfirmationService
from lumi.services.runs import RunService
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
    assert "Existing active tasks (state, not actions performed now):" in joined
    assert "Standup" in joined                   # calendar
    assert "Дайджесты до 09:30" in joined        # memory
    assert "Создана задача" in joined            # action results
    assert "Backend action facts for the current message (source of truth):" in joined
    assert "Do not claim any other backend action happened." in joined
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


async def test_planner_context_is_compact_state_with_counts_not_full_prompt(user):
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID, first_name="Макс", username="tester")
        conversation = await users.ensure_main_conversation(u)
        task_service = TaskService(session)
        recent = await task_service.create_task(
            u,
            title="Webhook для Lumi на проде",
            project=None,
        )
        await task_service.create_task(
            u,
            title="Секретная активная задача",
            project="Lumi",
        )
        session.add(Message(
            conversation_id=conversation.id,
            user_id=u.id,
            role=MessageRole.USER,
            content="ПОЛНАЯ ИСТОРИЯ НЕ ДОЛЖНА БЫТЬ В PLANNER CONTEXT",
            char_count=47,
        ))
        runs = RunService(session)
        run = await runs.create(
            user_id=u.id,
            type_=AgentRunType.CHAT,
            trigger="telegram_message",
            conversation_id=conversation.id,
            input_summary="create",
        )
        await runs.log_tool_call(
            run=run,
            tool_name="create_task",
            status="completed",
            args={"title": recent.title},
            result={"task_id": str(recent.id)},
        )

        context = await PlannerContextBuilder(session).build(user=u, conversation=conversation)

    prompt = context.to_prompt_text()
    trace = context.to_trace_summary()
    assert "recent_task_refs" in prompt
    assert "active_task_candidates" in prompt
    assert "known_projects" in prompt
    assert str(recent.id) in prompt
    assert "Webhook для Lumi на проде" in prompt
    assert "Секретная активная задача" in prompt
    assert "ПОЛНАЯ ИСТОРИЯ" not in prompt
    assert "Calendar today" not in prompt
    assert "Attached image understanding" not in prompt
    assert trace["recent_task_ref_count"] == 1
    assert trace["active_task_count"] == 2
    assert trace["known_project_count"] == 1
    assert "Webhook для Lumi на проде" not in str(trace)


async def test_planner_context_exposes_recent_and_pending_project_refs(user):
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID, first_name="Макс", username="tester")
        conversation = await users.ensure_main_conversation(u)
        task_service = TaskService(session)
        task = await task_service.create_task(
            u,
            title="Разобраться с лимитами",
            project="Lumi",
        )
        runs = RunService(session)
        run = await runs.create(
            user_id=u.id,
            type_=AgentRunType.CHAT,
            trigger="telegram_message",
            conversation_id=conversation.id,
            input_summary="create",
        )
        await runs.log_tool_call(
            run=run,
            tool_name="create_task",
            status="completed",
            args={"title": task.title, "project": "Lumi"},
            result={"task_id": str(task.id)},
        )
        pending = await ConfirmationService(session).create(
            u,
            action_type="create_task",
            action_payload={
                "title": "проработать задачи с маркетингом",
                "project": "Lumi",
                "confidence": 0.7,
                "requires_confirmation": True,
            },
            prompt="Создать задачу «проработать задачи с маркетингом»?",
        )

        context = await PlannerContextBuilder(session).build(user=u, conversation=conversation)

    prompt = context.to_prompt_text()
    trace = context.to_trace_summary()
    assert "project_refs:" in prompt
    assert 'last_task_project="Lumi"' in prompt
    assert 'last_proposed_task_project="Lumi"' in prompt
    assert "pending_task_refs:" in prompt
    assert str(pending.id) in prompt
    assert "проработать задачи с маркетингом" in prompt
    assert trace["pending_task_ref_count"] == 1


async def test_final_context_includes_task_projects_and_pending_confirmations(user):
    async with session_scope() as session:
        users = UserService(session)
        u = await users.ensure_user(TEST_TELEGRAM_ID, first_name="Макс", username="tester")
        conversation = await users.ensure_main_conversation(u)
        await TaskService(session).create_task(
            u,
            title="Разобраться с лимитами",
            project="Lumi",
        )
        await ConfirmationService(session).create(
            u,
            action_type="create_task",
            action_payload={
                "title": "проработать задачи с маркетингом",
                "project": "Lumi",
                "confidence": 0.7,
                "requires_confirmation": True,
            },
            prompt="Создать задачу «проработать задачи с маркетингом»?",
        )

        context = await ContextBuilder(session).build(
            user=u,
            conversation=conversation,
            current_text="В какой проект она пойдет?",
        )

    joined = "\n".join(s for s in context.debug_snapshot["sections"])
    assert "project=Lumi" in joined
    assert "Pending confirmations" in joined
    assert "проработать задачи с маркетингом" in joined
    assert "Lumi" in joined
