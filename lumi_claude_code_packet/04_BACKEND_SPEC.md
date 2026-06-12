# Lumi — Backend Spec

## Stack

Backend must be Python.

Recommended versions:

- Python 3.12+
- FastAPI
- Uvicorn
- aiogram 3.x
- SQLAlchemy 2.x async
- Alembic
- asyncpg
- Pydantic v2
- pydantic-settings
- httpx
- tenacity
- redis
- arq
- croniter
- feedparser
- google-api-python-client
- google-auth
- google-auth-oauthlib
- cryptography
- pytest
- pytest-asyncio
- ruff
- mypy optional

## Configuration

Use typed Pydantic settings.

Environment variables should be loaded from `.env`.

Do not commit `.env`.

`Settings` must include:

```python
APP_ENV: str
APP_NAME: str = "Lumi"
APP_PUBLIC_URL: str | None
BACKEND_BASE_URL: str
FRONTEND_PUBLIC_PATH: str = "/app"

DATABASE_URL: str
REDIS_URL: str

TELEGRAM_BOT_TOKEN: str
ALLOWED_TELEGRAM_USER_IDS: list[int]

LLM_PROVIDER: Literal["minimax", "mock"]
MINIMAX_API_KEY: str | None
MINIMAX_BASE_URL: str = "https://api.minimax.io/v1"
MINIMAX_MODEL: str = "MiniMax-M3"
LLM_TIMEOUT_SECONDS: int = 90
LLM_MAX_RETRIES: int = 3
LLM_CONTEXT_MAX_CHARS: int = 120000

DEFAULT_TIMEZONE: str = "Europe/Moscow"

APP_SECRET_KEY: str
ENCRYPTION_KEY: str

GOOGLE_OAUTH_CLIENT_SECRET_FILE: str | None
GOOGLE_OAUTH_TOKEN_FILE: str | None
GOOGLE_SCOPES: list[str]

NEWS_DEFAULT_TOPICS: list[str]
NEWS_MAX_ITEMS_PER_TOPIC: int = 10

SCHEDULER_TICK_SECONDS: int = 30
```

For `ALLOWED_TELEGRAM_USER_IDS`, support comma-separated env parsing:

```text
ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
```

## API server

FastAPI app should expose:

```text
GET /health
GET /app/*                  static Mini App SPA
GET /api/me
GET /api/today
GET /api/messages
GET /api/tasks
POST /api/tasks
PATCH /api/tasks/{id}
POST /api/tasks/{id}/complete
POST /api/tasks/{id}/snooze
GET /api/calendar/events
POST /api/calendar/plan-day
POST /api/calendar/blocks/{id}/confirm
POST /api/calendar/sync
GET /api/inbox/summary
POST /api/inbox/triage/run
GET /api/news/topics
POST /api/news/topics
PATCH /api/news/topics/{id}
POST /api/news/digest/run
GET /api/automations
POST /api/automations
PATCH /api/automations/{id}
POST /api/automations/{id}/run
GET /api/memories
PATCH /api/memories/{id}
DELETE /api/memories/{id}
GET /api/agent-runs
GET /api/agent-runs/{id}
GET /api/connectors/google/status
GET /api/connectors/google/auth-url      optional if server OAuth implemented
GET /api/connectors/google/callback      optional if server OAuth implemented
POST /api/connectors/google/disconnect   optional
```

All `/api/*` routes except `/health` and OAuth callback must require Telegram Mini App auth or local dev auth.

## Telegram Mini App auth

Frontend sends:

```text
X-Telegram-Init-Data: window.Telegram.WebApp.initData
```

Backend:

1. Validate raw initData using aiogram `safe_parse_webapp_init_data` or equivalent HMAC validation.
2. Reject if invalid.
3. Extract Telegram user id.
4. Reject if id not in `ALLOWED_TELEGRAM_USER_IDS`.
5. Create or update user in DB.
6. Return request-scoped current user.

Do not trust `initDataUnsafe` from frontend except for temporary display before backend confirms.

Local dev fallback may be allowed only when `APP_ENV=local` and `DEV_AUTH_TELEGRAM_USER_ID` is set. It must be disabled by default.

## Bot process

Use aiogram long polling.

Startup:

1. Load settings.
2. Initialize DB session maker.
3. Initialize services and orchestrator.
4. Ensure webhook is deleted if necessary; polling cannot work while webhook is set.
5. Start polling with allowed updates: message, callback_query.

Message handling:

1. If not private chat: ignore or reply “Lumi работает только в личном чате” only for allowed user if desired.
2. If user id not allowlisted: ignore silently or reply “Access denied” depending config.
3. On `/start`: create user, create main conversation, send intro with Mini App button.
4. On `/app`: send Mini App open button.
5. On `/today`: return concise Today summary.
6. On `/tasks`: list active tasks.
7. On `/plan`: enqueue/run daily planning.
8. On `/news`: enqueue/run news digest.
9. On `/email`: enqueue/run email triage.
10. On normal text: pass to `AssistantOrchestrator.handle_user_message`.

Callback handling:

- `confirm:<confirmation_id>`
- `reject:<confirmation_id>`
- `task_done:<task_id>`
- `task_snooze:<task_id>:<preset>`
- `run:<automation_type>`
- `open_app`

## Assistant Orchestrator

Core method:

```python
async def handle_user_message(
    telegram_user_id: int,
    telegram_chat_id: int,
    telegram_message_id: int,
    text: str,
) -> AssistantResult:
    ...
```

Responsibilities:

1. Ensure user and main conversation exist.
2. Save inbound message.
3. Create `agent_run` with type `chat`.
4. Run `SignalExtractor` with timeout and retries.
5. Apply safe high-confidence actions:
   - create task;
   - create reminder;
   - store memory;
   - create pending confirmation;
   - update task if clearly identified.
6. Build final context via `ContextBuilder`.
7. Call LLM via `LLMProvider`.
8. Save assistant message.
9. Schedule compaction job if needed.
10. Return text + optional Telegram buttons.

Do not let extraction failure break the chat. If extraction fails, log and continue to final answer.

## SignalExtractor

Separate from final assistant response. It returns structured JSON.

Purpose:

- Identify tasks.
- Identify reminders.
- Identify memory candidates.
- Identify calendar intent.
- Identify automation intent.
- Identify email/news commands.
- Identify whether confirmation is required.

Output schema example:

```json
{
  "language": "ru",
  "intents": ["create_task", "create_reminder"],
  "tasks": [
    {
      "title": "Написать Саше по договору",
      "description": null,
      "due_at_local": "2026-06-11T09:00:00",
      "reminder_at_local": "2026-06-11T09:00:00",
      "priority": "medium",
      "project": null,
      "tags": ["договор"],
      "confidence": 0.94,
      "requires_confirmation": false
    }
  ],
  "memory_candidates": [
    {
      "kind": "preference",
      "text": "Пользователь предпочитает утренние дайджесты до 09:30.",
      "importance": 4,
      "confidence": 0.86,
      "requires_confirmation": false
    }
  ],
  "calendar_requests": [
    {
      "kind": "find_focus_slot",
      "title": "Архитектура Lumi",
      "duration_minutes": 90,
      "time_window_local": {
        "start": "2026-06-10T15:00:00",
        "end": "2026-06-10T20:00:00"
      },
      "requires_confirmation": true,
      "confidence": 0.9
    }
  ],
  "automation_requests": [],
  "should_answer_normally": true
}
```

Important rules:

- If confidence < 0.75, do not auto-create. Create a pending confirmation or ask in final reply.
- Destructive/external actions always require confirmation.
- External calendar write always requires confirmation.
- Email send/delete/archive always requires confirmation and can be unimplemented in MVP.

## ContextBuilder

Input:

- user;
- conversation;
- current message;
- agent run;
- optional action results.

Output:

```python
BuiltContext(
    system_prompt: str,
    messages: list[LLMMessage],
    debug_snapshot: dict,
    estimated_chars: int,
)
```

Context sections:

1. Lumi identity/system prompt.
2. Date/time/timezone.
3. User profile.
4. Permissions and safety rules.
5. Active tasks.
6. Due reminders.
7. Calendar window.
8. Relevant memories.
9. Current conversation summary.
10. Recent messages.
11. Action results already performed.
12. Current user message.

## LLMProvider

Interface:

```python
class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        request_kind: str,
        metadata: dict | None = None,
    ) -> LLMResponse: ...

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        system: str | None = None,
        json_schema_hint: dict | None = None,
        request_kind: str,
        metadata: dict | None = None,
    ) -> dict: ...
```

Implement:

- `MiniMaxProvider`
- `MockLLMProvider`

`MiniMaxProvider` can use OpenAI-compatible API for MVP:

```text
base_url=https://api.minimax.io/v1
model=MiniMax-M3
endpoint=/chat/completions
```

Keep provider abstraction so later switching to Anthropic-compatible MiniMax endpoint is easy.

Use:

- timeout;
- retries with exponential backoff;
- response/error logging to `llm_calls`;
- no secrets in logs.

## Services

### TaskService

Methods:

```python
create_task_from_signal(user, signal, source_message_id)
list_active_tasks(user)
complete_task(user, task_id)
snooze_task(user, task_id, until)
extract_due_reminders(now)
```

### CalendarService

Methods:

```python
sync_google_calendar(user)
list_events(user, start, end)
find_free_slots(user, start, end, duration_minutes)
create_internal_block(user, title, start, end, source)
propose_day_plan(user, date)
confirm_external_calendar_write(user, block_id)
```

### EmailService

Methods:

```python
sync_recent_threads(user, since)
triage_inbox(user, since)
extract_tasks_from_emails(user, triage_result)
```

### NewsService

Methods:

```python
list_topics(user)
create_topic(user, query, schedule)
collect_news(topic)
generate_digest(user, topics)
```

### AutomationService

Methods:

```python
create_scheduled_task(user, type, cron, config)
update_scheduled_task(...)
run_now(user, scheduled_task_id)
find_due_tasks(now)
mark_started/mark_completed/mark_failed
```

### MemoryService

Methods:

```python
store_candidate(user, candidate, source_message_id)
retrieve_relevant(user, query, limit=12)
list_memories(user)
archive_memory(user, memory_id)
```

MVP retrieval can be keyword/recency/importance scoring, not vector search.

## Formatting Telegram messages

Telegram has message length limits; implement chunking.

Use plain text by default to avoid Markdown escaping bugs. If using Markdown/HTML parse mode, implement safe escaping and tests.

## Error handling

User-facing errors should be calm and actionable:

```text
Я не смог сейчас достучаться до модели. Сообщение сохранил, можно повторить через минуту.
```

For background jobs:

- save failed agent_run;
- increment scheduled_task failure_count;
- notify user only for important recurring failures after threshold;
- include retry.

## Observability

Log JSON lines.

Every request/job should have correlation id:

- `request_id` for API;
- `agent_run_id` for AI jobs;
- `telegram_update_id` for bot messages.

Store in DB:

- llm_calls;
- tool_calls;
- agent_runs;
- audit_logs.

## CLI/scripts

Implement:

```text
make setup
make up
make down
make logs
make migrate
make test
make lint
make smoke
make google-auth-local
make frontend-build
make reset-local-db
```

`make setup` should not ask for secrets inside committed files. It can copy `.env.example` to `.env` and print what to fill.

Optional `scripts/bootstrap_local.py` may prompt user for tokens and write `.env` locally.
