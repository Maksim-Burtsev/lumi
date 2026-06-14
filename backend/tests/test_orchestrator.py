from sqlalchemy import select

from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.db.models import (
    AgentRun,
    AgentRunType,
    Message,
    MessageRole,
    PendingConfirmation,
    RunStatus,
    ScheduledTask,
    Task,
    ToolCall,
)
from lumi.db.session import session_scope
from lumi.llm.base import LLMResponse
from lumi.llm.gateway import LLMGateway
from lumi.llm.mock import MockLLMProvider
from lumi.services.tasks import TaskService
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


class PendingTaskProvider:
    name = "pending-task"
    model = "pending-task-1"

    def __init__(self) -> None:
        self.final_chat_calls = 0

    async def complete_json(self, **kwargs) -> dict:
        return {
            "language": "ru",
            "intents": ["create_task"],
            "tasks": [
                {
                    "title": "Свой аналог session в Lumi интегрировать",
                    "description": None,
                    "due_at_local": None,
                    "reminder_at_local": None,
                    "priority": "medium",
                    "project": "Работа",
                    "tags": [],
                    "confidence": 0.7,
                    "requires_confirmation": True,
                }
            ],
            "memory_candidates": [],
            "calendar_requests": [],
            "automation_requests": [],
            "email_requests": [],
            "news_requests": [],
            "should_answer_normally": False,
        }

    async def complete(self, **kwargs) -> LLMResponse:
        self.final_chat_calls += 1
        text = (
            "Записал в активные задачи:\n"
            "- [medium] Сделать real-time обновления в mini-app Lumi\n"
            "- [medium] Написать короткий сценарий теста accept/reject\n"
            "- [medium] Свой аналог session в Lumi интегрировать"
        )
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=len(text),
        )


class RenameTaskProvider:
    name = "rename-task"
    model = "rename-task-1"

    def __init__(
        self,
        *,
        current_title: str,
        new_title: str,
        project: str | None = None,
        tags: list[str] | None = None,
        requires_confirmation: bool = False,
        confidence: float = 0.95,
    ) -> None:
        self.current_title = current_title
        self.new_title = new_title
        self.project = project
        self.tags = tags or []
        self.requires_confirmation = requires_confirmation
        self.confidence = confidence
        self.final_chat_calls = 0

    async def complete_json(self, **kwargs) -> dict:
        return {
            "language": "ru",
            "intents": ["update_task"],
            "tasks": [],
            "task_updates": [
                {
                    "operation": "rename",
                    "current_title": self.current_title,
                    "new_title": self.new_title,
                    "project": self.project,
                    "tags": self.tags,
                    "confidence": self.confidence,
                    "requires_confirmation": self.requires_confirmation,
                }
            ],
            "memory_candidates": [],
            "calendar_requests": [],
            "automation_requests": [],
            "email_requests": [],
            "news_requests": [],
            "should_answer_normally": False,
        }

    async def complete(self, **kwargs) -> LLMResponse:
        self.final_chat_calls += 1
        return LLMResponse(
            text="Готово: переименовал задачу.",
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=29,
        )


class AgentPlannerProvider:
    name = "agent-planner"
    model = "agent-planner-1"

    def __init__(self, plan: dict) -> None:
        self.plan = plan
        self.planner_prompts: list[str] = []
        self.final_chat_calls = 0

    async def complete_json(self, **kwargs) -> dict:
        assert kwargs["request_kind"] == "agent_planner"
        messages = kwargs.get("messages") or []
        self.planner_prompts.append((kwargs.get("system") or "") + "\n" + messages[-1].content)
        return self.plan

    async def complete(self, **kwargs) -> LLMResponse:
        self.final_chat_calls += 1
        return LLMResponse(
            text="final answer",
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=12,
        )


async def test_full_chat_pipeline_creates_task():
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(MockLLMProvider()))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=1,
            text="Напомни завтра в 10 написать Саше по договору",
            first_name="Тест",
        )
        assert result.reply_text
        assert result.agent_run_id is not None
        # Auto-created task -> action buttons attached.
        assert result.buttons

    async with session_scope() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].reminder_at is not None
        assert tasks[0].source == "chat"

        messages = (await session.execute(select(Message))).scalars().all()
        roles = {m.role for m in messages}
        assert MessageRole.USER in roles and MessageRole.ASSISTANT in roles

        run = (await session.execute(select(AgentRun))).scalars().one()
        assert run.status == RunStatus.COMPLETED

        tool_calls = (await session.execute(select(ToolCall))).scalars().all()
        assert any(c.tool_name == "create_task" and c.status == "completed" for c in tool_calls)


async def test_plain_chat_no_side_effects():
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(MockLLMProvider()))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=2,
            text="Привет! Как дела?",
        )
        assert result.reply_text

    async with session_scope() as session:
        assert (await session.execute(select(Task))).scalars().all() == []


async def test_action_only_pending_task_reply_does_not_list_existing_tasks():
    provider = PendingTaskProvider()
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(user, title="Сделать real-time обновления в mini-app Lumi")
        await TaskService(session).create_task(user, title="Написать короткий сценарий теста accept/reject")

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=3,
            text="добавь в бэклог задачу свой аналог session в Lumi интегрировать",
        )

        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tasks = (await session.execute(select(Task))).scalars().all()

    assert provider.final_chat_calls == 0
    assert len(confirmations) == 1
    assert confirmations[0].action_type == "create_task"
    assert len(tasks) == 2
    assert "Свой аналог session в Lumi интегрировать" in result.reply_text
    assert "Сделать real-time обновления" not in result.reply_text
    assert "сценарий теста accept/reject" not in result.reply_text


async def test_rename_task_updates_db_and_uses_backend_reply():
    provider = RenameTaskProvider(
        current_title="Написать короткий сценарий теста accept/reject",
        new_title="Свой аналог session в Lumi интегрировать",
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="Написать короткий сценарий теста accept/reject",
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=4,
            text=(
                "Задачу «Написать короткий сценарий теста accept/reject» переименуй "
                "в «Свой аналог session в Lumi интегрировать»"
            ),
        )

        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert provider.final_chat_calls == 0
    assert updated.title == "Свой аналог session в Lumi интегрировать"
    assert result.reply_text == (
        "Готово: переименовал «Написать короткий сценарий теста accept/reject» "
        "→ «Свой аналог session в Lumi интегрировать»."
    )
    assert any(c.tool_name == "rename_task" and c.status == "completed" for c in tool_calls)


async def test_agent_planner_read_tasks_does_not_send_task_list_to_first_llm_call():
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "read_tasks",
                "args": {"filter": "all"},
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(user, title="Секретная открытая задача")

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=42,
            text="Покажи открытые задачи",
        )

        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.final_chat_calls == 0
    assert provider.planner_prompts
    assert "read_tasks" in provider.planner_prompts[0]
    assert "Секретная открытая задача" not in provider.planner_prompts[0]
    assert "Секретная открытая задача" in result.reply_text
    assert any(c.tool_name == "read_tasks" and c.status == "completed" for c in tool_calls)


async def test_agent_planner_rename_tool_call_updates_db_without_final_llm():
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "rename_task",
                "args": {
                    "current_title": "Написать короткий сценарий теста accept/reject",
                    "new_title": "Свой аналог session в Lumi интегрировать",
                },
                "confidence": 0.95,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="Написать короткий сценарий теста accept/reject",
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=43,
            text=(
                "Rename the task about accept/reject scenario to "
                "«Свой аналог session в Lumi интегрировать»"
            ),
        )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert provider.final_chat_calls == 0
    assert updated.title == "Свой аналог session в Lumi интегрировать"
    assert result.reply_text.startswith("Готово: переименовал")


async def test_low_confidence_explicit_rename_uses_backend_result_not_final_llm():
    provider = RenameTaskProvider(
        current_title="agent loop",
        new_title="проверить production harness",
        confidence=0.7,
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="проверить новый agent loop",
            tags=["test"],
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=44,
            text="Переименуй задачу про agent loop в «проверить production harness»",
        )

        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert provider.final_chat_calls == 0
    assert updated.title == "проверить production harness"
    assert result.reply_text == (
        "Готово: переименовал «проверить новый agent loop» → "
        "«проверить production harness»."
    )
    assert any(c.tool_name == "rename_task" and c.status == "completed" for c in tool_calls)


async def test_rename_task_high_confidence_confirmation_flag_still_updates_db():
    provider = RenameTaskProvider(
        current_title="Написать короткий сценарий теста accept/reject",
        new_title="Свой аналог session в Lumi интегрировать",
        requires_confirmation=True,
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="Написать короткий сценарий теста accept/reject",
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=41,
            text=(
                "Задачу «Написать короткий сценарий теста accept/reject» переименуй "
                "в «Свой аналог session в Lumi интегрировать»"
            ),
        )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert updated.title == "Свой аналог session в Lumi интегрировать"
    assert result.reply_text.startswith("Готово: переименовал")


async def test_rename_task_not_found_does_not_claim_done():
    provider = RenameTaskProvider(
        current_title="Несуществующая задача",
        new_title="Новое название",
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(user, title="Другая задача")

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=5,
            text="Переименуй задачу «Несуществующая задача» в «Новое название»",
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.final_chat_calls == 0
    assert [task.title for task in tasks] == ["Другая задача"]
    assert "Готово" not in result.reply_text
    assert result.reply_text == "Не нашёл активную задачу «Несуществующая задача». Уточни название."
    assert any(c.tool_name == "rename_task" and c.status == "skipped" for c in tool_calls)


async def test_rename_task_fuzzy_match_updates_db_and_uses_backend_reply():
    provider = RenameTaskProvider(
        current_title="аналог сешн в lumi",
        new_title="Интегрировать свой session в Lumi",
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="Свой аналог session в Lumi интегрировать",
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=6,
            text="Переименуй задачу про аналог сешн в lumi в «Интегрировать свой session в Lumi»",
        )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert provider.final_chat_calls == 0
    assert updated.title == "Интегрировать свой session в Lumi"
    assert result.reply_text == (
        "Готово: переименовал «Свой аналог session в Lumi интегрировать» "
        "→ «Интегрировать свой session в Lumi»."
    )


async def test_rename_task_ambiguous_returns_choice_buttons():
    provider = RenameTaskProvider(
        current_title="написать сценарий теста",
        new_title="Новый сценарий",
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        first = await TaskService(session).create_task(
            user,
            title="Написать сценарий теста accept reject",
            project="Lumi",
            tags=["test"],
        )
        second = await TaskService(session).create_task(
            user,
            title="Написать сценарий теста approve reject",
            project="Работа",
        )

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=7,
            text="Переименуй задачу написать сценарий теста в «Новый сценарий»",
        )

        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert result.reply_text == "Нашёл несколько похожих задач. Какую переименовать?"
    assert len(result.buttons) == 2
    assert result.buttons[0][0].callback_data.startswith("rename_pick:")
    assert len(result.buttons[0][0].callback_data) <= 64
    assert {result.buttons[0][0].text, result.buttons[1][0].text} == {
        "Написать сценарий теста approve reject · Работа",
        "Написать сценарий теста accept reject · Lumi · #test",
    }
    assert confirmations[0].action_type == "rename_task_choice"
    assert set(confirmations[0].action_payload["candidate_task_ids"]) == {
        str(first.id),
        str(second.id),
    }
    assert any(c.tool_name == "rename_task" and c.status == "requires_confirmation" for c in tool_calls)


async def test_snooze_task_sets_reminder_and_backend_reply_with_time():
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "snooze_task",
                "args": {"task_query": "real-time обновления в люми", "preset": "tomorrow"},
                "confidence": 0.7,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        task = await TaskService(session).create_task(
            user,
            title="Сделать real-time обновления в mini-app Lumi",
            project="Работа",
            tags=["backlog", "mini-app", "lumi"],
        )
        task_id = task.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=45,
            text="отложи задачу про real-time обновления в люми на завтра",
        )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        updated = await TaskService(session).get(user, task_id)

    assert provider.final_chat_calls == 0
    assert updated.snoozed_until is not None
    assert updated.reminder_at == updated.snoozed_until
    assert result.reply_text.startswith(
        "Готово: отложил «Сделать real-time обновления в mini-app Lumi» до "
    )


async def test_snooze_prefers_visible_candidate_over_already_snoozed_match():
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "snooze_task",
                "args": {"task_query": "real-time обновления в люми", "preset": "tomorrow"},
                "confidence": 0.7,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        already_snoozed = await TaskService(session).create_task(
            user,
            title="Сделать real-time обновления в mini-app Lumi",
            project="Работа",
            tags=["backlog", "mini-app", "lumi", "real-time"],
        )
        already_snoozed = await TaskService(session).snooze_task(
            user,
            already_snoozed,
            preset="tomorrow",
        )
        already_snoozed_id = already_snoozed.id
        already_snoozed_until = already_snoozed.snoozed_until
        visible = await TaskService(session).create_task(
            user,
            title="Сделать real-time обновления в Lumi",
        )
        visible_id = visible.id

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=48,
            text="отложи задачу про real-time обновления в люми на завтра",
        )

    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        old_task = await TaskService(session).get(user, already_snoozed_id)
        new_task = await TaskService(session).get(user, visible_id)

    assert provider.final_chat_calls == 0
    assert old_task.snoozed_until == already_snoozed_until
    assert new_task.snoozed_until is not None
    assert new_task.reminder_at == new_task.snoozed_until
    assert result.reply_text.startswith("Готово: отложил «Сделать real-time обновления в Lumi» до ")


async def test_snooze_ambiguous_visible_matches_returns_choice_buttons():
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "snooze_task",
                "args": {"task_query": "real-time обновления", "preset": "tomorrow"},
                "confidence": 0.7,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        first = await TaskService(session).create_task(
            user,
            title="Сделать real-time обновления в Lumi",
        )
        second = await TaskService(session).create_task(
            user,
            title="Сделать real-time обновления в mini-app Lumi",
            project="Работа",
            tags=["mini-app"],
        )

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=49,
            text="отложи задачу про real-time обновления на завтра",
        )

        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.final_chat_calls == 0
    assert result.reply_text == "Нашёл несколько похожих задач. Какую отложить?"
    assert len(result.buttons) == 2
    assert result.buttons[0][0].callback_data.startswith("snooze_pick:")
    assert confirmations[0].action_type == "snooze_task_choice"
    assert set(confirmations[0].action_payload["candidate_task_ids"]) == {
        str(first.id),
        str(second.id),
    }
    assert any(c.tool_name == "snooze_task" and c.status == "requires_confirmation" for c in tool_calls)


async def test_low_confidence_rename_not_found_does_not_call_final_llm_or_claim_done():
    provider = RenameTaskProvider(
        current_title="несуществующая задача",
        new_title="новое название",
        confidence=0.7,
    )
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await TaskService(session).create_task(user, title="Другая задача")

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=46,
            text="Переименуй несуществующую задачу в «новое название»",
        )

    assert provider.final_chat_calls == 0
    assert "Готово" not in result.reply_text
    assert result.reply_text == "Не нашёл активную задачу «несуществующая задача». Уточни название."


async def test_news_digest_tool_starts_one_off_run_without_scheduled_task(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    async def fake_enqueue_job(job_name, *args, **kwargs):
        calls.append((job_name, args, kwargs))
        return "job-1"

    from lumi.assistant import orchestrator as orchestrator_module
    from lumi.services.news import NewsService

    monkeypatch.setattr(orchestrator_module, "enqueue_job", fake_enqueue_job)
    provider = AgentPlannerProvider({
        "mode": "tool_calls",
        "tool_calls": [
            {
                "name": "news_digest",
                "args": {"topics": ["AI"]},
                "confidence": 0.9,
                "requires_confirmation": False,
            }
        ],
        "should_answer_normally": False,
    })
    async with session_scope() as session:
        user = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        await NewsService(session).create_topic(user, title="AI", query="AI", language="ru")

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=47,
            text="Собери дайджест новостей про AI за последние 24 часа",
        )

        runs = (await session.execute(select(AgentRun))).scalars().all()
        scheduled = (await session.execute(select(ScheduledTask))).scalars().all()

    news_runs = [run for run in runs if run.type == AgentRunType.NEWS_DIGEST]
    assert provider.final_chat_calls == 0
    assert len(news_runs) == 1
    assert scheduled == []
    assert calls and calls[0][0] == "run_news_digest"
    assert result.buttons == []
    assert result.reply_text == "Запустил сбор дайджеста — пришлю результат отдельным сообщением."
