# Lumi — Testing and Acceptance Checklist

## Test strategy

The project must include automated tests and local smoke checks.

Minimum:

```text
pytest backend tests
frontend build passes
ruff check passes
Docker Compose starts
migrations apply
mock LLM smoke passes
```

## Backend unit tests

### ContextBuilder

Test:

- includes user profile;
- includes active tasks;
- includes calendar window;
- includes relevant memories;
- includes summary;
- includes recent messages;
- respects char budget;
- does not include compacted old messages when summary exists.

### SignalExtractor JSON parsing

Test:

- parses valid JSON;
- strips markdown fences;
- handles invalid JSON gracefully;
- validates task schema;
- low confidence creates confirmation, not task.

### TaskService

Test:

- create task;
- complete task;
- snooze;
- due reminders query;
- task event audit.

### MemoryService

Test:

- store memory;
- deduplicate similar memory;
- retrieve by keyword;
- archive memory.

### Telegram auth

Test:

- allowlisted user passes;
- non-allowlisted user rejected;
- group chat ignored;
- invalid Mini App initData rejected.

For initData validation, include a test that mocks/patches aiogram validation or uses fixture if generating valid signed initData is too much.

### Scheduler

Test:

- due scheduled task enqueued;
- disabled task skipped;
- next_run_at updated;
- lock prevents double enqueue.

### CalendarService

Test:

- merge busy intervals;
- find free slots;
- create proposed block;
- external write requires confirmation.

### EmailService

Test with mocked Gmail connector:

- sync threads;
- triage result mapping;
- task candidates from emails.

### NewsService

Test with mocked RSS:

- fetch items;
- deduplicate by hash;
- build digest input;
- save digest run.

### LLMProvider

Test Mock provider.

For MiniMax provider, include integration test skipped unless `MINIMAX_API_KEY` exists:

```python
pytest.mark.skipif(not os.getenv("MINIMAX_API_KEY"), reason="requires MiniMax key")
```

## API tests

Use FastAPI test client or httpx async client.

Endpoints:

- `/health`
- `/api/me`
- `/api/today`
- `/api/tasks`
- `/api/calendar/events`
- `/api/automations`
- `/api/memories`

Auth can be bypassed only through explicit local test dependency override.

## Frontend checks

- `npm run build` passes.
- TypeScript passes.
- Main pages render with mocked API or dev data.
- API client sends `X-Telegram-Init-Data`.
- 401 state is handled.

## Smoke tests

Implement:

```text
make smoke
```

Smoke with `LLM_PROVIDER=mock` should:

1. connect to DB;
2. create user;
3. create main conversation;
4. call orchestrator with “Напомни завтра в 10 написать Саше”;
5. assert task created;
6. assert assistant response exists;
7. run context builder;
8. run scheduler due check;
9. print success.

## Manual acceptance test

After real secrets are provided:

### Bot startup

```text
make up
make migrate
make seed
```

Expected:

- all containers healthy/running;
- bot polling logs show startup;
- no webhook conflict.

### Telegram chat

Send `/start`.

Expected:

- Lumi replies;
- user row created;
- main conversation created;
- Mini App button visible if APP_PUBLIC_URL set.

Send:

```text
Напомни завтра в 10 написать Саше по договору
```

Expected:

- Lumi confirms task/reminder;
- task appears in Mini App;
- DB row exists.

Send:

```text
Что у меня сегодня?
```

Expected:

- Lumi returns Today summary using tasks/calendar state.

### Mini App

Open Mini App.

Expected:

- Today loads;
- Tasks page shows created task;
- Automations page loads;
- Memory page loads;
- Settings shows connector status.

### News

In Telegram or Mini App, run news digest.

Expected:

- agent_run created;
- news_items saved;
- digest message sent.

### Google Calendar

If Google connected:

- run calendar sync;
- events appear;
- plan day proposes focus blocks;
- external calendar write asks confirmation.

### Gmail

If Google connected:

- run email triage;
- threads summarized;
- digest appears;
- no emails are modified.

## Definition of done for Claude Code

Do not stop after scaffolding.

The implementation is done only when:

1. Repo has backend, frontend, Docker Compose, migrations, tests, docs.
2. `make setup` works.
3. `make up` works or failures are only due missing secrets and clearly documented.
4. `make test` passes.
5. `make frontend-build` passes.
6. `make smoke` passes with mock LLM.
7. Real MiniMax provider code exists and is wired via env.
8. Bot polling code exists and handles messages.
9. Mini App static serving exists.
10. DB schema matches docs or differences are documented.
11. README explains setup step-by-step.
12. `docs/architecture.md` contains diagrams.
13. `docs/runbook.md` explains operations/debugging.

## If blocked

If Claude Code cannot complete an external integration due missing credentials:

- implement code path;
- implement mock connector;
- document exact secret/setup needed;
- continue with the rest of the project.

Do not leave TODO instead of core code unless a real external credential is impossible to simulate.
