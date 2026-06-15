"""AgentPlanner: fast JSON router from user message to backend tool calls."""

from __future__ import annotations

import uuid

from lumi.assistant.media import MediaCandidate
from lumi.assistant.prompts import AGENT_PLANNER_SYSTEM
from lumi.assistant.schemas import (
    AgentPlan,
    ExtractedSignals,
    MediaUnderstanding,
    PlannedToolCall,
)
from lumi.assistant.tool_registry import AGENT_PLANNER_SCHEMA_HINT, TOOL_CATALOG
from lumi.db.models import User
from lumi.llm.base import LLMMessage
from lumi.llm.gateway import LLMGateway
from lumi.logging import get_logger
from lumi.utils.time import local_now

log = get_logger(__name__)


class AgentPlanner:
    def __init__(self, llm: LLMGateway | None = None) -> None:
        self.llm = llm or LLMGateway()

    async def plan(
        self,
        *,
        user: User,
        text: str,
        known_context: str | None = None,
        media_context: MediaUnderstanding | None = None,
        available_media: list[MediaCandidate] | None = None,
        agent_run_id: uuid.UUID | None = None,
        session=None,
    ) -> AgentPlan:
        now_local = local_now(user.timezone)
        has_user_text = bool(text.strip())
        media_block = ""
        if media_context is not None:
            media_block = (
                "\n\nmedia_context:\n"
                f"User text/caption explicitly present: {'yes' if has_user_text else 'no'}\n"
                f"{media_context.to_prompt_text()}\n"
                "Planner policy: do not choose tools from media_context unless user text/caption "
                "explicitly asks for an action involving the image."
            )
        available_media_block = ""
        if available_media:
            media_lines = "\n".join(media.to_prompt_text() for media in available_media[:5])
            available_media_block = (
                "\n\navailable_media:\n"
                "These are the only media ids you may reference. They are listed newest-first. "
                "If the user refers to an image, set referenced_media_id to one of these ids. "
                "For an elliptical follow-up that does not name another image, prefer the first matching media item. "
                "Decide this semantically in any user language.\n"
                "If has_media_context=yes and it contains enough evidence, answer or plan from it. "
                "If the file is needed, set mode=needs_media_understanding or mode=needs_focused_vision.\n"
                f"{media_lines}"
            )
        user_content = (
            f"Current datetime: {now_local.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"Timezone: {user.timezone}\n"
            f"Known user context: {known_context or '—'}\n\n"
            f"{TOOL_CATALOG}\n\n"
            f"Message: {text}\n"
            f"{media_block}"
            f"{available_media_block}\n\n"
            "Return JSON matching the schema."
        )
        try:
            raw = await self.llm.complete_json(
                messages=[LLMMessage(role="user", content=user_content)],
                system=AGENT_PLANNER_SYSTEM,
                json_schema_hint=AGENT_PLANNER_SCHEMA_HINT,
                request_kind="agent_planner",
                user_id=user.id,
                agent_run_id=agent_run_id,
                session=session,
                temperature=0.0,
                max_tokens=1536,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("agent planner LLM call failed", fields={"error": str(exc)})
            return AgentPlan.empty()

        try:
            if _looks_like_legacy_signals(raw):
                return _signals_to_plan(ExtractedSignals.model_validate(raw))
            return AgentPlan.model_validate(raw)
        except Exception:
            try:
                return _signals_to_plan(ExtractedSignals.model_validate(raw))
            except Exception as exc:  # noqa: BLE001
                log.warning("agent planner validation failed", fields={"error": str(exc)[:300]})
                return AgentPlan.empty()


def _looks_like_legacy_signals(raw: object) -> bool:
    return isinstance(raw, dict) and any(
        key in raw for key in (
            "tasks",
            "task_updates",
            "memory_candidates",
            "calendar_requests",
            "automation_requests",
            "email_requests",
            "news_requests",
        )
    )


def _signals_to_plan(signals: ExtractedSignals) -> AgentPlan:
    calls: list[PlannedToolCall] = []
    for task in signals.tasks:
        calls.append(PlannedToolCall(
            name="create_task",
            args=task.model_dump(mode="json"),
            confidence=task.confidence,
            requires_confirmation=task.requires_confirmation,
        ))
    for update in signals.task_updates:
        calls.append(PlannedToolCall(
            name="rename_task",
            args=update.model_dump(mode="json", exclude={"operation"}),
            confidence=update.confidence,
            requires_confirmation=update.requires_confirmation,
        ))
    for candidate in signals.memory_candidates:
        calls.append(PlannedToolCall(
            name="store_memory",
            args=candidate.model_dump(mode="json"),
            confidence=candidate.confidence,
            requires_confirmation=candidate.requires_confirmation,
        ))
    for request in signals.calendar_requests:
        calls.append(PlannedToolCall(
            name={
                "plan_day": "plan_day",
                "find_focus_slot": "find_focus_slot",
                "create_internal_block": "create_internal_calendar_block",
                "create_external_event": "create_external_calendar_event",
            }[request.kind],
            args=request.model_dump(mode="json", exclude={"kind"}),
            confidence=request.confidence,
            requires_confirmation=request.requires_confirmation,
        ))
    for automation in signals.automation_requests:
        calls.append(PlannedToolCall(
            name="create_automation",
            args=automation.model_dump(mode="json"),
            confidence=automation.confidence,
            requires_confirmation=automation.requires_confirmation,
        ))
    for request in signals.email_requests:
        if request.kind == "triage":
            calls.append(PlannedToolCall(
                name="email_triage",
                args=request.model_dump(mode="json", exclude={"kind"}),
                confidence=request.confidence,
            ))
    for request in signals.news_requests:
        if request.kind == "digest":
            calls.append(PlannedToolCall(
                name="news_digest",
                args=request.model_dump(mode="json", exclude={"kind"}),
                confidence=request.confidence,
            ))

    return AgentPlan(
        mode="tool_calls" if calls else "final_answer",
        tool_calls=calls,
        should_answer_normally=signals.should_answer_normally,
        language=signals.language,
    )
