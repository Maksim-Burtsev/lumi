from __future__ import annotations

import os

import pytest

from lumi.db.models import TaskStatus

from .assistant_cases import ASSISTANT_CORE_CASES
from .helpers.assistant_flow import AssistantCase, run_assistant_case


def _selected_areas() -> set[str] | None:
    raw = os.environ.get("ASSISTANT_CORE_AREA", "").strip()
    if not raw:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


@pytest.mark.parametrize("case", ASSISTANT_CORE_CASES, ids=[case.id for case in ASSISTANT_CORE_CASES])
async def test_assistant_core_flow(case: AssistantCase):
    selected = _selected_areas()
    if selected is not None and case.area not in selected:
        pytest.skip(f"case area {case.area!r} not selected")

    result = await run_assistant_case(case)
    actual_tools = [(call.tool_name, call.status) for call in result.tool_calls]

    for expected in case.expected_tools:
        assert (expected.name, expected.status) in actual_tools
    for forbidden in case.forbidden_tools:
        assert all(call.tool_name != forbidden for call in result.tool_calls)
    if case.expected_pending_confirmations is not None:
        assert len(result.pending_confirmations) == case.expected_pending_confirmations
    if case.expected_buttons is not None:
        assert bool(result.buttons_count) is case.expected_buttons
    if case.expected_loop_stop_reason:
        assert result.agent_run is not None
        assert result.agent_run.metadata_["loop_trace"]["stop_reason"] == case.expected_loop_stop_reason

    for expected in case.expected_tasks:
        matches = [task for task in result.tasks if expected.title_contains.casefold() in task.title.casefold()]
        assert matches, f"task containing {expected.title_contains!r} not found"
        if expected.project is not None:
            assert any(task.project == expected.project for task in matches)
        if expected.status is not None:
            expected_status = TaskStatus(expected.status)
            assert any(task.status == expected_status for task in matches)

    for reply_expectation in case.reply:
        if reply_expectation.contains is not None:
            assert reply_expectation.contains in result.reply_text
        if reply_expectation.not_contains is not None:
            assert reply_expectation.not_contains not in result.reply_text
