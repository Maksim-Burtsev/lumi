"""AgentPlanner: fast JSON router from user message to backend tool calls."""

from __future__ import annotations

import json
import uuid
from typing import Any

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
        self.last_trace: dict[str, Any] = {}

    async def plan(
        self,
        *,
        user: User,
        text: str,
        known_context: str | None = None,
        media_context: MediaUnderstanding | None = None,
        available_media: list[MediaCandidate] | None = None,
        tool_observations: list[dict[str, Any]] | None = None,
        loop_step: int = 1,
        remaining_steps: int | None = None,
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
        observations_block = ""
        if tool_observations:
            bounded_observations = tool_observations[-8:]
            observations_block = (
                "\n\ntool_observations:\n"
                f"{json.dumps(bounded_observations, ensure_ascii=False, indent=2)[:6000]}\n"
                "Use these observations as the current backend state. Choose the next valid tool "
                "or a final/ask_user answer. Do not repeat a read-only tool unless it is still needed. "
                "If the user requested creating or scheduling something and the observations contain "
                "enough local times/title/duration to do it, choose the write tool next. Use ask_user "
                "only when a required detail is still missing or the write would be unsafe."
            )
        loop_block = (
            f"\nLoop step: {max(1, loop_step)}"
            + (f"\nRemaining model steps: {remaining_steps}" if remaining_steps is not None else "")
        )
        user_content = (
            f"Current datetime: {now_local.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            f"Timezone: {user.timezone}\n"
            f"Known user context: {known_context or '—'}\n\n"
            f"{TOOL_CATALOG}\n\n"
            f"Message: {text}\n"
            f"{loop_block}"
            f"{observations_block}"
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
            self.last_trace = _planner_trace(
                raw=None,
                plan=AgentPlan.empty(),
                validation_status="llm_error",
                validation_error=str(exc),
                media_context=media_context,
                available_media=available_media,
            )
            return AgentPlan.empty()

        try:
            if _looks_like_legacy_signals(raw):
                plan = _signals_to_plan(ExtractedSignals.model_validate(raw))
                self.last_trace = _planner_trace(
                    raw=raw,
                    plan=plan,
                    validation_status="legacy_validated",
                    media_context=media_context,
                    available_media=available_media,
                )
                return plan
            plan = AgentPlan.model_validate(raw)
            self.last_trace = _planner_trace(
                raw=raw,
                plan=plan,
                validation_status="validated",
                media_context=media_context,
                available_media=available_media,
            )
            return plan
        except Exception as plan_exc:
            if _looks_like_legacy_signals(raw):
                try:
                    plan = _signals_to_plan(ExtractedSignals.model_validate(raw))
                    self.last_trace = _planner_trace(
                        raw=raw,
                        plan=plan,
                        validation_status="legacy_validated_after_error",
                        validation_error=str(plan_exc),
                        media_context=media_context,
                        available_media=available_media,
                    )
                    return plan
                except Exception as exc:  # noqa: BLE001
                    plan_exc = exc
            log.warning("agent planner validation failed", fields={"error": str(plan_exc)[:300]})
            self.last_trace = _planner_trace(
                raw=raw,
                plan=AgentPlan.empty(),
                validation_status="validation_error",
                validation_error=str(plan_exc),
                media_context=media_context,
                available_media=available_media,
            )
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


def _short_text(value: str, *, limit: int = 500) -> str:
    value = " ".join(value.split()).strip()
    return value[:limit]


def _sanitize_raw_plan(value: object, *, depth: int = 0) -> object:
    if depth >= 5:
        return "..."
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 40:
                sanitized["..."] = "truncated"
                break
            sanitized[str(key)[:80]] = _sanitize_raw_plan(item, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_raw_plan(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return _short_text(value, limit=1000)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _short_text(str(value), limit=500)


def _planner_trace(
    *,
    raw: object,
    plan: AgentPlan,
    validation_status: str,
    media_context: MediaUnderstanding | None,
    available_media: list[MediaCandidate] | None,
    validation_error: str | None = None,
) -> dict[str, Any]:
    return {
        "has_media_context": media_context is not None,
        "available_media_count": len(available_media or []),
        "validation_status": validation_status,
        "validation_error": _short_text(validation_error, limit=800) if validation_error else None,
        "mode": plan.mode,
        "tool_names": [call.name for call in plan.tool_calls],
        "tool_count": len(plan.tool_calls),
        "final_answer_present": bool(plan.final_answer),
        "user_visible_status": _short_text(plan.user_visible_status, limit=120)
        if plan.user_visible_status else None,
        "progress_kind": plan.progress_kind,
        "raw_plan_sanitized": _sanitize_raw_plan(raw),
    }


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
