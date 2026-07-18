from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from lumi.assistant.action_reply_renderer import ActionOutcome, ActionReplyRenderer
from lumi.assistant.command_core import (
    decision_to_agent_plan_data,
    parse_assistant_decision,
)
from lumi.assistant.orchestrator import _with_schedule_read_guard
from lumi.assistant.planner import AgentPlanner
from lumi.assistant.schemas import AgentPlan
from lumi.assistant.tool_registry import TOOL_CATALOG, VISIBLE_COMMAND_NAMES
from lumi.db.models import User
from lumi.evals.assistant_command_core import evaluate_decisions, load_golden_corpus

CORPUS_PATH = Path(__file__).parent / "fixtures" / "assistant_command_golden.json"
REQUIRED_CATEGORIES = {
    "ru",
    "en",
    "mixed",
    "typo",
    "followup",
    "correction",
    "relative_date",
    "ambiguity",
    "multi_intent",
    "unsupported",
    "research",
    "prompt_injection",
}


class ScriptedPlannerLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = 0

    async def complete_json(self, **_kwargs) -> dict:
        self.calls += 1
        return self.response


def _test_user() -> User:
    return User(
        id=uuid.uuid4(),
        telegram_user_id=101,
        timezone="UTC",
        locale="en",
        settings={},
        is_allowed=True,
    )


def test_visible_command_registry_is_narrow_and_hides_internal_operations() -> None:
    assert len(VISIBLE_COMMAND_NAMES) == 14
    assert "resolve_entity" not in VISIBLE_COMMAND_NAMES
    assert "find_focus_slot" not in VISIBLE_COMMAND_NAMES
    assert "resolve_entity" not in TOOL_CATALOG
    assert "find_focus_slot" not in TOOL_CATALOG


def test_command_contract_rejects_unknown_or_extra_fields() -> None:
    with pytest.raises(ValidationError):
        parse_assistant_decision({
            "kind": "commands",
            "language": "en",
            "commands": [{"command": "delete_everything", "args": {}}],
        })
    with pytest.raises(ValidationError):
        parse_assistant_decision({
            "kind": "commands",
            "language": "en",
            "commands": [{
                "command": "create_task",
                "args": {"title": "safe", "shell_command": "rm -rf /"},
            }],
        })


def test_preference_write_requires_explicit_user_request() -> None:
    with pytest.raises(ValidationError):
        parse_assistant_decision({
            "kind": "commands",
            "language": "en",
            "commands": [{
                "command": "manage_preference",
                "args": {"operation": "remember", "text": "prefers mornings"},
            }],
        })


def test_external_calendar_creation_is_forced_to_confirmation() -> None:
    decision = parse_assistant_decision({
        "kind": "commands",
        "language": "en",
        "commands": [{
            "command": "create_calendar_event",
            "args": {
                "destination": "external",
                "title": "Vendor call",
                "start_at_local": "2026-07-19T10:00:00",
                "end_at_local": "2026-07-19T11:00:00",
            },
            "confidence": 0.98,
            "requires_confirmation": False,
        }],
    })

    plan_data = decision_to_agent_plan_data(decision)

    assert plan_data["tool_calls"][0]["name"] == "create_external_calendar_event"
    assert plan_data["tool_calls"][0]["requires_confirmation"] is True


def test_write_command_requires_explicit_sufficient_confidence() -> None:
    base_command = {
        "command": "update_task",
        "args": {
            "task_query": "invoice",
            "updates": {"status": "done"},
        },
    }
    with pytest.raises(ValidationError):
        parse_assistant_decision({
            "kind": "commands",
            "language": "en",
            "commands": [base_command],
        })
    with pytest.raises(ValidationError):
        parse_assistant_decision({
            "kind": "commands",
            "language": "en",
            "commands": [{**base_command, "confidence": 0.2}],
        })


def test_explicit_null_task_updates_survive_compatibility_mapping() -> None:
    decision = parse_assistant_decision({
        "kind": "commands",
        "language": "en",
        "commands": [{
            "command": "update_task",
            "args": {
                "task_query": "invoice",
                "updates": {
                    "description": None,
                    "project": None,
                    "due_at_local": None,
                    "reminder_at_local": None,
                },
            },
            "confidence": 0.98,
        }],
    })

    plan_data = decision_to_agent_plan_data(decision)

    assert plan_data["tool_calls"][0]["args"]["updates"] == {
        "description": None,
        "project": None,
        "due_at_local": None,
        "reminder_at_local": None,
    }


def test_private_note_keeps_recent_calendar_reference() -> None:
    decision = parse_assistant_decision({
        "kind": "commands",
        "language": "en",
        "commands": [{
            "command": "update_calendar_event",
            "args": {
                "operation": "private_note",
                "recency_hint": "last_touched_calendar_event",
                "private_note": "Bring the revised budget.",
            },
            "confidence": 0.98,
        }],
    })

    plan_data = decision_to_agent_plan_data(decision)

    assert plan_data["tool_calls"][0]["name"] == "update_calendar_private_note"
    assert plan_data["tool_calls"][0]["args"]["recency_hint"] == (
        "last_touched_calendar_event"
    )


def test_plan_day_keeps_the_explicit_local_date() -> None:
    decision = parse_assistant_decision({
        "kind": "commands",
        "language": "en",
        "commands": [{
            "command": "plan_day",
            "args": {"date_local": "2035-07-12"},
            "confidence": 0.98,
        }],
    })

    plan_data = decision_to_agent_plan_data(decision)

    assert plan_data["tool_calls"][0]["args"]["date_local"] == "2035-07-12"


def test_legacy_plan_contract_remains_compatible() -> None:
    plan = AgentPlan.model_validate({
        "mode": "tool_calls",
        "tool_calls": [{"name": "complete_task", "args": {"task_query": "invoice"}}],
    })

    assert plan.command_core is False
    assert plan.tool_calls[0].name == "complete_task"


@pytest.mark.asyncio
async def test_live_planner_rejects_legacy_model_output_unless_explicitly_enabled() -> None:
    response = {
        "mode": "tool_calls",
        "tool_calls": [{"name": "update_settings", "args": {"locale": "ru"}}],
    }

    strict = await AgentPlanner(llm=ScriptedPlannerLLM(response)).plan(
        user=_test_user(),
        text="change settings",
    )
    replay = await AgentPlanner(
        llm=ScriptedPlannerLLM(response),
        allow_legacy_agent_plans=True,
    ).plan(
        user=_test_user(),
        text="replay fixture",
    )

    assert strict.tool_calls == []
    assert strict.mode == "final_answer"
    assert strict.command_core is True
    assert replay.tool_calls[0].name == "update_settings"


@pytest.mark.asyncio
async def test_strict_validation_failure_cannot_become_a_regex_calendar_command() -> None:
    plan = await AgentPlanner(
        llm=ScriptedPlannerLLM({"mode": "final_answer"}),
    ).plan(
        user=_test_user(),
        text="what is on my calendar tomorrow?",
    )

    guarded = _with_schedule_read_guard(
        _test_user(),
        "what is on my calendar tomorrow?",
        plan,
    )

    assert guarded.command_core is True
    assert guarded.mode == "final_answer"
    assert guarded.tool_calls == []


def test_deterministic_action_reply_uses_backend_facts() -> None:
    rendered = ActionReplyRenderer.render_deterministic(
        user=_test_user(),
        planner_language="ru",
        outcomes=[
            ActionOutcome(
                action_type="create_task",
                status="completed",
                fallback_text="Created task",
                title="Сверить договор",
                project="Работа",
                button_keys=["task_done", "task_snooze"],
            )
        ],
    )

    assert rendered is not None
    assert rendered.message == "Создана задача: «Сверить договор» в проекте Работа"
    assert rendered.button_labels == {
        "task_done": "✓ Выполнено",
        "task_snooze": "⏰ Отложить",
    }


@pytest.mark.asyncio
async def test_golden_corpus_passes_offline_command_gates() -> None:
    cases = load_golden_corpus(CORPUS_PATH)
    assert len(cases) >= 40
    assert REQUIRED_CATEGORIES <= {str(case.get("category")) for case in cases}

    decisions = []
    latencies_ms: list[float] = []
    for case in cases:
        response = case["output"]
        llm = ScriptedPlannerLLM(response)
        planner = AgentPlanner(llm=llm)  # type: ignore[arg-type]
        started = time.perf_counter()
        plan = await planner.plan(
            user=_test_user(),
            text=str(case["message"]),
            known_context="sanitized deterministic fixture",
        )
        latencies_ms.append((time.perf_counter() - started) * 1000)
        decision = parse_assistant_decision(response)
        decisions.append(decision)

        expected_mode = {
            "commands": "tool_calls",
            "final": "final_answer",
            "ask": "ask_user",
            "denied": "out_of_scope",
        }[case["expected_kind"]]
        assert llm.calls == 1
        assert plan.command_core is True
        assert plan.mode == expected_mode
        assert len(plan.tool_calls) == len(case.get("expected") or [])

    report = evaluate_decisions(
        cases=cases,
        decisions=decisions,
        latencies_ms=latencies_ms,
    )

    assert report.unexpected_writes == 0
    assert report.fake_successes == 0
    assert report.write_intent_precision == 1.0
    assert report.critical_intent_args_accuracy >= 0.95
    assert report.ambiguity_guesses == 0
    assert report.p95_latency_ms < report.provider_target_p95_ms
