# Master Prompt for Claude Code — Implement Lumi MVP

You are Claude Code working as a senior full-stack engineer and product-minded backend architect.

Your task is to implement a complete local MVP of **Lumi**, a personal AI assistant in Telegram.

The user will run this locally on a Mac first. Cost/tokens/time are not important. Do the complete implementation, not a shallow scaffold.

## Product name

The assistant is called **Lumi**.

Use this name everywhere:

- product name;
- bot identity;
- Mini App title;
- README;
- docs;
- code/package naming where appropriate.

## Main goal

Build a working local Telegram AI assistant with:

1. Python backend.
2. Telegram bot via long polling.
3. MiniMax M3 API integration.
4. Own backend context management, memory, summaries, tasks, scheduled jobs.
5. Postgres/Redis/Docker Compose.
6. React/Vite Telegram Mini App.
7. Tasks, reminders, calendar, scheduled news digest, email triage, Google Calendar/Gmail connector skeleton or working local connector.
8. Detailed documentation and diagrams.

The final result should let the user:

1. provide Telegram bot token;
2. provide MiniMax API key;
3. optionally provide Google OAuth credentials;
4. run Docker Compose locally;
5. open Telegram;
6. message Lumi;
7. get a real AI response;
8. create tasks/reminders from chat;
9. open the Mini App;
10. see Today/Tasks/Calendar/Inbox/News/Automations/Memory/Settings;
11. manually run news/email/calendar/planning jobs.

## Non-negotiable decisions

Implement exactly these decisions unless technically impossible:

```text
Assistant name: Lumi
Backend: Python
API: FastAPI
Bot: aiogram 3.x long polling
DB: Postgres
ORM: SQLAlchemy 2 async
Migrations: Alembic
Queue/cache: Redis
Worker: async worker, preferably arq
Scheduler: application-level scheduler, croniter, DB-backed scheduled_tasks
Frontend: React + TypeScript + Vite + Tailwind
Mini App: Telegram WebApp, served by FastAPI static files under /app
LLM default: MiniMax M3
LLM architecture: stateless provider calls, state stored in Lumi DB
Context management: ContextBuilder + conversation summaries + memory retrieval
MVP users: only private 1:1 assistant, allowlisted Telegram user ids
Group chats: not supported
Storage: local files only, no S3
Deployment: local Docker Compose
Bot update mode: polling, not webhook
External Google writes: confirmation required
Email destructive/send actions: not implemented or confirmation-gated
```

## Important implementation style

Do not produce only design docs. Write actual code.

Do not stop after scaffolding.

Do not ask broad clarifying questions before implementing. Use the specs and sensible defaults. Only ask the user for secrets after the code is ready to run.

If external credentials are unavailable, implement mock/fallback paths and continue.

Use clean architecture:

```text
bot/API -> services/orchestrator -> repositories/connectors/LLM provider -> DB/external APIs
```

No direct MiniMax/Gmail/Calendar calls inside Telegram handlers.

No raw secrets in logs.

## Sources

When unsure about current API details, consult current official docs. Prefer official docs over memory.

Relevant sources are listed in `99_SOURCES.md`.

## Deliverables

Create a complete repo:

```text
lumi-assistant/
  README.md
  Makefile
  docker-compose.yml
  .env.example
  .gitignore
  backend/
  frontend/
  docs/
  scripts/
```

Backend:

- FastAPI app.
- aiogram polling bot.
- SQLAlchemy models.
- Alembic migrations.
- Services and repositories.
- MiniMax provider + mock provider.
- Context builder and compaction.
- Task extraction and memory extraction.
- Scheduler and worker.
- Google connector code.
- News RSS connector.
- API routes for Mini App.
- Tests.

Frontend:

- React/Vite/Tailwind Mini App.
- Premium mobile-first UI.
- Pages: Today, Tasks, Calendar, Inbox, News, Automations, Memory, Settings, Agent Runs.
- Telegram initData auth header.
- API client.
- Loading/error/empty states.

Docs:

- README with local setup.
- `docs/architecture.md` with Mermaid diagrams.
- `docs/database.md` with schema and ERD.
- `docs/context-management.md`.
- `docs/connectors.md`.
- `docs/runbook.md`.
- `docs/security.md`.

Tests:

- backend pytest tests.
- frontend build check.
- smoke script with mock LLM.

## Implementation phases

Work in phases and commit mentally after each phase. Actually modify files.

### Phase 0 — Inspect and initialize

1. Inspect existing directory.
2. If empty, create repo structure.
3. Create `.gitignore`, `.env.example`, `README.md`, `Makefile`, `docker-compose.yml`.
4. Decide package manager for backend. Prefer `uv` if available, otherwise standard `pip`/`requirements.txt` is acceptable. Keep it easy to run in Docker.
5. Decide frontend package manager. Use npm unless repo already uses something else.

### Phase 1 — Backend foundation

Implement:

- `backend/pyproject.toml` or requirements.
- `src/lumi/config.py` Pydantic settings.
- DB session.
- SQLAlchemy models matching schema spec.
- Alembic initial migration.
- FastAPI app with `/health`.
- structured logging.
- repository/service base.

### Phase 2 — LLM layer

Implement:

- `LLMProvider` protocol/base.
- `MiniMaxProvider` using OpenAI-compatible API by default:
  - `MINIMAX_BASE_URL=https://api.minimax.io/v1`
  - `MINIMAX_MODEL=MiniMax-M3`
  - endpoint chat completions via OpenAI-compatible SDK or httpx.
- `MockLLMProvider`.
- retry/timeout via tenacity.
- JSON parsing utility.
- LLM call logging.

If OpenAI SDK compatibility is annoying, use `httpx` directly.

### Phase 3 — Context, memory, compaction

Implement:

- system prompts for Lumi;
- `ContextBuilder`;
- `SignalExtractor`;
- `MemoryService`;
- `CompactionService`;
- background compaction job.

Use stateless LLM calls. Do not store/use provider conversation id as source of truth.

### Phase 4 — Tasks/reminders

Implement:

- TaskService.
- TaskRepository.
- Create task from chat extraction.
- Complete/snooze.
- Reminder due query.
- Reminder notification job.
- API endpoints.
- Mini App task payload.

### Phase 5 — Telegram bot

Implement aiogram polling:

- allowlist;
- private chat only;
- `/start`, `/help`, `/app`, `/today`, `/tasks`, `/plan`, `/news`, `/email`, `/settings`;
- normal text to orchestrator;
- callback confirmations;
- Telegram buttons;
- message chunking.

On startup, if webhook conflict exists, handle/delete webhook or log clear instruction.

### Phase 6 — Scheduler/worker/automations

Implement:

- DB-backed scheduled_tasks.
- Scheduler loop with croniter.
- Redis queue via arq or equivalent.
- Worker jobs:
  - run_news_digest
  - run_email_triage
  - run_daily_planning
  - run_calendar_sync
  - run_task_review
  - send_due_reminders
  - compact_conversation
- API endpoints for automations and run now.

### Phase 7 — Calendar

Implement:

- internal calendar events;
- free slot algorithm;
- day planning service;
- proposed focus blocks;
- confirm external write flow;
- Google Calendar connector;
- calendar sync job;
- calendar API routes.

If Google credentials are missing, internal calendar must still work.

### Phase 8 — Email

Implement:

- Gmail connector read-only;
- local OAuth script or server OAuth flow;
- email thread/message upsert;
- email triage service;
- LLM triage prompt;
- task candidates;
- Telegram digest;
- API routes.

No send/delete/archive in MVP unless implemented as confirmation-gated stubs.

### Phase 9 — News

Implement:

- RSS/Google News RSS fetcher;
- topics;
- dedupe;
- digest generation;
- scheduled digest;
- Telegram digest;
- API routes.

### Phase 10 — Frontend Mini App

Implement React/Vite/Tailwind app:

- Telegram WebApp wrapper.
- API client with initData header.
- App shell.
- Premium UI.
- Pages:
  - Today
  - Tasks
  - Calendar
  - Inbox
  - News
  - Automations
  - Memory
  - Settings
  - Agent Runs
- Empty/loading/error states.
- Static build served by FastAPI.

Focus visual polish on Today page.

### Phase 11 — Docker/local setup

Make sure:

- `docker-compose.yml` works.
- backend image builds.
- frontend builds.
- static app is served.
- Postgres and Redis volumes exist.
- Makefile commands work.
- `.env.example` complete.
- `make smoke` works with `LLM_PROVIDER=mock`.

### Phase 12 — Tests

Write tests for:

- context builder;
- JSON parsing;
- signal extraction parsing;
- task service;
- memory service;
- scheduler due tasks;
- calendar free slots;
- Telegram auth guards;
- API health/today/tasks with test auth override;
- mock LLM smoke.

Run tests. Fix failures.

### Phase 13 — Documentation

Create docs with Mermaid diagrams:

- architecture;
- DB ERD;
- context management;
- scheduler/worker;
- connectors;
- local deployment;
- troubleshooting.

### Phase 14 — Final setup assistant behavior

After coding and tests, ask the user for secrets in this order:

1. `TELEGRAM_BOT_TOKEN`
2. `ALLOWED_TELEGRAM_USER_IDS` or help them get id
3. `MINIMAX_API_KEY`
4. `APP_PUBLIC_URL` if they want Mini App on iPad through tunnel
5. Google OAuth client secret JSON if they want Gmail/Calendar

Do not ask for secrets before code is ready unless necessary.

Then help them run:

```text
make setup
make frontend-build
make up-detached
make migrate
make seed
make smoke
```

Then tell them to message `/start` to the Telegram bot.

## Required architecture details

Use the detailed specs from the other documents in this packet. They define product, schema, backend, context, connectors, UI, deployment, security, and testing.

## Acceptance criteria

Implementation is acceptable only if:

1. It is a real runnable project.
2. Mock LLM path works without MiniMax key.
3. Real MiniMax path is implemented.
4. Telegram bot code is real and wired.
5. Mini App code is real and buildable.
6. Database schema is implemented via migrations.
7. Context management is implemented in code, not only documented.
8. Tasks/reminders are implemented.
9. Scheduler/worker exist.
10. News digest exists.
11. Calendar internal planning exists.
12. Google connector exists or is implemented as a well-documented local OAuth flow with mocks if credentials absent.
13. Email triage exists or gracefully requires Google connection.
14. Docs explain architecture with diagrams.
15. Tests/smoke checks exist.

## Do not do

- Do not build group chat support.
- Do not use webhook for local MVP.
- Do not depend on S3.
- Do not put secrets into repo.
- Do not let LLM execute arbitrary tools.
- Do not send/delete/archive email without confirmation.
- Do not write external calendar without confirmation.
- Do not make a cheap-looking dashboard.
- Do not leave all important features as TODO.

## Start now

Implement the full project. Use the specs. Prefer finishing a working MVP over perfect abstractions, but keep the architecture clean enough for a backend developer to extend.
