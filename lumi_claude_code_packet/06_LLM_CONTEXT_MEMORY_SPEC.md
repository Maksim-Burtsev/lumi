# Lumi — LLM Context, Memory and Compaction Spec

## Core decision

Use **stateless LLM calls**.

Lumi must not rely on a persistent conversation/thread stored by MiniMax or any LLM provider.

Backend stores all state and sends a freshly built context on every call.

## User/conversation model

For MVP:

```text
1 allowlisted Telegram user
→ 1 main conversation in Lumi DB
→ many messages
→ many agent_runs
→ many scheduled jobs
→ many tasks/memories/calendar/email/news objects
```

Background jobs are not separate user-facing chats. They are `agent_runs` linked to the same user.

Examples:

```text
chat_run
scheduled_news_run
email_triage_run
calendar_planning_run
task_review_run
compaction_run
```

## ContextBuilder budget

MiniMax M3 supports very large context, but Lumi should not send huge context by default.

Default budgets:

```text
normal chat: 20k–60k tokens equivalent
email triage: 50k–120k tokens equivalent
news digest: 60k–200k tokens equivalent
very long document mode: not in MVP
```

Implementation can estimate token count by chars / 4. Use char budget for simplicity:

```text
LLM_CONTEXT_MAX_CHARS=120000
RECENT_MESSAGES_LIMIT=30
COMPACT_AFTER_MESSAGES=80
COMPACT_AFTER_CHARS=160000
SUMMARY_TARGET_CHARS=12000
```

## Context sections

Every final assistant call should have this shape.

### System prompt

```text
Ты Lumi — персональный AI-ассистент пользователя в Telegram.

Твоя задача — помогать пользователю держать в порядке задачи, календарь, почту, новости и личный контекст.
Ты не просто отвечаешь на вопросы: ты аккуратно ведешь дела пользователя, предлагаешь действия, создаешь задачи и напоминания, помогаешь планировать день и объясняешь, что сделал.

Правила поведения:
- Отвечай на русском, если пользователь пишет на русском.
- Будь кратким, точным и полезным.
- Не перегружай пользователя длинными объяснениями без необходимости.
- Если действие уже выполнено backend-системой, явно скажи, что сделано.
- Если действие требует подтверждения, не утверждай, что оно выполнено.
- Не выдумывай состояние задач, календаря, почты или новостей. Используй только контекст, который тебе передан.
- Если информации не хватает, задай короткий уточняющий вопрос.
- Не обещай отправить email, удалить email, изменить внешний календарь или выполнить рискованное действие без явного подтверждения пользователя.
- Не раскрывай внутренние technical/debug details пользователю без запроса.
- Пользователь — backend-разработчик; технические объяснения можно давать структурно, но в обычном режиме будь ассистентом, а не документацией.
```

### Runtime metadata

```text
Current datetime: 2026-06-10 09:15
Timezone: Europe/Moscow
User locale: ru
Channel: telegram_private_chat
```

### User profile

```text
User:
- Name: ...
- Telegram username: ...
- Timezone: ...
- Preferences: ...
```

### Permissions

```text
Permissions:
- Can create internal Lumi tasks automatically when user intent is clear.
- Can create internal reminders automatically when user intent is clear.
- Can store non-sensitive memory when user explicitly says “запомни” or intent is very clear.
- Must ask confirmation before writing to external Google Calendar.
- Must ask confirmation before sending, deleting, archiving, or modifying email.
- Must never access local filesystem/shell as a tool.
```

### Active state

```text
Active tasks:
- [high] Архитектура Lumi — due today 18:00
- [medium] Ответить Саше по договору — reminder tomorrow 09:00

Calendar today:
- 10:00–11:00 Standup
- 13:00–14:00 Product sync
- 16:00–16:30 1:1

Recent email triage:
- 3 messages need reply
- 1 invoice/document

Active automations:
- daily news digest weekdays 08:30
- email triage weekdays 09:00
```

### Relevant memories

Retrieve memories using keyword/importance/recency scoring.

```text
Relevant memory:
- Пользователь предпочитает утренние дайджесты до 09:30.
- Рабочие задачи лучше группировать по проектам.
- Для внешних календарей пользователь хочет подтверждение перед записью.
```

### Conversation summary

```text
Conversation summary:
Пользователь проектирует Lumi — личного AI-ассистента в Telegram. Было решено: Python backend, FastAPI, aiogram polling, MiniMax M3, stateless LLM context, Postgres, Redis, Docker Compose, Mini App React/Vite. MVP включает задачи, календарь, новости, email triage, automations, memory.
```

### Recent messages

Last 10–30 messages, depending on budget.

### Action results

```text
Backend actions already performed for this message:
- Created task: “Написать Саше по договору”, reminder tomorrow 09:00.
- Created pending confirmation: “Поставить focus block 15:30–17:00 во внешний Google Calendar”.
```

### Current message

The current user message.

## Signal extraction prompt

System:

```text
Ты модуль структурного извлечения сигналов для AI-ассистента Lumi.
Твоя задача — прочитать сообщение пользователя и вернуть только валидный JSON.
Не отвечай пользователю. Не добавляй markdown. Не добавляй комментарии.

Извлекай:
- задачи;
- напоминания;
- календарные запросы;
- настройки автоматизаций;
- memory candidates;
- команды на почту/новости;
- необходимость подтверждения.

Не создавай действия из слабых формулировок.
Если пользователь говорит “надо бы”, “как-нибудь”, “может быть” — confidence ниже и requires_confirmation=true.
Если действие внешнее или потенциально рискованное — requires_confirmation=true.
```

User content should include:

```text
Current datetime: ...
Timezone: ...
Known user context: ...
Message: ...

Return JSON matching this schema:
...
```

Schema:

```json
{
  "language": "ru|en|other",
  "intents": ["create_task", "create_reminder", "plan_day", "email_triage", "news_digest", "create_automation", "store_memory", "chat"],
  "tasks": [
    {
      "title": "string",
      "description": "string|null",
      "due_at_local": "YYYY-MM-DDTHH:MM:SS|null",
      "reminder_at_local": "YYYY-MM-DDTHH:MM:SS|null",
      "priority": "low|medium|high|urgent",
      "project": "string|null",
      "tags": ["string"],
      "confidence": 0.0,
      "requires_confirmation": true
    }
  ],
  "memory_candidates": [
    {
      "kind": "preference|fact|project|instruction|workflow|other",
      "text": "string",
      "importance": 1,
      "confidence": 0.0,
      "requires_confirmation": true
    }
  ],
  "calendar_requests": [
    {
      "kind": "find_focus_slot|create_internal_block|create_external_event|plan_day",
      "title": "string|null",
      "duration_minutes": 60,
      "start_at_local": "YYYY-MM-DDTHH:MM:SS|null",
      "end_at_local": "YYYY-MM-DDTHH:MM:SS|null",
      "time_window_local": {"start": "YYYY-MM-DDTHH:MM:SS", "end": "YYYY-MM-DDTHH:MM:SS"},
      "requires_confirmation": true,
      "confidence": 0.0
    }
  ],
  "automation_requests": [
    {
      "type": "news_digest|email_triage|daily_planning|calendar_sync|task_review|custom_prompt",
      "title": "string",
      "cron_expression": "string|null",
      "timezone": "string|null",
      "config": {},
      "requires_confirmation": true,
      "confidence": 0.0
    }
  ],
  "email_requests": [
    {"kind": "triage|summarize|find", "time_window": "string|null", "confidence": 0.0}
  ],
  "news_requests": [
    {"kind": "digest|add_topic", "topics": ["string"], "confidence": 0.0}
  ],
  "should_answer_normally": true
}
```

## Applying extracted signals

Rules:

```text
Task auto-create:
  confidence >= 0.85 and requires_confirmation=false

Reminder auto-create:
  confidence >= 0.85 and clear reminder_at

Memory auto-store:
  if user explicitly says “запомни” and confidence >= 0.85
  OR if kind=preference/instruction and confidence >= 0.92
  otherwise pending confirmation or ignore

External calendar write:
  always pending confirmation

Email modify/send:
  always pending confirmation, and MVP may respond “подготовлю черновик позже” if not implemented

Automation create/update:
  confidence >= 0.9 can create disabled pending confirmation
  user must confirm enablement
```

## Memory retrieval MVP

No vector DB required.

Implement scoring:

```python
score = 0
score += importance * 3
score += keyword_overlap(query, memory.text) * 5
score += tag_overlap(query, memory.tags) * 4
score += recency_boost(memory.last_accessed_at)
score += kind_boost
```

Return top 8–12 active memories.

Update `last_accessed_at` when memory is used in context.

## Memory deduplication

Before storing memory:

1. Normalize text lower-case.
2. Search existing active memories for high textual overlap.
3. If duplicate, update importance/confidence/source instead of inserting.
4. If contradiction detected, create new memory but mark metadata `potential_conflict=true` and surface in Memory page.

## Compaction

Compaction should run after reply or scheduled job, not block user response unless necessary.

Trigger when:

```text
conversation has more than COMPACT_AFTER_MESSAGES uncompacted old messages
OR uncompacted old messages char_count > COMPACT_AFTER_CHARS
```

Do not compact last 30 messages.

Compaction input:

- previous summary if any;
- old messages from last compact boundary to cutoff;
- important tool/action results.

Compaction output:

```text
- stable user preferences;
- active projects discussed;
- decisions made;
- unresolved tasks/questions;
- relevant facts for future conversations;
- things not to remember;
- concise chronological summary.
```

Compaction prompt:

```text
Ты модуль сжатия истории для Lumi.
Сожми старую историю диалога так, чтобы будущий ассистент понял важный контекст без чтения всех сообщений.
Не добавляй фактов, которых нет в истории.
Сохрани решения, предпочтения, активные задачи, открытые вопросы, важные ограничения.
Не сохраняй одноразовые детали, если они больше не нужны.
Верни структурированный текст на русском.
```

Output format:

```text
## Summary
...

## Decisions
- ...

## User preferences
- ...

## Active projects
- ...

## Open loops
- ...

## Things to avoid
- ...
```

After compaction:

- insert `conversation_summaries`;
- mark compacted messages `is_compacted=true` except recent protected messages;
- update conversation `summary_current_id` and `compacted_until_message_id`.

## Final assistant response prompt

System prompt as above.

Developer/context message:

```text
Ниже передан backend-контекст. Считай его источником правды. Если чего-то нет в контексте, не выдумывай.
```

Then structured context.

User message as latest user role.

Assistant output should be natural text for Telegram.

## JSON robustness

LLMs sometimes return invalid JSON. Implement:

1. Strip markdown fences.
2. Extract first JSON object substring.
3. Parse via `json.loads`.
4. Validate Pydantic model.
5. On failure: log and continue without extracted actions.

## LLM call logging

For each call store:

- provider;
- model;
- request_kind;
- status;
- char/token estimates;
- latency;
- error.

Do not store raw prompts unless `STORE_LLM_DEBUG_PAYLOADS=true`.

## Fallback behavior

If MiniMax call fails:

- For chat: save user message, return friendly failure.
- For extraction: skip extraction, continue final response.
- For compaction: mark job failed, retry later.
- For digest/planning: mark agent_run failed and optionally notify user.

## Mock LLM provider

Must support deterministic local tests.

Examples:

- If input contains `напомни`, mock returns task extraction.
- If request_kind=`final_chat`, mock returns “Готово, я это зафиксировал.”
- If request_kind=`compaction`, mock returns simple summary.

## Context debug endpoint

In local dev, add endpoint:

```text
GET /api/debug/context/latest
```

Only if `APP_ENV=local`.

It should return context snapshot for the last message without secrets. Useful for backend debugging.
