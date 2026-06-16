"""Agent-facing backend tool catalog.

The planner sees this compact catalog on every chat turn. Domain data is loaded
only after a matching tool call passes validation/policy.
"""

from __future__ import annotations

TOOL_NAMES = {
    "create_task",
    "read_tasks",
    "update_task",
    "bulk_update_tasks",
    "rename_task",
    "complete_task",
    "snooze_task",
    "store_memory",
    "plan_day",
    "find_focus_slot",
    "read_calendar_events",
    "create_internal_calendar_block",
    "create_external_calendar_event",
    "create_automation",
    "email_triage",
    "news_digest",
    "set_language",
}

TOOL_CATALOG = """Available backend tools:
- create_task(title, description?, priority?, project?, tags?, due_at_local?, reminder_at_local?)
- read_tasks(filter?: all|today|upcoming|inbox|done, limit?)
- update_task(task_id? | task_query? | recency_hint?: last_created_task|last_touched_task, updates={project?, title?, description?, tags?, priority?})
- bulk_update_tasks(task_query?, from_project?, from_tags?, status?: open|all, limit?, updates={project?, description?, tags?, tags_add?, tags_remove?, priority?, status?})
- rename_task(current_title|task_query, new_title, project?, tags?)  # project/tags here are search filters, not update targets
- complete_task(task_query|current_title, project?, tags?)
- snooze_task(task_query|current_title, preset?: 1h|3h|tomorrow|next_week, project?, tags?)
- store_memory(kind, text, importance?)
- plan_day()
- find_focus_slot(title?, duration_minutes?, time_window_local?)
- read_calendar_events(start_at_local, end_at_local, include_details?, sync_if_needed?)
- create_internal_calendar_block(title, start_at_local, end_at_local)
- create_external_calendar_event(title, start_at_local, end_at_local)
- create_automation(type, title, cron_expression, timezone?, config?)
- email_triage(time_window?)
- news_digest(topics?)
- set_language(app_locale?: en|ru, reply_language_mode?: auto|app_locale)

Rules:
- Return tool calls as JSON only. Do not claim that a tool was executed.
- Do not request domain lists up front. The backend loads relevant data after a tool call.
- Any user request to create, read, update, complete, or snooze Lumi-managed state must use mode=tool_calls.
- For task project/tags/priority/description changes, use update_task. Do not use rename_task to set a project.
- For changes to several tasks at once (all tasks matching a query, all tasks in a project/tag, move everything related to a project), use bulk_update_tasks. Backend will ask for confirmation before changing multiple tasks.
- Delete/remove task requests should set updates.status="cancelled"; never physically delete tasks.
- Calendar questions about meetings/events on today, tomorrow, a future date, or a recurring date must use read_calendar_events with the requested local time window.
- For short follow-ups to recent backend task actions, use recency_hint=last_created_task or last_touched_task from Planner context.
- Do not resolve ambiguous task matches yourself. If the user intent is a task update and Planner context has multiple plausible candidates, still call update_task with task_query; backend will ask with confirmation buttons.
- Choose tools semantically across languages, typos, punctuation, quotes, emotional phrasing, and short follow-ups.
- For action-only commands set should_answer_normally=false.
- For ordinary chat or questions without needed tools use mode=final_answer or ask_user.
- If the user asks to change the app language, interface language, bot language,
  reply language, or to return replies to automatic language matching, use set_language.
  app_locale controls Mini App UI. reply_language_mode=auto means match each message;
  reply_language_mode=app_locale means always reply using the app language.
- If the user refers to media, set referenced_media_id to one available_media id.
- available_media is listed newest-first. For an elliptical follow-up, prefer the first matching media item.
- Use visual_intent=read_only for visual questions. Use visual_intent=action_evidence only for explicit backend actions based on media.
- For visual detail missing from media_context use mode=needs_media_understanding or mode=needs_focused_vision.
- For image-derived arguments set source=image or source=mixed and include evidence.

Examples:
- User asks to create a task with title "Webhook для Lumi на проде" -> mode=tool_calls, create_task(title="Webhook для Lumi на проде"), should_answer_normally=false.
- User asks to attach the recently created task to project "Lumi" -> mode=tool_calls, update_task(recency_hint="last_created_task", updates={"project":"Lumi"}), should_answer_normally=false.
- User asks "Move the notes task to project Lumi" and several active notes tasks exist -> mode=tool_calls, update_task(task_query="notes", updates={"project":"Lumi"}), should_answer_normally=false. Do not ask_user with your own candidate list.
- User asks "все задачи про Lumi из Работа перенеси в Lumi" -> mode=tool_calls, bulk_update_tasks(task_query="Lumi", from_project="Работа", updates={"project":"Lumi"}), should_answer_normally=false.
- User asks "Какие встречи завтра в календаре?" -> mode=tool_calls, read_calendar_events(start_at_local=<tomorrow 00:00>, end_at_local=<next day 00:00>), should_answer_normally=false.
- User asks "what can you do?" -> mode=final_answer, no tool calls.
- User asks to show/open/list Lumi tasks -> mode=tool_calls, read_tasks(...), should_answer_normally=false.
- User asks "Always answer in Russian and switch the app to Russian" -> mode=tool_calls,
  set_language(app_locale="ru", reply_language_mode="app_locale"), should_answer_normally=false.
- User asks "ответы снова авто" -> mode=tool_calls,
  set_language(reply_language_mode="auto"), should_answer_normally=false.
"""


AGENT_PLANNER_SCHEMA_HINT = {
    "mode": "final_answer|tool_calls|ask_user|needs_media_understanding|needs_focused_vision",
    "referenced_media_id": "one available_media media_id, or null",
    "visual_intent": "none|read_only|action_evidence",
    "needs_media_understanding": "boolean",
    "tool_calls": [
        {
            "name": "one of the Available backend tools",
            "args": {"key": "value"},
            "confidence": 0.0,
            "requires_confirmation": False,
            "source": "text|image|mixed",
            "evidence": ["short fact supporting this call"],
        }
    ],
    "focused_vision": "null unless mode=needs_focused_vision; then object with non-empty question, reason, confidence",
    "final_answer": "string|null",
    "should_answer_normally": "boolean",
    "language": "ru|en|other",
}
