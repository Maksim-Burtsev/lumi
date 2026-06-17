# Context, Memory, and Compaction

## Why stateless

Lumi does not trust the LLM provider to store the conversation. Every call receives a full, freshly assembled context from the database. This provides provider switching without history loss, full budget control, a debuggable prompt (`GET /api/debug/context/latest`), and one source of truth.

## What goes into context (ContextBuilder)

Section order (`backend/src/lumi/assistant/context_builder.py`):

1. **System prompt**: Lumi identity and behavior rules (`prompts.py: LUMI_SYSTEM_PROMPT`)
2. **Runtime**: current date/time in the user's timezone, locale, channel
3. **Profile**: name, username, timezone
4. **Permissions**: what can be automatic and what requires confirmation
5. **Active tasks as current state** (<=15, with overdue items) and **today's calendar**
6. **Email snapshot** (need-reply count) and **active automations**
7. **Relevant memory** (top 10 by score)
8. **Conversation summary** (latest compacted version)
9. **Only current-message action results** ("Created task ...") so the model does not confuse them with active state
10. **Recent messages** (up to 30, within remaining budget)
11. **Current message**

Budget: `LLM_CONTEXT_MAX_CHARS=120000` (~30k tokens, estimated as chars/4). Sections 1-9 are always included; recent-message history is squeezed into the remaining budget.

## Signal extraction

A separate JSON call (`signal_extraction`) runs before the final reply. Schema: tasks, reminders, memory candidates, calendar requests, automations, email/news commands, plus confidence and requires_confirmation for each item. Extraction failure never breaks chat: it only prevents auto-actions. Invalid JSON also has fragment-level salvage.

### Application thresholds (orchestrator)

```text
Task:             confidence >= 0.85 and !requires_confirmation -> create
                  0.50-0.85 -> pending confirmation + buttons
Memory:           explicit "remember this" and >= 0.85 -> store
                  preference/instruction and >= 0.92 + !requires_confirmation -> store
                  otherwise ignore without pending confirmation
Internal block:   explicit request and >= 0.75 -> create
External calendar: ALWAYS pending confirmation
Automation:       >= 0.60 -> pending confirmation (enable only manually)
Email send/delete: not implemented at all
```

## Memory

**Write** (`MemoryService.store_candidate`): normalize -> find duplicate by keyword-overlap >= 0.75 -> update duplicate (importance/confidence) instead of inserting; overlap 0.45-0.75 creates a new row marked `potential_conflict`.

**Read** (`retrieve_relevant`) uses scoring without vectors:

```python
score = importance*3 + keyword_overlap(query, text)*5 + tag_overlap*4
      + recency_boost(last_accessed_at < 7d: +1.5) + kind_boost(instruction 3, preference 2, ...)
```

Top 10 memories enter context; used memories have `last_accessed_at` updated. Memory is not exposed as user navigation in the Mini App; it is an internal part of context. Replacing it with pgvector is one method.

## Compaction

Trigger after reply: more than `COMPACT_AFTER_MESSAGES=80` uncompacted messages beyond the protected 30 most recent messages, or total size > `COMPACT_AFTER_CHARS=160000`. The bot enqueues `compact_conversation`; the user does not wait.

Job: previous summary + old messages -> compaction prompt -> structured text (Summary / Decisions / Preferences / Projects / Open loops / Things to avoid) -> new `conversation_summaries` row (version+1) -> old messages get `is_compacted=true` -> conversation pointers update. The latest 30 messages are never compacted.

## End-to-end example

User: "Remind me tomorrow at 10 to write Sasha"

```text
messages       + role=user "Remind me tomorrow at 10 to write Sasha"
agent_runs     + type=chat, trigger=telegram_message, running
llm_calls      + signal_extraction (mock: 1ms / MiniMax: ~1-2s)
tasks          + "write Sasha", reminder_at=tomorrow 10:00 (user TZ -> UTC)
task_events    + created (actor=agent)
tool_calls     + create_task completed {task_id}
audit_logs     + task created
llm_calls      + final_chat
messages       + role=assistant "Done. Created task..."
agent_runs     -> completed, metadata.context_snapshot = {...}
```

Tomorrow at 10:00, worker-cron `send_due_reminders` finds the task and sends a reminder with action buttons.

## Where to change things

| What | Where |
|---|---|
| Lumi personality/rules | `assistant/prompts.py: LUMI_SYSTEM_PROMPT` |
| Auto-action thresholds | `assistant/orchestrator.py` (constants at the top) |
| Context budgets | `.env`: LLM_CONTEXT_MAX_CHARS, RECENT_MESSAGES_LIMIT, COMPACT_* |
| Memory scoring | `assistant/memory_service.py: retrieve_relevant` |
| Compaction prompt | `assistant/prompts.py: COMPACTION_SYSTEM` |
| Inspect built context | `GET /api/debug/context/latest` (APP_ENV=local only) |
