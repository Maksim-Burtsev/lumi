from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi.assistant.orchestrator import AssistantOrchestrator
from lumi.db.models import AgentRun, LLMCall, PendingConfirmation, Task, ToolCall, User
from lumi.db.session import session_scope
from lumi.llm.base import LLMResponse, content_to_text
from lumi.llm.gateway import LLMGateway
from lumi.services.users import UserService

from ..conftest import TEST_TELEGRAM_ID


@dataclass(frozen=True)
class ToolExpectation:
    name: str
    status: str = "completed"


@dataclass(frozen=True)
class TaskExpectation:
    title_contains: str
    project: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class ReplyExpectation:
    contains: str | None = None
    not_contains: str | None = None


@dataclass(frozen=True)
class AssistantCase:
    id: str
    area: str
    message: str
    plans: tuple[dict[str, Any], ...]
    expected_tools: tuple[ToolExpectation, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    expected_tasks: tuple[TaskExpectation, ...] = ()
    expected_pending_confirmations: int | None = None
    expected_buttons: bool | None = None
    reply: tuple[ReplyExpectation, ...] = ()
    seed: str | None = None
    expected_loop_stop_reason: str | None = None


@dataclass
class AssistantCaseResult:
    reply_text: str
    buttons_count: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    pending_confirmations: list[PendingConfirmation] = field(default_factory=list)
    agent_run: AgentRun | None = None
    llm_calls: list[LLMCall] = field(default_factory=list)


class ScriptedAssistantProvider:
    name = "assistant-regression"
    model = "scripted-1"

    def __init__(self, plans: tuple[dict[str, Any], ...]) -> None:
        self.plans = list(plans)
        self.final_chat_calls = 0

    async def complete_json(self, **kwargs) -> dict[str, Any]:
        request_kind = kwargs["request_kind"]
        messages = kwargs.get("messages") or []
        prompt = (kwargs.get("system") or "") + "\n" + content_to_text(messages[-1].content)
        if request_kind == "agent_planner":
            if not self.plans:
                raise AssertionError("scripted assistant provider exhausted")
            plan = dict(self.plans.pop(0))
            plan.setdefault("language", _language_from_prompt(prompt))
            return plan
        if request_kind == "action_reply_renderer":
            return _render_action_reply(prompt)
        raise AssertionError(f"unexpected JSON request_kind: {request_kind}")

    async def complete(self, **kwargs) -> LLMResponse:
        self.final_chat_calls += 1
        text = "Понял. Отвечаю без действий." if _last_message_is_ru(kwargs.get("messages") or []) else (
            "Understood. Answering without actions."
        )
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            input_chars=1,
            output_chars=len(text),
        )


def _language_from_prompt(prompt: str) -> str:
    text = prompt
    if "Message:" in prompt:
        text = prompt.split("Message:", 1)[1].split("\n", 1)[0]
    cyrillic = sum(1 for char in text if "\u0400" <= char <= "\u04ff")
    latin = sum(1 for char in text if ("a" <= char.lower() <= "z"))
    return "ru" if cyrillic >= 2 and cyrillic >= latin else "en"


def _last_message_is_ru(messages: list[Any]) -> bool:
    if not messages:
        return False
    text = content_to_text(messages[-1].content)
    return sum(1 for char in text if "\u0400" <= char <= "\u04ff") >= 2


def _renderer_payload(prompt: str) -> dict[str, Any]:
    marker = "payload_json:"
    if marker not in prompt:
        return {}
    return json.loads(prompt.split(marker, 1)[1].strip())


def _render_action_reply(prompt: str) -> dict[str, Any]:
    payload = _renderer_payload(prompt)
    target_language = str(payload.get("target_language") or "en")
    messages: list[str] = []
    labels: dict[str, str] = {}
    for outcome in payload.get("action_outcomes") or []:
        if not isinstance(outcome, dict):
            continue
        fallback = outcome.get("fallback_text")
        if fallback:
            messages.append(str(fallback))
            continue
        title = outcome.get("title")
        action_type = outcome.get("action_type")
        status = outcome.get("status")
        if title and action_type == "create_task" and status == "completed":
            messages.append(f"Создана задача: {title}" if target_language == "ru" else f"Created task: {title}")
        elif title and action_type == "create_task" and status == "requires_confirmation":
            messages.append(
                f"Задача требует подтверждения: {title}"
                if target_language == "ru"
                else f"Task needs confirmation: {title}"
            )
    if target_language == "ru":
        labels = {"confirm": "Подтвердить", "reject": "Не надо"}
    message = "\n".join(messages) if messages else ("Готово." if target_language == "ru" else "Done.")
    return {"message": message, "button_labels": labels}


async def run_assistant_case(case: AssistantCase) -> AssistantCaseResult:
    async with session_scope() as session:
        users = UserService(session)
        user = await users.ensure_user(TEST_TELEGRAM_ID, first_name="Alex", username="alex_planner")
        user.timezone = "America/New_York"
        user.locale = "en"
        user.language_code = "en"
        await users.ensure_main_conversation(user)
        await seed_case(session, user, case.seed)

        provider = ScriptedAssistantProvider(case.plans)
        orchestrator = AssistantOrchestrator(session, llm=LLMGateway(provider))
        result = await orchestrator.handle_user_message(
            telegram_user_id=TEST_TELEGRAM_ID,
            telegram_chat_id=TEST_TELEGRAM_ID,
            telegram_message_id=1000,
            text=case.message,
        )

        return AssistantCaseResult(
            reply_text=result.reply_text,
            buttons_count=sum(len(row) for row in result.buttons),
            tool_calls=list((await session.execute(select(ToolCall).order_by(ToolCall.created_at))).scalars()),
            tasks=list((await session.execute(select(Task).order_by(Task.created_at))).scalars()),
            pending_confirmations=list(
                (await session.execute(select(PendingConfirmation).order_by(PendingConfirmation.created_at)))
                .scalars()
            ),
            agent_run=(await session.execute(select(AgentRun).order_by(AgentRun.created_at.desc()))).scalars().first(),
            llm_calls=list((await session.execute(select(LLMCall).order_by(LLMCall.created_at))).scalars()),
        )


async def seed_case(session: AsyncSession, user: User, seed: str | None) -> None:
    from datetime import datetime, timedelta

    from lumi.assistant.memory_service import MemoryService
    from lumi.db.models import CalendarEventStatus, CalendarSource, MemoryKind, TaskStatus
    from lumi.services.calendar import CalendarService
    from lumi.services.tasks import TaskService
    from lumi.utils.time import local_to_utc

    tasks = TaskService(session)
    calendar = CalendarService(session)
    if seed == "task_candidates":
        await tasks.create_task(user, title="Onboarding checklist", project="Work", actor="user")
        await tasks.create_task(user, title="Onboarding notes", project="Work", actor="user")
    elif seed == "task_project":
        await tasks.create_task(user, title="Q3 budget review", project="Work", actor="user")
    elif seed == "calendar_busy":
        start = local_to_utc(datetime(2026, 6, 30, 14, 0), user.timezone)
        await calendar.create_internal_block(
            user,
            title="Client check-in",
            start_at=start,
            end_at=start + timedelta(hours=1),
            created_by="user",
        )
    elif seed == "calendar_gym_block":
        start = local_to_utc(datetime(2026, 6, 30, 17, 0), user.timezone)
        await calendar.create_internal_block(
            user,
            title="gym block",
            start_at=start,
            end_at=start + timedelta(hours=1),
            created_by="user",
        )
    elif seed == "memory":
        service = MemoryService(session)
        from lumi.assistant.schemas import MemoryCandidate

        await service.store_candidate(
            user,
            MemoryCandidate(
                kind=MemoryKind.PREFERENCE.value,
                text="I prefer short daily planning summaries.",
                importance=4,
            ),
            actor="user",
        )
    elif seed == "external_calendar":
        event = await calendar.create_internal_block(
            user,
            title="Google sync",
            start_at=local_to_utc(datetime(2026, 6, 30, 11, 0), user.timezone),
            end_at=local_to_utc(datetime(2026, 6, 30, 12, 0), user.timezone),
            created_by="sync",
        )
        event.source = CalendarSource.GOOGLE
        event.external_id = "google-1"
        event.status = CalendarEventStatus.CONFIRMED
    elif seed == "done_task":
        task = await tasks.create_task(user, title="Closed report", actor="user")
        task.status = TaskStatus.DONE
    elif seed is None:
        return
    else:
        raise AssertionError(f"unknown assistant regression seed: {seed}")
