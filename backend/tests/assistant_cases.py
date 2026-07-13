from __future__ import annotations

from typing import Final

from .helpers.assistant_flow import (
    AssistantCase,
    ReplyExpectation,
    TaskExpectation,
    ToolExpectation,
    future_local_at,
)


def tool_plan(name: str, args: dict, *, confidence: float = 0.95) -> dict:
    return {
        "mode": "tool_calls",
        "tool_calls": [{"name": name, "args": args, "confidence": confidence}],
        "should_answer_normally": False,
        "user_visible_status": "Working on it...",
        "progress_kind": "writing",
    }


def final_answer(text: str) -> dict:
    return {
        "mode": "final_answer",
        "tool_calls": [],
        "final_answer": text,
        "should_answer_normally": True,
        "progress_kind": "answering",
    }


def out_of_scope() -> dict:
    return {
        "mode": "out_of_scope",
        "tool_calls": [],
        "should_answer_normally": False,
        "progress_kind": "answering",
    }


ASSISTANT_CORE_CASES: Final[tuple[AssistantCase, ...]] = (
    AssistantCase(
        id="task_create_project_en",
        area="task",
        message="Add a task in the Home project to schedule the annual HVAC service.",
        plans=(tool_plan("create_task", {"title": "schedule the annual HVAC service", "project": "Home"}),),
        expected_tools=(ToolExpectation("create_task"),),
        expected_tasks=(TaskExpectation("HVAC service", project="Home", status="active"),),
        reply=(ReplyExpectation(contains="HVAC service"),),
    ),
    AssistantCase(
        id="task_update_exact_title_en",
        area="task",
        seed="task_project",
        message="Move the Q3 budget review task to the Finance project.",
        plans=(tool_plan("update_task", {"task_query": "Q3 budget review", "updates": {"project": "Finance"}}),),
        expected_tools=(ToolExpectation("update_task"),),
        expected_tasks=(TaskExpectation("Q3 budget review", project="Finance", status="active"),),
    ),
    AssistantCase(
        id="task_ambiguous_confirmation_en",
        area="task",
        seed="task_candidates",
        message="Move the onboarding task to the People Ops project.",
        plans=(tool_plan("update_task", {"task_query": "onboarding", "updates": {"project": "People Ops"}}),),
        expected_tools=(ToolExpectation("update_task", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
        reply=(ReplyExpectation(contains="Found several matching tasks"),),
    ),
    AssistantCase(
        id="task_missing_safe_reply_en",
        area="task",
        message="Mark the non-existent vendor invoice task as done.",
        plans=(tool_plan("complete_task", {"task_query": "non-existent vendor invoice"}),),
        expected_tools=(ToolExpectation("complete_task", status="skipped"),),
        expected_pending_confirmations=0,
        reply=(ReplyExpectation(not_contains="Done"),),
    ),
    AssistantCase(
        id="task_bulk_confirmation_en",
        area="task",
        seed="task_candidates",
        message="Move all onboarding tasks from Work to People Ops.",
        plans=(
            tool_plan(
                "bulk_update_tasks",
                {"task_query": "onboarding", "from_project": "Work", "updates": {"project": "People Ops"}},
            ),
        ),
        expected_tools=(ToolExpectation("bulk_update_tasks", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
    ),
    AssistantCase(
        id="calendar_read_tomorrow_en",
        area="calendar",
        seed="calendar_busy",
        message="What meetings do I have tomorrow?",
        plans=(
            tool_plan(
                "read_calendar_events",
                {
                    "start_at_local": future_local_at(0, days=1).isoformat(),
                    "end_at_local": future_local_at(0, days=2).isoformat(),
                    "include_details": True,
                    "sync_if_needed": False,
                },
            ),
        ),
        expected_tools=(ToolExpectation("read_calendar_events"),),
        reply=(ReplyExpectation(contains="Client check-in"),),
    ),
    AssistantCase(
        id="calendar_update_internal_block_en",
        area="calendar",
        seed="calendar_gym_block",
        message="Move my gym block by 30 minutes.",
        plans=(tool_plan("update_calendar_event", {"event_query": "gym block", "shift_minutes": 30}),),
        expected_tools=(ToolExpectation("update_calendar_event"),),
        reply=(ReplyExpectation(contains="gym block"),),
    ),
    AssistantCase(
        id="calendar_external_create_confirmation_en",
        area="calendar",
        message="Create an external calendar event for the vendor kickoff tomorrow from 10 to 11.",
        plans=(
            tool_plan(
                "create_external_calendar_event",
                {
                    "title": "vendor kickoff",
                    "start_at_local": future_local_at(10).isoformat(),
                    "end_at_local": future_local_at(11).isoformat(),
                },
            ),
        ),
        expected_tools=(ToolExpectation("create_external_calendar_event", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
    ),
    AssistantCase(
        id="memory_store_preference_en",
        area="memory",
        message="Remember that I prefer short daily planning summaries.",
        plans=(
            tool_plan(
                "store_memory",
                {"kind": "preference", "text": "I prefer short daily planning summaries.", "importance": 4},
            ),
        ),
        expected_tools=(ToolExpectation("store_memory"),),
        reply=(ReplyExpectation(contains="short daily planning summaries"),),
    ),
    AssistantCase(
        id="memory_read_existing_en",
        area="memory",
        seed="memory",
        message="What do you remember about my planning preferences?",
        plans=(tool_plan("read_memories", {"query": "planning summaries", "limit": 5}),),
        expected_tools=(ToolExpectation("read_memories"),),
        reply=(ReplyExpectation(contains="short daily planning summaries"),),
    ),
    AssistantCase(
        id="ordinary_question_no_tools_en",
        area="chat",
        message="What can you help me with?",
        plans=(final_answer("I can help with tasks, calendar planning, memory, and daily planning."),),
        forbidden_tools=("create_task", "update_task", "read_calendar_events"),
        reply=(ReplyExpectation(contains="tasks"),),
    ),
    AssistantCase(
        id="research_out_of_scope_en",
        area="chat",
        message="Research the latest AI agent news and summarize it for me.",
        plans=(out_of_scope(),),
        forbidden_tools=("create_task", "store_memory", "read_calendar_events"),
        reply=(ReplyExpectation(contains="outside Lumi's scope"),),
    ),
    AssistantCase(
        id="task_create_project_ru_multilingual",
        area="task",
        message="Добавь задачу в проект Дом: заказать фильтры для воды",
        plans=(tool_plan("create_task", {"title": "заказать фильтры для воды", "project": "Дом"}),),
        expected_tools=(ToolExpectation("create_task"),),
        expected_tasks=(TaskExpectation("фильтры для воды", project="Дом", status="active"),),
        reply=(ReplyExpectation(contains="фильтры для воды"),),
    ),
)


ASSISTANT_TOOL_COVERAGE: Final[dict[str, str]] = {
    "create_task": "assistant-core:task_create_project_en",
    "read_tasks": "existing:test_orchestrator",
    "update_task": "assistant-core:task_update_exact_title_en",
    "bulk_update_tasks": "assistant-core:task_bulk_confirmation_en",
    "rename_task": "existing:test_orchestrator",
    "complete_task": "assistant-core:task_missing_safe_reply_en",
    "snooze_task": "existing:test_orchestrator",
    "resolve_entity": "existing:test_orchestrator",
    "store_memory": "assistant-core:memory_store_preference_en",
    "read_memories": "assistant-core:memory_read_existing_en",
    "update_memory": "existing:test_orchestrator",
    "delete_memory": "existing:test_orchestrator",
    "plan_day": "existing:worker/planning tests",
    "find_focus_slot": "existing:test_orchestrator",
    "read_calendar_events": "assistant-core:calendar_read_tomorrow_en",
    "create_internal_calendar_block": "existing:test_orchestrator",
    "update_calendar_event": "assistant-core:calendar_update_internal_block_en",
    "cancel_calendar_event": "existing:test_orchestrator",
    "update_calendar_private_note": "existing:test_calendar_private_notes",
    "delete_calendar_private_note": "existing:test_calendar_private_notes",
    "create_external_calendar_event": "assistant-core:calendar_external_create_confirmation_en",
    "read_settings": "existing:test_orchestrator",
    "update_settings": "existing:test_orchestrator",
    "read_connectors": "existing:test_orchestrator",
}
