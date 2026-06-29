from __future__ import annotations

from typing import Final

from .helpers.assistant_flow import AssistantCase, ReplyExpectation, TaskExpectation, ToolExpectation


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


ASSISTANT_CORE_CASES: Final[tuple[AssistantCase, ...]] = (
    AssistantCase(
        id="task_create_project_ru",
        area="task",
        message="Добавь в проект Lumi задачу написать regression pack",
        plans=(tool_plan("create_task", {"title": "написать regression pack", "project": "Lumi"}),),
        expected_tools=(ToolExpectation("create_task"),),
        expected_tasks=(TaskExpectation("regression pack", project="Lumi", status="active"),),
        reply=(ReplyExpectation(contains="regression pack"),),
    ),
    AssistantCase(
        id="task_update_exact_title",
        area="task",
        seed="task_project",
        message="Перенеси Regression draft в проект Lumi",
        plans=(tool_plan("update_task", {"task_query": "Regression draft", "updates": {"project": "Lumi"}}),),
        expected_tools=(ToolExpectation("update_task"),),
        expected_tasks=(TaskExpectation("Regression draft", project="Lumi", status="active"),),
    ),
    AssistantCase(
        id="task_ambiguous_confirmation",
        area="task",
        seed="task_candidates",
        message="Перенеси Dalma в проект Lumi",
        plans=(tool_plan("update_task", {"task_query": "Dalma", "updates": {"project": "Lumi"}}),),
        expected_tools=(ToolExpectation("update_task", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
        reply=(ReplyExpectation(contains="похожих задач"),),
    ),
    AssistantCase(
        id="task_missing_safe_reply",
        area="task",
        message="Закрой задачу Not Existing",
        plans=(tool_plan("complete_task", {"task_query": "Not Existing"}),),
        expected_tools=(ToolExpectation("complete_task", status="skipped"),),
        expected_pending_confirmations=0,
        reply=(ReplyExpectation(not_contains="Готово"),),
    ),
    AssistantCase(
        id="task_bulk_confirmation",
        area="task",
        seed="task_candidates",
        message="Все задачи Dalma перенеси в проект Lumi",
        plans=(tool_plan("bulk_update_tasks", {"task_query": "Dalma", "updates": {"project": "Lumi"}}),),
        expected_tools=(ToolExpectation("bulk_update_tasks", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
    ),
    AssistantCase(
        id="calendar_read_tomorrow",
        area="calendar",
        seed="calendar_busy",
        message="Какие встречи завтра?",
        plans=(
            tool_plan(
                "read_calendar_events",
                {
                    "start_at_local": "2026-06-30T00:00:00",
                    "end_at_local": "2026-07-01T00:00:00",
                    "include_details": True,
                    "sync_if_needed": False,
                },
            ),
        ),
        expected_tools=(ToolExpectation("read_calendar_events"),),
        reply=(ReplyExpectation(contains="Busy block"),),
    ),
    AssistantCase(
        id="calendar_update_internal_block",
        area="calendar",
        seed="calendar_dalma",
        message="Перенеси Dalma на полчаса",
        plans=(tool_plan("update_calendar_event", {"event_query": "Dalma", "shift_minutes": 30}),),
        expected_tools=(ToolExpectation("update_calendar_event"),),
        reply=(ReplyExpectation(contains="Dalma"),),
    ),
    AssistantCase(
        id="calendar_external_create_confirmation",
        area="calendar",
        message="Создай внешнюю встречу Sync завтра с 10 до 11",
        plans=(
            tool_plan(
                "create_external_calendar_event",
                {
                    "title": "Sync",
                    "start_at_local": "2026-06-30T10:00:00",
                    "end_at_local": "2026-06-30T11:00:00",
                },
            ),
        ),
        expected_tools=(ToolExpectation("create_external_calendar_event", status="requires_confirmation"),),
        expected_pending_confirmations=1,
        expected_buttons=True,
    ),
    AssistantCase(
        id="memory_store_preference",
        area="memory",
        message="Запомни, что я люблю короткие ответы",
        plans=(tool_plan("store_memory", {"kind": "preference", "text": "Люблю короткие ответы", "importance": 4}),),
        expected_tools=(ToolExpectation("store_memory"),),
        reply=(ReplyExpectation(contains="Люблю короткие ответы"),),
    ),
    AssistantCase(
        id="memory_read_existing",
        area="memory",
        seed="memory",
        message="Что ты помнишь про формат ответов?",
        plans=(tool_plan("read_memories", {"query": "ответы", "limit": 5}),),
        expected_tools=(ToolExpectation("read_memories"),),
        reply=(ReplyExpectation(contains="короткие ответы"),),
    ),
    AssistantCase(
        id="ordinary_question_no_tools",
        area="chat",
        message="Что ты умеешь?",
        plans=(final_answer("Я могу помогать с задачами, расписанием и памятью."),),
        forbidden_tools=("create_task", "update_task", "read_calendar_events"),
        reply=(ReplyExpectation(contains="задачами"),),
    ),
)


ASSISTANT_TOOL_COVERAGE: Final[dict[str, str]] = {
    "create_task": "assistant-core:task_create_project_ru",
    "read_tasks": "existing:test_orchestrator",
    "update_task": "assistant-core:task_update_exact_title",
    "bulk_update_tasks": "assistant-core:task_bulk_confirmation",
    "rename_task": "existing:test_orchestrator",
    "complete_task": "assistant-core:task_missing_safe_reply",
    "snooze_task": "existing:test_orchestrator",
    "resolve_entity": "existing:test_orchestrator",
    "store_memory": "assistant-core:memory_store_preference",
    "read_memories": "assistant-core:memory_read_existing",
    "update_memory": "existing:test_orchestrator",
    "delete_memory": "existing:test_orchestrator",
    "plan_day": "existing:worker/planning tests",
    "find_focus_slot": "existing:test_orchestrator",
    "read_calendar_events": "assistant-core:calendar_read_tomorrow",
    "create_internal_calendar_block": "existing:test_orchestrator",
    "update_calendar_event": "assistant-core:calendar_update_internal_block",
    "cancel_calendar_event": "existing:test_orchestrator",
    "update_calendar_private_note": "existing:test_calendar_private_notes",
    "delete_calendar_private_note": "existing:test_calendar_private_notes",
    "create_external_calendar_event": "assistant-core:calendar_external_create_confirmation",
    "create_automation": "existing:test_orchestrator",
    "read_automations": "existing:test_orchestrator",
    "update_automation": "existing:test_orchestrator",
    "run_automation": "existing:test_orchestrator",
    "email_triage": "existing:worker/email flow",
    "read_inbox": "existing:test_orchestrator",
    "read_email_thread": "existing:test_orchestrator",
    "create_task_from_email": "existing:test_orchestrator",
    "news_digest": "existing:test_news_service",
    "read_news_topics": "existing:test_orchestrator",
    "create_news_topic": "existing:test_orchestrator",
    "update_news_topic": "existing:test_orchestrator",
    "run_news_digest": "existing:test_orchestrator",
    "read_settings": "existing:test_orchestrator",
    "update_settings": "existing:test_orchestrator",
    "read_connectors": "existing:test_orchestrator",
}
