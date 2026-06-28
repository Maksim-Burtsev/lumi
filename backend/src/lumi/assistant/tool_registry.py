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
    "resolve_entity",
    "store_memory",
    "read_memories",
    "update_memory",
    "delete_memory",
    "plan_day",
    "find_focus_slot",
    "read_calendar_events",
    "create_internal_calendar_block",
    "update_calendar_event",
    "cancel_calendar_event",
    "create_external_calendar_event",
    "create_automation",
    "read_automations",
    "update_automation",
    "run_automation",
    "email_triage",
    "read_inbox",
    "read_email_thread",
    "create_task_from_email",
    "news_digest",
    "read_news_topics",
    "create_news_topic",
    "update_news_topic",
    "run_news_digest",
    "read_settings",
    "update_settings",
    "read_connectors",
    "set_language",
}

TOOL_CATALOG = """Available backend tools:
- create_task(title, description?, priority?, project?, project_ref?, tags?, due_at_local?, reminder_at_local?)
- read_tasks(filter?: all|today|upcoming|inbox|done, limit?)
- update_task(task_id? | task_query? | recency_hint?: last_created_task|last_touched_task|last_notified_task|replied_task, updates={project?, title?, description?, tags?, priority?, status?, due_at_local?, due_time_local?, reminder_at_local?, reminder_time_local?})
- bulk_update_tasks(task_query?, from_project?, from_tags?, status?: open|all, limit?, updates={project?, description?, tags?, tags_add?, tags_remove?, priority?, status?})
- rename_task(current_title|task_query, new_title, project?, tags?)  # project/tags here are search filters, not update targets
- complete_task(task_query|current_title, project?, tags?)
- snooze_task(task_query|current_title, preset?: 1h|3h|tomorrow|next_week, project?, tags?)
- resolve_entity(query, domains?: tasks|calendar|memories|automations|news|email|settings|connectors[], time_window_local?)
- store_memory(kind, text, importance?)
- read_memories(query?, kind?, limit?)
- update_memory(memory_id, text?, kind?, importance?)
- delete_memory(memory_id)
- plan_day()
- find_focus_slot(title?, duration_minutes?, time_window_local?)
- read_calendar_events(start_at_local, end_at_local, include_details?, sync_if_needed?)
- create_internal_calendar_block(title, start_at_local, end_at_local, description?)
- update_calendar_event(event_id? | event_query? | recency_hint?: last_created_calendar_block|last_touched_calendar_event, start_at_local?, start_time_local?, shift_minutes?, end_at_local?, duration_minutes?, title?, description?)
- cancel_calendar_event(event_id? | event_query? | recency_hint?: last_created_calendar_block|last_touched_calendar_event)
- create_external_calendar_event(title, start_at_local, end_at_local)
- create_automation(type, title, cron_expression, timezone?, config?)
- read_automations(include_system?)
- update_automation(automation_id, title?, cron_expression?, timezone?, enabled?, config?)
- run_automation(automation_id)
- email_triage(time_window?)
- read_inbox(limit?)
- read_email_thread(thread_id)
- create_task_from_email(thread_id, title?)
- news_digest(topics?)
- read_news_topics(include_disabled?)
- create_news_topic(title, query, language?, config?)
- update_news_topic(topic_id, title?, query?, language?, enabled?, config?)
- run_news_digest()
- read_settings()
- update_settings(timezone?, locale?, reply_language_mode?, reply_language?, time_format?)
- read_connectors()
- set_language(app_locale?: en|ru, reply_language_mode?: auto|fixed|app_locale, reply_language?: language tag)

Rules:
- Return tool calls as JSON only. Do not claim that a tool was executed.
- Set user_visible_status on every non-final step: one short line in the user's language,
  max 80 chars, no links, no markdown, no success/completion claims before tools succeed.
- user_visible_status must use the same language as the language field; ignore older chat history language.
- progress_kind is for logs only: understanding, reading_calendar, resolving, writing, or answering.
- Do not request domain lists up front. The backend loads relevant data after a tool call.
- Any user request to create, read, update, complete, or snooze Lumi-managed state must use mode=tool_calls.
- For task project/tags/priority/description changes, use update_task. Do not use rename_task to set a project.
- For create_task, if the user explicitly says to add/create the task in/to/into/a/en/zu a named project
  in any language, set project to that exact project name. Project names are user data; "Lumi" can be
  a project even though it is also the app name.
- For reopening a completed task ("open again", "not done", "верни статус открыто", "она не выполнена"), use update_task with updates.status="active".
- For changing when the user will do a task ("перенеси задачу на 21:00", "move task to 9pm"),
  use update_task with updates.due_time_local="HH:MM" when only time is stated; backend keeps the task date.
- Use updates.due_at_local only when the user gives a full date/time. Use reminder_at_local/reminder_time_local
  only for explicit reminder intent such as "напомни"/"remind me".
- For fuzzy time like "после 14"/"after 2pm", use the earliest concrete time: 14:00.
- For changes to several tasks at once (all tasks matching a query, all tasks in a project/tag, move everything related to a project), use bulk_update_tasks. Backend will ask for confirmation before changing multiple tasks.
- Delete/remove task requests should set updates.status="cancelled"; never physically delete tasks.
- Calendar questions about meetings/events on today, tomorrow, a future date, or a recurring date must use read_calendar_events with the requested local time window.
- Calendar/schedule block update requests ("move block", "перенеси блок", "сдвинь встречу", "убери из расписания")
  must use update_calendar_event or cancel_calendar_event. Do not use read_tasks for schedule blocks.
- If the user says only a name and the name could be both a task and a calendar block, call resolve_entity first;
  backend will ask the user to choose and will not write.
- For "на полчаса"/"by 30 minutes" without "earlier/back", use update_calendar_event(shift_minutes=30).
- For event moves with only a new start time, use start_time_local="HH:MM"; backend preserves the original local date and duration.
- Synced external Google/Yandex calendar events are read-only in chat v1; backend will return unsupported instead of mutating.
- For short follow-ups to recent backend task actions, use recency_hint=last_created_task or last_touched_task from Planner context.
- For short follow-ups to recent calendar blocks, use recency_hint=last_created_calendar_block or last_touched_calendar_event from Planner context.
- For short follow-ups right after a task reminder notification, use recency_hint=last_notified_task.
- If the user replies to a task reminder notification, use recency_hint=replied_task.
- For create_task follow-ups that refer to a recent project, use project_ref=last_task_project,
  last_created_task_project, last_proposed_task_project, or last_touched_task_project.
- Do not resolve ambiguous task matches yourself. If the user intent is a task update and Planner context has multiple plausible candidates, still call update_task with task_query; backend will ask with confirmation buttons.
- Choose tools semantically across languages, typos, punctuation, quotes, emotional phrasing, and short follow-ups.
- For action-only commands set should_answer_normally=false.
- For ordinary chat or questions without needed tools use mode=final_answer or ask_user.
- If the user asks to change the app language, interface language, bot language,
  reply language, or to return replies to automatic language matching, use set_language.
  app_locale controls Mini App UI. reply_language_mode=auto means match each message;
  reply_language_mode=fixed means always reply using reply_language; reply_language may be any normalized
  language tag like it, es, de; reply_language_mode=app_locale means always reply using the app language.
- If the user refers to media, set referenced_media_id to one available_media id.
- available_media is listed newest-first. For an elliptical follow-up, prefer the first matching media item.
- Use visual_intent=read_only for visual questions. Use visual_intent=action_evidence only for explicit backend actions based on media.
- For visual detail missing from media_context use mode=needs_media_understanding or mode=needs_focused_vision.
- For image-derived arguments set source=image or source=mixed and include evidence.

Examples:
- User asks to create a task with title "Webhook для Lumi на проде" -> mode=tool_calls, create_task(title="Webhook для Lumi на проде"), should_answer_normally=false.
- User asks "Aggiungi a Lumi la task scrivere proposta" -> mode=tool_calls, create_task(title="scrivere proposta", project="Lumi"), should_answer_normally=false.
- User asks "E nello stesso progetto aggiungi preparare materiali marketing" -> mode=tool_calls, create_task(title="preparare materiali marketing", project_ref="last_task_project"), should_answer_normally=false.
- User asks "И в тот же проект добавь проработать задачи с маркетингом" -> mode=tool_calls, create_task(title="проработать задачи с маркетингом", project_ref="last_task_project"), should_answer_normally=false.
- User asks to attach the recently created task to project "Lumi" -> mode=tool_calls, update_task(recency_hint="last_created_task", updates={"project":"Lumi"}), should_answer_normally=false.
- User asks "передвинь задачу по X с 10:00 на вечер, 21:00" -> mode=tool_calls, update_task(task_query="X", updates={"due_time_local":"21:00"}), should_answer_normally=false.
- User asks "напомни про задачу по X в 21:00" -> mode=tool_calls, update_task(task_query="X", updates={"reminder_time_local":"21:00"}), should_answer_normally=false.
- User asks right after a reminder "перенеси на субботу днем, где-то после 14" -> mode=tool_calls, update_task(recency_hint="last_notified_task", updates={"due_at_local":"<Saturday>T14:00:00"}), should_answer_normally=false.
- User replies to a task reminder "перенеси на воскресенье после 14" -> mode=tool_calls, update_task(recency_hint="replied_task", updates={"due_at_local":"<Sunday>T14:00:00"}), should_answer_normally=false.
- User asks "Move the notes task to project Lumi" and several active notes tasks exist -> mode=tool_calls, update_task(task_query="notes", updates={"project":"Lumi"}), should_answer_normally=false. Do not ask_user with your own candidate list.
- User asks "все задачи про Lumi из Работа перенеси в Lumi" -> mode=tool_calls, bulk_update_tasks(task_query="Lumi", from_project="Работа", updates={"project":"Lumi"}), should_answer_normally=false.
- User asks "Какие встречи завтра в календаре?" -> mode=tool_calls, read_calendar_events(start_at_local=<tomorrow 00:00>, end_at_local=<next day 00:00>), should_answer_normally=false.
- User asks "перенеси Dalma на полчаса" after a Dalma calendar block exists -> mode=tool_calls,
  update_calendar_event(event_query="Dalma", shift_minutes=30), should_answer_normally=false.
- User asks "убери блок Dalma" -> mode=tool_calls, cancel_calendar_event(event_query="Dalma"), should_answer_normally=false.
- User asks "перенеси dalma на 17:30" and context has both task and calendar block named Dalma -> mode=tool_calls,
  resolve_entity(query="Dalma", domains=["tasks","calendar"]), should_answer_normally=false.
- User asks "what can you do?" -> mode=final_answer, no tool calls.
- User asks to show/open/list Lumi tasks -> mode=tool_calls, read_tasks(...), should_answer_normally=false.
- User asks "Always answer in Russian and switch the app to Russian" -> mode=tool_calls,
  set_language(app_locale="ru", reply_language_mode="app_locale"), should_answer_normally=false.
- User asks "Always answer in Italian" -> mode=tool_calls,
  set_language(reply_language_mode="fixed", reply_language="it"), should_answer_normally=false.
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
    "user_visible_status": "short user-language progress line, max 80 chars, no links/markdown/success claims",
    "progress_kind": "understanding|reading_calendar|resolving|writing|answering|null",
    "should_answer_normally": "boolean",
    "language": "latest user message language tag, e.g. en|ru|it|es|de",
}
