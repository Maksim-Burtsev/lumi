"""Agent-facing backend tool catalog.

The planner sees this compact catalog on every chat turn. Domain data is loaded
only after a matching tool call passes validation/policy.
"""

from __future__ import annotations

TOOL_NAMES = {
    "create_task",
    "read_tasks",
    "rename_task",
    "complete_task",
    "snooze_task",
    "store_memory",
    "plan_day",
    "find_focus_slot",
    "create_internal_calendar_block",
    "create_external_calendar_event",
    "create_automation",
    "email_triage",
    "news_digest",
}

TOOL_CATALOG = """Available backend tools:
- create_task(title, description?, priority?, project?, tags?, due_at_local?, reminder_at_local?)
- read_tasks(filter?: all|today|upcoming|inbox|done, limit?)
- rename_task(current_title|task_query, new_title, project?, tags?)
- complete_task(task_query|current_title, project?, tags?)
- snooze_task(task_query|current_title, preset?: 1h|3h|tomorrow|next_week, project?, tags?)
- store_memory(kind, text, importance?)
- plan_day()
- find_focus_slot(title?, duration_minutes?, time_window_local?)
- create_internal_calendar_block(title, start_at_local, end_at_local)
- create_external_calendar_event(title, start_at_local, end_at_local)
- create_automation(type, title, cron_expression, timezone?, config?)
- email_triage(time_window?)
- news_digest(topics?)

Rules:
- Return tool calls as JSON only. Do not claim that a tool was executed.
- Do not request domain lists up front. The backend loads relevant data after a tool call.
- For action-only commands set should_answer_normally=false.
- For ordinary chat or questions without needed tools use mode=final_answer or ask_user.
"""


AGENT_PLANNER_SCHEMA_HINT = {
    "mode": "final_answer|tool_calls|ask_user",
    "tool_calls": [
        {
            "name": "one of the Available backend tools",
            "args": {"key": "value"},
            "confidence": 0.0,
            "requires_confirmation": False,
        }
    ],
    "final_answer": "string|null",
    "should_answer_normally": "boolean",
    "language": "ru|en|other",
}
