from sqlalchemy import select

from lumi.assistant.media import ImageInput
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
from lumi.llm.base import LLMResponse, content_to_text
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


def _test_image(**overrides) -> ImageInput:
    data = {
        "data": b"image-bytes",
        "mime_type": "image/png",
        "file_id": "telegram-file",
        "file_unique_id": "telegram-unique",
        "file_size": 11,
        "source": "attached",
        "telegram_message_id": 3,
    }
    data.update(overrides)
    return ImageInput(**data)


class MediaFlowProvider:
    name = "media-flow"
    model = "media-flow-1"

    def __init__(
        self,
        *,
        media: dict,
        plan: dict | list[dict],
        media_reference: dict | None = None,
        focused: dict | None = None,
        final_text: str = "final answer",
    ) -> None:
        self.media = media
        self.plans = list(plan) if isinstance(plan, list) else [plan]
        self.media_reference = media_reference or {}
        self.focused = focused or {}
        self.final_text = final_text
        self.calls: list[str] = []
        self.planner_prompts: list[str] = []
        self.final_chat_calls = 0

    async def complete_json(self, **kwargs) -> dict:
        request_kind = kwargs["request_kind"]
        self.calls.append(request_kind)
        messages = kwargs.get("messages") or []
        if request_kind == "media_understanding":
            assert isinstance(messages[-1].content, list)
            return self.media
        if request_kind == "agent_planner":
            prompt = (kwargs.get("system") or "") + "\n" + content_to_text(messages[-1].content)
            self.planner_prompts.append(prompt)
            return self.plans.pop(0)
        if request_kind == "media_reference":
            return self.media_reference
        if request_kind == "focused_vision":
            assert isinstance(messages[-1].content, list)
            return self.focused
        raise AssertionError(f"unexpected JSON request_kind: {request_kind}")

    async def complete(self, **kwargs) -> LLMResponse:
        request_kind = kwargs["request_kind"]
        self.calls.append(request_kind)
        if request_kind == "final_chat":
            self.final_chat_calls += 1
        return LLMResponse(
            text=self.final_text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=len(self.final_text),
        )


MEDIA_CAT = {
    "summary": "На фото рыжий кот на диване.",
    "visible_text": [],
    "entities": [],
    "action_relevant_facts": [],
    "instruction_like_text": [],
    "confidence": 0.9,
    "limitations": [],
}


SERIAL_MEDIA = {
    "summary": "Наклейка Acer, серийный номер обведен красным.",
    "visible_text": [
        "Aspire 5742G-374G50Mnkk",
        "S/N:LXRJ00C058135065891601",
        "SNID : 13502599316",
    ],
    "entities": [
        {
            "type": "other",
            "label": "serial number (S/N)",
            "value": "LXRJ00C058135065891601",
            "evidence": "S/N line circled in red",
            "confidence": 0.99,
        },
    ],
    "action_relevant_facts": [
        "Serial number (S/N) highlighted in red: LXRJ00C058135065891601",
        "SNID: 13502599316",
    ],
    "instruction_like_text": [],
    "confidence": 0.99,
    "limitations": [],
}


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


async def test_image_only_chat_sends_image_to_final_reply_without_side_effects():
    provider = MockLLMProvider()
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=3,
            text="",
            image=_test_image(),
        )
        assert result.reply_text

    async with session_scope() as session:
        assert (await session.execute(select(Task))).scalars().all() == []
        messages = (await session.execute(select(Message))).scalars().all()
        inbound = next(m for m in messages if m.role == MessageRole.USER)
        assert inbound.metadata_["images"][0]["file_id"] == "telegram-file"
        assert "data" not in inbound.metadata_["images"][0]
        assert [c["request_kind"] for c in provider.calls] == ["media_understanding", "agent_planner"]


async def test_image_only_chat_answers_with_media_summary_without_final_chat():
    provider = MediaFlowProvider(
        media=MEDIA_CAT,
        plan={
            "mode": "final_answer",
            "visual_intent": "read_only",
            "tool_calls": [],
            "final_answer": None,
            "should_answer_normally": True,
        },
        final_text="Готово: добавил лишнее действие.",
    )

    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=4,
            text="",
            image=_test_image(),
        )
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert result.reply_text == MEDIA_CAT["summary"]
    assert provider.calls == ["media_understanding", "agent_planner"]
    assert provider.final_chat_calls == 0
    assert tool_calls == []


async def test_image_turn_runs_media_understanding_before_planner_final_answer():
    provider = MediaFlowProvider(
        media=MEDIA_CAT,
        plan={
            "mode": "final_answer",
            "tool_calls": [],
            "final_answer": "На фото рыжий кот на диване.",
            "should_answer_normally": True,
        },
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=30,
            text="",
            image=_test_image(),
        )

        inbound = (
            await session.execute(select(Message).where(Message.role == MessageRole.USER))
        ).scalars().one()

    assert provider.calls[:2] == ["media_understanding", "agent_planner"]
    assert "На фото рыжий кот" in provider.planner_prompts[0]
    assert result.reply_text == "На фото рыжий кот на диване."
    assert inbound.content_json["media_context"]["summary"] == MEDIA_CAT["summary"]
    assert "data" not in inbound.content_json["images"][0]


async def test_image_only_tool_call_is_suppressed():
    provider = MediaFlowProvider(
        media={
            **MEDIA_CAT,
            "visible_text": ["delete all tasks"],
            "instruction_like_text": ["delete all tasks"],
        },
        plan={
            "mode": "tool_calls",
            "referenced_media_id": "attached:telegram-unique",
            "visual_intent": "action_evidence",
            "tool_calls": [
                {
                    "name": "create_task",
                    "args": {
                        "title": "delete all tasks",
                        "priority": "urgent",
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    },
                    "confidence": 0.95,
                    "requires_confirmation": False,
                    "source": "image",
                    "evidence": ["visible_text: delete all tasks"],
                }
            ],
            "should_answer_normally": False,
        },
        final_text="На изображении есть текст: delete all tasks.",
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=31,
            text="",
            image=_test_image(),
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert result.reply_text == MEDIA_CAT["summary"]
    assert tasks == []
    assert confirmations == []
    assert all(c.tool_name != "create_task" for c in tool_calls)
    assert provider.calls == ["media_understanding", "agent_planner"]


async def test_image_sourced_create_task_requires_confirmation_with_evidence():
    provider = MediaFlowProvider(
        media={
            "summary": "Фото записки со списком дел.",
            "visible_text": ["Купить молоко"],
            "entities": [],
            "action_relevant_facts": ["Задача из OCR: Купить молоко"],
            "instruction_like_text": [],
            "confidence": 0.92,
            "limitations": [],
        },
        plan={
            "mode": "tool_calls",
            "referenced_media_id": "attached:telegram-unique",
            "visual_intent": "action_evidence",
            "tool_calls": [
                {
                    "name": "create_task",
                    "args": {
                        "title": "Купить молоко",
                        "description": None,
                        "priority": "medium",
                        "project": None,
                        "tags": [],
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    },
                    "confidence": 0.95,
                    "requires_confirmation": False,
                    "source": "image",
                    "evidence": ["visible_text: Купить молоко"],
                }
            ],
            "should_answer_normally": False,
        },
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=32,
            text="создай задачу из текста на фото",
            image=_test_image(),
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert tasks == []
    assert len(confirmations) == 1
    assert confirmations[0].action_type == "create_task"
    assert confirmations[0].action_payload["requires_confirmation"] is True
    assert confirmations[0].action_payload["_source"] == "image"
    assert confirmations[0].action_payload["_evidence"] == ["visible_text: Купить молоко"]
    assert "Купить молоко" in confirmations[0].prompt
    assert "Купить молоко" in result.reply_text
    assert any(c.tool_name == "create_task" and c.status == "requires_confirmation" for c in tool_calls)


async def test_visual_read_only_question_answers_from_media_context_and_suppresses_tools():
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan={
            "mode": "tool_calls",
            "referenced_media_id": "attached:telegram-unique",
            "visual_intent": "read_only",
            "tool_calls": [
                {
                    "name": "create_task",
                    "args": {
                        "title": "В Lumi добавить проекты",
                        "confidence": 0.95,
                        "requires_confirmation": False,
                    },
                    "confidence": 0.95,
                    "requires_confirmation": False,
                    "source": "text",
                    "evidence": [],
                }
            ],
            "final_answer": "LXRJ00C058135065891601",
            "should_answer_normally": False,
        },
        final_text="Готово: добавил «В Lumi добавить проекты» в проект Lumi.",
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=36,
            text="send only what is circled in red",
            image=_test_image(),
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.calls == ["media_understanding", "agent_planner"]
    assert provider.final_chat_calls == 0
    assert result.reply_text == "LXRJ00C058135065891601"
    assert tasks == []
    assert confirmations == []
    assert tool_calls == []


async def test_visual_read_only_without_planner_answer_uses_focused_vision_not_final_chat():
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan={
            "mode": "final_answer",
            "referenced_media_id": "attached:telegram-unique",
            "visual_intent": "none",
            "tool_calls": [],
            "final_answer": None,
            "should_answer_normally": True,
        },
        focused={
            "answer": "LXRJ00C058135065891601",
            "facts": ["serial: LXRJ00C058135065891601"],
            "visible_text": ["S/N:LXRJ00C058135065891601"],
            "confidence": 0.95,
            "limitations": [],
        },
        final_text="Готово: добавил «В Lumi добавить проекты» в проект Lumi.",
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=361,
            text="какой серийник выделен красным на фото?",
            image=_test_image(),
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()
        inbound = (
            await session.execute(select(Message).where(Message.role == MessageRole.USER))
        ).scalars().one()

    assert provider.calls == ["media_understanding", "agent_planner", "focused_vision"]
    assert provider.final_chat_calls == 0
    assert result.reply_text == "LXRJ00C058135065891601"
    assert tasks == []
    assert tool_calls == []
    assert inbound.content_json["focused_vision"]["request"]["question"] == (
        "какой серийник выделен красным на фото?"
    )


async def test_text_followup_uses_llm_selected_recent_media_without_keyword_heuristics():
    image_metadata = {
        "file_id": "recent-file",
        "file_unique_id": "telegram-unique",
        "mime_type": "image/png",
        "file_size": 100,
        "source": "attached",
        "telegram_message_id": 30,
    }
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan={
            "mode": "final_answer",
            "referenced_media_id": "recent:telegram-unique",
            "visual_intent": "read_only",
            "tool_calls": [],
            "final_answer": "LXRJ00C058135065891601",
            "should_answer_normally": False,
        },
    )
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(user)
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content="[image] serial sticker",
            char_count=22,
            metadata_={"images": [image_metadata], "media_context": SERIAL_MEDIA},
            content_json={"text": "", "images": [image_metadata], "media_context": SERIAL_MEDIA},
        ))
        await session.flush()

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=37,
            text="envía solo lo marcado en rojo",
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.calls == ["agent_planner"]
    assert "available_media" in provider.planner_prompts[0]
    assert "recent:telegram-unique" in provider.planner_prompts[0]
    assert "Serial number (S/N) highlighted in red: LXRJ00C058135065891601" in provider.planner_prompts[0]
    assert result.reply_text == "LXRJ00C058135065891601"
    assert tasks == []
    assert tool_calls == []


async def test_text_followup_accepts_router_media_id_with_different_source_prefix():
    image_metadata = {
        "file_id": "recent-file",
        "file_unique_id": "telegram-unique",
        "mime_type": "image/png",
        "file_size": 100,
        "source": "attached",
        "telegram_message_id": 30,
    }
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan={
            "mode": "final_answer",
            "visual_intent": "none",
            "tool_calls": [],
            "final_answer": None,
            "should_answer_normally": True,
        },
        media_reference={
            "references_media": True,
            "media_id": "attached:telegram-unique9",
            "visual_intent": "read_only",
            "question": "read the text marked in red",
            "reason": "The user asks for the marked visual detail from the recent image.",
            "confidence": 0.86,
        },
        focused={
            "answer": "LXRJ00C058135065891601",
            "facts": ["serial: LXRJ00C058135065891601"],
            "visible_text": ["S/N:LXRJ00C058135065891601"],
            "confidence": 0.95,
            "limitations": [],
        },
        final_text="Готово: добавил «В Lumi добавить проекты» в проект Lumi.",
    )

    async def image_loader(metadata: dict) -> ImageInput:
        return _test_image(
            file_id=metadata["file_id"],
            file_unique_id=metadata["file_unique_id"],
            source="latest",
        )

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(user)
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content="[image] serial sticker",
            char_count=22,
            metadata_={"images": [image_metadata], "media_context": SERIAL_MEDIA},
            content_json={"text": "", "images": [image_metadata], "media_context": SERIAL_MEDIA},
        ))
        await session.flush()

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=38,
            text="send only what is marked in red",
            image_loader=image_loader,
        )
        inbound = (
            await session.execute(select(Message).where(Message.telegram_message_id == 38))
        ).scalars().one()

    assert provider.calls == ["agent_planner", "media_reference", "focused_vision"]
    assert provider.final_chat_calls == 0
    assert result.reply_text == "LXRJ00C058135065891601"
    assert inbound.content_json["referenced_images"][0]["file_id"] == "recent-file"


async def test_text_followup_uses_media_router_when_planner_does_not_select_recent_media():
    image_metadata = {
        "file_id": "recent-file",
        "file_unique_id": "telegram-unique",
        "mime_type": "image/png",
        "file_size": 100,
        "source": "attached",
        "telegram_message_id": 30,
    }
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan={
            "mode": "final_answer",
            "visual_intent": "none",
            "tool_calls": [],
            "final_answer": None,
            "should_answer_normally": True,
        },
        media_reference={
            "references_media": True,
            "media_id": "recent:telegram-unique",
            "visual_intent": "read_only",
            "question": "read the text marked in red",
            "reason": "The user asks for the marked visual detail from the recent image.",
            "confidence": 0.86,
        },
        focused={
            "answer": "LXRJ00C058135065891601",
            "facts": ["serial: LXRJ00C058135065891601"],
            "visible_text": ["S/N:LXRJ00C058135065891601"],
            "confidence": 0.95,
            "limitations": [],
        },
        final_text="Готово: добавил «В Lumi добавить проекты» в проект Lumi.",
    )
    loaded_metadata: list[dict] = []

    async def image_loader(metadata: dict) -> ImageInput:
        loaded_metadata.append(metadata)
        return _test_image(
            file_id=metadata["file_id"],
            file_unique_id=metadata["file_unique_id"],
            source="latest",
        )

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(user)
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content="[image] serial sticker",
            char_count=22,
            metadata_={"images": [image_metadata], "media_context": SERIAL_MEDIA},
            content_json={"text": "", "images": [image_metadata], "media_context": SERIAL_MEDIA},
        ))
        await session.flush()

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=38,
            text="envía solo lo marcado en rojo",
            image_loader=image_loader,
        )

        tool_calls = (await session.execute(select(ToolCall))).scalars().all()
        inbound = (
            await session.execute(select(Message).where(Message.telegram_message_id == 38))
        ).scalars().one()

    assert provider.calls == ["agent_planner", "media_reference", "focused_vision"]
    assert provider.final_chat_calls == 0
    assert result.reply_text == "LXRJ00C058135065891601"
    assert loaded_metadata and loaded_metadata[0]["file_id"] == "recent-file"
    assert tool_calls == []
    assert inbound.content_json["referenced_images"][0]["file_id"] == "recent-file"
    assert inbound.content_json["media_context"]["summary"] == SERIAL_MEDIA["summary"]
    assert inbound.content_json["focused_vision"]["request"]["question"] == "read the text marked in red"


async def test_recent_media_can_be_downloaded_for_llm_requested_focused_vision():
    image_metadata = {
        "file_id": "recent-file",
        "file_unique_id": "telegram-unique",
        "mime_type": "image/png",
        "file_size": 100,
        "source": "attached",
        "telegram_message_id": 30,
    }
    provider = MediaFlowProvider(
        media=SERIAL_MEDIA,
        plan=[
            {
                "mode": "needs_media_understanding",
                "referenced_media_id": "recent:telegram-unique",
                "visual_intent": "read_only",
                "tool_calls": [],
                "needs_media_understanding": True,
                "should_answer_normally": False,
            },
            {
                "mode": "needs_focused_vision",
                "referenced_media_id": "recent:telegram-unique",
                "visual_intent": "read_only",
                "tool_calls": [],
                "focused_vision": {
                    "question": "read the text circled in red",
                    "reason": "needs exact OCR",
                    "confidence": 0.9,
                },
                "should_answer_normally": False,
            },
        ],
        focused={
            "answer": "LXRJ00C058135065891601",
            "facts": ["serial: LXRJ00C058135065891601"],
            "visible_text": ["S/N:LXRJ00C058135065891601"],
            "confidence": 0.95,
            "limitations": [],
        },
    )
    loaded_metadata: list[dict] = []

    async def image_loader(metadata: dict) -> ImageInput:
        loaded_metadata.append(metadata)
        return _test_image(
            file_id=metadata["file_id"],
            file_unique_id=metadata["file_unique_id"],
            source="recent",
            telegram_message_id=metadata["telegram_message_id"],
        )

    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(TEST_TELEGRAM_ID)
        conversation = await users.ensure_main_conversation(user)
        session.add(Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.USER,
            content="[image]",
            char_count=7,
            metadata_={"images": [image_metadata]},
            content_json={"text": "", "images": [image_metadata]},
        ))
        await session.flush()

        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=38,
            text="send only what is circled in red",
            image_loader=image_loader,
        )
        inbound = (
            await session.execute(
                select(Message).where(
                    Message.role == MessageRole.USER,
                    Message.telegram_message_id == 38,
                )
            )
        ).scalars().one()
        tasks = (await session.execute(select(Task))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert loaded_metadata == [image_metadata]
    assert provider.calls == ["agent_planner", "media_understanding", "agent_planner", "focused_vision"]
    assert result.reply_text == "LXRJ00C058135065891601"
    assert inbound.content_json["referenced_images"][0]["file_id"] == "recent-file"
    assert inbound.content_json["media_context"]["summary"] == SERIAL_MEDIA["summary"]
    assert inbound.content_json["focused_vision"]["request"]["question"] == "read the text circled in red"
    assert tasks == []
    assert tool_calls == []


async def test_focused_vision_mode_sends_image_only_for_second_narrow_call():
    provider = MediaFlowProvider(
        media={
            "summary": "Фото устройства, мелкий текст неразборчив.",
            "visible_text": [],
            "entities": [],
            "action_relevant_facts": [],
            "instruction_like_text": [],
            "confidence": 0.6,
            "limitations": ["мелкий текст в правом нижнем углу не извлечен"],
        },
        plan={
            "mode": "needs_focused_vision",
            "tool_calls": [],
            "focused_vision": {
                "question": "прочитай мелкий серийный номер в правом нижнем углу",
                "reason": "media_context не содержит этот OCR",
                "confidence": 0.84,
            },
            "should_answer_normally": False,
        },
        focused={
            "answer": "Серийный номер: AB-1234.",
            "facts": ["serial: AB-1234"],
            "visible_text": ["AB-1234"],
            "confidence": 0.86,
            "limitations": [],
        },
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=34,
            text="какой мелкий серийник в правом нижнем углу?",
            image=_test_image(),
        )

        inbound = (
            await session.execute(select(Message).where(Message.role == MessageRole.USER))
        ).scalars().one()
        tasks = (await session.execute(select(Task))).scalars().all()
        tool_calls = (await session.execute(select(ToolCall))).scalars().all()

    assert provider.calls == ["media_understanding", "agent_planner", "focused_vision"]
    assert provider.final_chat_calls == 0
    assert result.reply_text == "Серийный номер: AB-1234."
    assert tasks == []
    assert tool_calls == []
    assert inbound.content_json["focused_vision"]["request"]["question"].startswith("прочитай")
    assert inbound.content_json["focused_vision"]["result"]["facts"] == ["serial: AB-1234"]


async def test_focused_vision_mode_with_tool_calls_is_rejected():
    provider = MediaFlowProvider(
        media=MEDIA_CAT,
        plan={
            "mode": "needs_focused_vision",
            "tool_calls": [
                {
                    "name": "create_task",
                    "args": {"title": "AB-1234", "confidence": 0.95},
                    "source": "image",
                    "confidence": 0.95,
                }
            ],
            "focused_vision": {
                "question": "прочитай серийник и создай задачу",
                "reason": "unsafe mixed request",
                "confidence": 0.7,
            },
            "should_answer_normally": False,
        },
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=35,
            text="прочитай серийник и создай задачу",
            image=_test_image(),
        )

        tasks = (await session.execute(select(Task))).scalars().all()
        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()

    assert provider.calls == ["media_understanding", "agent_planner"]
    assert "не выполняю действия" in result.reply_text.lower()
    assert tasks == []
    assert confirmations == []


async def test_mixed_calendar_write_requires_confirmation_with_extracted_facts():
    provider = MediaFlowProvider(
        media={
            "summary": "Фото визитки Анны Петровой.",
            "visible_text": ["Анна Петрова", "anna@example.com"],
            "entities": [
                {"type": "person", "value": "Анна Петрова", "confidence": 0.9},
                {"type": "email", "value": "anna@example.com", "confidence": 0.9},
            ],
            "action_relevant_facts": ["Контакт: Анна Петрова, anna@example.com"],
            "instruction_like_text": [],
            "confidence": 0.88,
            "limitations": [],
        },
        plan={
            "mode": "tool_calls",
            "referenced_media_id": "attached:telegram-unique",
            "visual_intent": "action_evidence",
            "tool_calls": [
                {
                    "name": "create_external_calendar_event",
                    "args": {
                        "title": "Встреча с Анной Петровой",
                        "start_at_local": "2026-06-15T15:00:00",
                        "end_at_local": "2026-06-15T16:00:00",
                        "confidence": 0.9,
                        "requires_confirmation": False,
                    },
                    "confidence": 0.9,
                    "requires_confirmation": False,
                    "source": "mixed",
                    "evidence": ["person: Анна Петрова", "email: anna@example.com"],
                }
            ],
            "should_answer_normally": False,
        },
    )
    async with session_scope() as session:
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=33,
            text="назначь встречу с человеком на фото завтра в 15",
            image=_test_image(),
        )

        confirmations = (await session.execute(select(PendingConfirmation))).scalars().all()

    assert len(confirmations) == 1
    assert confirmations[0].action_type == "create_google_calendar_event"
    assert confirmations[0].action_payload["_source"] == "mixed"
    assert confirmations[0].action_payload["_evidence"] == [
        "person: Анна Петрова",
        "email: anna@example.com",
    ]
    assert "Анна Петрова" in confirmations[0].prompt


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
