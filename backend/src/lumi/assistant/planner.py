"""AgentPlanner: fast JSON router from user message to backend tool calls."""

from __future__ import annotations

import json
import uuid
from typing import Any

from lumi.assistant.command_core import decision_to_agent_plan_data, parse_assistant_decision
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
    def __init__(
        self,
        llm: LLMGateway | None = None,
        *,
        allow_legacy_agent_plans: bool | None = None,
    ) -> None:
        self.llm = llm or LLMGateway()
        self.allow_legacy_agent_plans = (
            bool(getattr(self.llm, "allow_legacy_agent_plans", False))
            if allow_legacy_agent_plans is None
            else allow_legacy_agent_plans
        )
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
            f"{observations_block}\n\n"
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
            if _looks_like_legacy_signals(raw) and self.allow_legacy_agent_plans:
                plan = _signals_to_plan(ExtractedSignals.model_validate(raw))
                self.last_trace = _planner_trace(
                    raw=raw,
                    plan=plan,
                    validation_status="legacy_validated",
                    media_context=media_context,
                    available_media=available_media,
                )
                return plan
            if _looks_like_command_decision(raw):
                decision = parse_assistant_decision(raw)
                plan = AgentPlan.model_validate(decision_to_agent_plan_data(decision))
                validation_status = "command_core_validated"
            elif self.allow_legacy_agent_plans:
                # Explicit compatibility for persisted/scripted test replays.
                # Live model output is never allowed through this branch.
                plan = AgentPlan.model_validate(raw)
                validation_status = "legacy_plan_validated"
            else:
                raise ValueError("strict AssistantDecision output required")
            self.last_trace = _planner_trace(
                raw=raw,
                plan=plan,
                validation_status=validation_status,
                media_context=media_context,
                available_media=available_media,
            )
            return plan
        except Exception as plan_exc:
            if _looks_like_legacy_signals(raw) and self.allow_legacy_agent_plans:
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
            fallback_plan = AgentPlan(command_core=not self.allow_legacy_agent_plans)
            self.last_trace = _planner_trace(
                raw=raw,
                plan=fallback_plan,
                validation_status="validation_error",
                validation_error=str(plan_exc),
                media_context=media_context,
                available_media=available_media,
            )
            return fallback_plan


def _looks_like_legacy_signals(raw: object) -> bool:
    return isinstance(raw, dict) and any(
        key in raw for key in (
            "tasks",
            "task_updates",
            "memory_candidates",
            "calendar_requests",
        )
    )


def _looks_like_command_decision(raw: object) -> bool:
    return isinstance(raw, dict) and raw.get("kind") in {"commands", "final", "ask", "denied"}


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
        "command_core": plan.command_core,
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
    for calendar_request in signals.calendar_requests:
        calls.append(PlannedToolCall(
            name={
                "plan_day": "plan_day",
                "find_focus_slot": "find_focus_slot",
                "create_internal_block": "create_internal_calendar_block",
                "create_external_event": "create_external_calendar_event",
            }[calendar_request.kind],
            args=calendar_request.model_dump(mode="json", exclude={"kind"}),
            confidence=calendar_request.confidence,
            requires_confirmation=calendar_request.requires_confirmation,
        ))
    return AgentPlan(
        mode="tool_calls" if calls else "final_answer",
        tool_calls=calls,
        should_answer_normally=signals.should_answer_normally,
        language=signals.language,
    )
