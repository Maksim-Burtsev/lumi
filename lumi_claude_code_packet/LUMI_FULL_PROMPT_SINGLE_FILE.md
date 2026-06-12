# Lumi Full Implementation Prompt — single file

Скопируй этот файл целиком в Claude Code. Он содержит мастер-промпт и все спецификации для реализации MVP Lumi.



---

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


---

# Lumi — Product Spec MVP

## Название

**Lumi** — личный AI-ассистент в Telegram.

## Позиционирование

Lumi — не просто чат с моделью. Это персональный операционный слой поверх задач, календаря, почты, новостей и долгосрочного пользовательского контекста. Главная ценность: Lumi каждый день превращает хаос из сообщений, писем, задач, встреч и информационного шума в понятный план действий.

## Главный пользовательский сценарий MVP

Пользователь открывает Telegram, пишет Lumi обычным языком, например:

```text
Напомни завтра утром написать Саше по договору и сегодня после встреч найди слот на архитектуру Lumi.
```

Lumi должен:

1. Понять сообщение.
2. Создать задачу.
3. Создать напоминание.
4. Посмотреть календарь.
5. Предложить фокус-блок.
6. Сохранить важный контекст при необходимости.
7. Ответить в Telegram человеческим, коротким, полезным сообщением.
8. Отобразить изменения в Mini App.

## Core-wow фокус

Не делать 100 случайных функций. Сделать небольшой, но сильный набор:

1. **Единый личный чат в Telegram** — пользователь пишет Lumi как ассистенту.
2. **Извлечение задач из диалога** — Lumi превращает естественный язык в задачи, напоминания, фокус-блоки.
3. **Today command center в Mini App** — красивый мобильный экран: встречи, задачи, письма, предложения ассистента.
4. **Планирование дня** — Lumi смотрит задачи и календарь, предлагает слоты.
5. **Новости по темам** — scheduled digest по темам, важным пользователю.
6. **Email triage** — Lumi разгребает почту read-only, находит важное, предлагает действия.
7. **Внутренний календарь + внешний Google Calendar** — внутренний календарь для proposed/AI blocks, внешний как источник занятости и опциональная запись после подтверждения.
8. **Память и context management** — Lumi помнит предпочтения, проекты, правила, но делает это явно, прозрачно и управляемо.

## Что точно входит в MVP

### Telegram bot

- Только private 1:1 чат.
- Никаких групповых чатов.
- Ответы только allowlisted Telegram user id.
- Long polling для локального запуска.
- Команды:
  - `/start`
  - `/help`
  - `/app`
  - `/today`
  - `/tasks`
  - `/plan`
  - `/news`
  - `/email`
  - `/settings`
- Inline buttons для подтверждения действий:
  - создать задачу
  - принять план
  - создать календарный блок
  - отклонить действие
  - открыть Mini App

### AI chat

- MiniMax M3 как default real provider.
- Mock provider для тестов и локального smoke без ключа.
- Stateless LLM calls: все состояние хранится в backend БД, а не в “чате на стороне LLM”.
- Собственный context builder.
- Собственный compaction/summarization.
- Собственная память пользователя.
- Логи LLM-вызовов без хранения секретов.

### Tasks

- Создание задач из чата.
- Создание задач из email triage.
- Ручное создание задач в Mini App.
- Статусы: inbox, active, done, cancelled.
- Приоритеты: low, medium, high, urgent.
- Due date, reminder date, tags, project.
- Напоминания через scheduler.
- История изменений задачи.

### Calendar

- Internal calendar в БД.
- Google Calendar sync как внешний источник.
- Свободные окна.
- Proposed focus blocks.
- Confirm before writing external calendar.
- Daily planning run.

### Email

- Google Gmail read-only MVP.
- Сбор новых писем за период.
- Классификация:
  - needs_reply
  - waiting_for_me
  - decision_needed
  - fyi
  - newsletter
  - invoice_document
  - ignore
- Summary digest в Telegram.
- Proposed tasks from email.
- Никаких delete/send/archive без отдельного явного подтверждения. В MVP можно вообще не реализовывать destructive actions.

### News

- Scheduled digest по темам.
- Источник MVP: RSS, включая Google News RSS query URL или ручные RSS sources.
- LLM summary с группировкой по темам.
- Сохранение items и digest runs.

### Mini App

Страницы:

1. Today
2. Tasks
3. Calendar
4. Inbox
5. News
6. Automations
7. Memory
8. Settings

Тон UI: premium, calm, elegant, mobile-first. Не дешёвый dashboard.

### Automations

Пользователь может иметь scheduled tasks:

- daily_news_digest
- email_morning_triage
- daily_planning
- calendar_sync
- task_review
- custom_prompt

Для MVP обязательно реализовать создание/редактирование/включение/выключение automation в Mini App, а также ручной `Run now`.

## Что не входит в MVP

- Group chats.
- Multi-user SaaS.
- Payments.
- S3/object storage.
- Production Kubernetes.
- Complex vector search.
- Multi-workspace/team mode.
- Голосовые сообщения, speech-to-text, text-to-speech.
- Отправка email без подтверждения.
- Удаление email.
- Агент, который имеет доступ к shell/файлам Mac.

## Главный UX принцип

Lumi не должен вести себя как “универсальная LLM без памяти”. Он должен вести себя как аккуратный личный операционный ассистент:

- коротко отвечает;
- сам предлагает следующий шаг;
- явно говорит, что создал/не создал;
- не делает рискованных действий без подтверждения;
- показывает пользователю, что он понял контекст;
- не перегружает интерфейс;
- ведёт аккуратный audit trail.

## Примеры пользовательских команд

```text
Напомни завтра в 10 написать Ивану.
```

```text
Разбери почту за утро и скажи, где от меня ждут ответа.
```

```text
Сделай мне план на сегодня с учетом встреч и задач.
```

```text
Каждый будний день в 8:30 присылай новости по AI agents, Telegram Mini Apps и pricing LLM.
```

```text
У меня сегодня созвон в 15, после него поставь 90 минут на архитектуру backend.
```

```text
Запомни: рабочие задачи лучше группировать по проектам.
```

```text
Что ты про меня помнишь?
```

## Ответы Lumi должны быть такими

Хороший ответ:

```text
Готово.

Создал задачу: написать Ивану.
Напоминание: завтра в 10:00.

Еще вижу свободное окно завтра 10:30–12:00, могу поставить туда фокус-блок, если нужно.
```

Плохой ответ:

```text
Конечно! Я могу помочь вам с большим количеством задач, включая напоминания, календарь, почту...
```

## Product definition of done

MVP считается готовым, когда пользователь может:

1. Запустить проект локально через Docker Compose.
2. Указать Telegram bot token и MiniMax API key.
3. Написать своему боту в Telegram.
4. Получить AI-ответ от Lumi через MiniMax M3.
5. Создать задачу из обычного сообщения.
6. Получить напоминание по задаче.
7. Открыть Mini App из Telegram.
8. Увидеть Today, Tasks, Calendar, Automations.
9. Запустить вручную news digest.
10. Подключить или подготовить Google connector для Gmail/Calendar.
11. Запустить email triage и calendar sync при наличии Google credentials.
12. Посмотреть memory и удалить memory.
13. Посмотреть логи agent runs/tool calls.
14. Прочитать документацию по архитектуре.


---

# Lumi — Architecture Spec

## Архитектурное решение MVP

Lumi должен быть локальным Docker Compose проектом, который можно запустить на Mac.

Главный принцип: **LLM stateless, stateful backend**.

То есть:

- Не использовать постоянный “chat id” на стороне LLM как источник правды.
- Не рассчитывать, что провайдер LLM хранит историю.
- Все сообщения, summaries, memories, tasks, calendar, email digest, agent runs хранятся в Postgres.
- Каждый вызов LLM получает контекст, который собрал backend `ContextBuilder`.
- Compaction делает backend: старые сообщения суммируются и заменяются summary внутри будущего контекста.

## Сервисы Docker Compose

Минимальная production-like локальная структура:

```text
lumi-assistant/
  backend/
  frontend/
  docs/
  scripts/
  docker-compose.yml
  Makefile
  .env.example
```

Docker services:

```text
postgres
redis
api
bot
worker
scheduler
```

Опционально для dev:

```text
frontend-dev
```

### postgres

Основная БД.

Хранит:

- users
- conversations
- messages
- summaries
- memories
- tasks
- reminders
- calendar events
- email metadata/digests
- news topics/items/digests
- scheduled tasks
- agent runs
- LLM calls
- tool calls
- pending confirmations
- connectors
- audit logs

### redis

Используется для:

- async job queue;
- locks;
- rate limiting;
- transient cache;
- idempotency keys;
- worker coordination.

### api

FastAPI backend.

Отвечает за:

- REST API для Mini App;
- Telegram Mini App initData validation;
- serving static Mini App build under `/app`;
- health checks;
- connector OAuth endpoints if implemented;
- admin/debug endpoints for local development.

### bot

Aiogram long polling process.

Отвечает за:

- получение Telegram updates через getUpdates/long polling;
- allowlist user check;
- private chat only;
- commands;
- callback buttons;
- передачу пользовательских сообщений в Assistant Orchestrator;
- отправку ответов, reminders, digests.

### worker

Async worker process.

Отвечает за:

- scheduled jobs execution;
- email triage;
- news digest;
- calendar sync;
- daily planning;
- conversation compaction;
- reminder notifications;
- long-running agent runs.

Рекомендуемая библиотека: `arq` + Redis, потому что backend Python async и много I/O calls. Если `arq` окажется неудобен, допустимо использовать Celery + Redis, но тогда нужно аккуратно задокументировать причину.

### scheduler

Process, который раз в N секунд:

1. читает `scheduled_tasks`, где `next_run_at <= now`;
2. ставит job в Redis queue;
3. берет lock, чтобы не было двойного запуска;
4. обновляет `last_run_at`, `next_run_at`, `failure_count`.

Рекомендуемые библиотеки:

- `croniter` для вычисления cron;
- простой async loop или APScheduler.

Не использовать системный cron внутри Mac как основной механизм. Всё должно жить внутри приложения.

## High-level runtime flow

```mermaid
flowchart TD
    U[User in Telegram] -->|private message| TG[Telegram Bot API]
    TG -->|long polling getUpdates| BOT[bot service / aiogram]
    BOT --> AUTH[Allowlist + private chat guard]
    AUTH --> ORCH[Assistant Orchestrator]
    ORCH --> DB[(Postgres)]
    ORCH --> CTX[Context Builder]
    CTX --> DB
    ORCH --> LLM[LLM Gateway / MiniMax M3]
    ORCH --> TOOLS[Tool Registry]
    TOOLS --> TASKS[Tasks Service]
    TOOLS --> CAL[Calendar Service]
    TOOLS --> EMAIL[Email Service]
    TOOLS --> NEWS[News Service]
    TASKS --> DB
    CAL --> DB
    EMAIL --> DB
    NEWS --> DB
    ORCH --> BOT
    BOT -->|sendMessage| TG
    TG --> U
```

## Mini App flow

```mermaid
sequenceDiagram
    participant User as User in Telegram
    participant WebApp as Lumi Mini App
    participant API as FastAPI
    participant Auth as TelegramAuthService
    participant DB as Postgres

    User->>WebApp: opens /app from Telegram button
    WebApp->>WebApp: reads window.Telegram.WebApp.initData
    WebApp->>API: GET /api/today with X-Telegram-Init-Data
    API->>Auth: safe_parse_webapp_init_data(bot_token, initData)
    Auth-->>API: Telegram user id
    API->>API: check ALLOWED_TELEGRAM_USER_IDS
    API->>DB: load user state
    DB-->>API: today payload
    API-->>WebApp: JSON
    WebApp-->>User: premium Today UI
```

## Scheduled task flow

```mermaid
sequenceDiagram
    participant Scheduler
    participant DB as Postgres
    participant Redis
    participant Worker
    participant LLM as MiniMax M3
    participant Bot as Telegram Bot

    Scheduler->>DB: find due scheduled_tasks
    Scheduler->>DB: acquire per-task lock
    Scheduler->>Redis: enqueue job
    Worker->>Redis: consume job
    Worker->>DB: create agent_run
    Worker->>DB: load user/context/config
    Worker->>LLM: call model
    LLM-->>Worker: result
    Worker->>DB: save output, tool_calls, llm_calls
    Worker->>Bot: send digest/notification
    Bot-->>User: Telegram message
```

## Context management flow

```mermaid
flowchart TD
    MSG[Incoming user message] --> SAVE[Save message]
    SAVE --> EXTRACT[LLM signal extraction]
    EXTRACT --> ACTIONS[Create tasks/memories/confirmations]
    ACTIONS --> BUILD[ContextBuilder]
    BUILD --> PROFILE[User profile]
    BUILD --> MEM[Relevant memories]
    BUILD --> TASKS[Active tasks]
    BUILD --> CAL[Calendar window]
    BUILD --> SUM[Conversation summary]
    BUILD --> RECENT[Recent messages]
    BUILD --> PROMPT[Final prompt]
    PROMPT --> CALL[LLM response call]
    CALL --> REPLY[Assistant reply]
    REPLY --> SAVE_REPLY[Save assistant message]
    SAVE_REPLY --> COMPACT{Need compaction?}
    COMPACT -->|yes| QUEUE[Enqueue compaction job]
    COMPACT -->|no| DONE[Done]
```

## Внутренние Python packages

Рекомендуемая структура backend:

```text
backend/
  pyproject.toml
  alembic.ini
  alembic/
  src/lumi/
    __init__.py
    main.py
    config.py
    logging.py
    db/
      base.py
      session.py
      models.py
      repositories/
    bot/
      runner.py
      handlers.py
      keyboards.py
      formatting.py
    api/
      router.py
      deps.py
      routes/
        me.py
        today.py
        tasks.py
        calendar.py
        inbox.py
        news.py
        automations.py
        memory.py
        agent_runs.py
        connectors.py
        debug.py
    assistant/
      orchestrator.py
      context_builder.py
      prompts.py
      signal_extractor.py
      compaction.py
      memory_service.py
      task_extractor.py
    llm/
      base.py
      minimax.py
      mock.py
      json_utils.py
    tools/
      registry.py
      schemas.py
      task_tools.py
      calendar_tools.py
      email_tools.py
      news_tools.py
    services/
      tasks.py
      reminders.py
      calendar.py
      email.py
      news.py
      automations.py
      today.py
      confirmations.py
      audit.py
    connectors/
      google/
        auth.py
        gmail.py
        calendar.py
      news/
        rss.py
    worker/
      main.py
      jobs.py
    scheduler/
      main.py
    security/
      telegram_auth.py
      crypto.py
      permissions.py
    utils/
      time.py
      text.py
      ids.py
```

## Frontend structure

```text
frontend/
  package.json
  index.html
  vite.config.ts
  tailwind.config.ts
  src/
    main.tsx
    App.tsx
    api/client.ts
    telegram/webapp.ts
    routes/
      TodayPage.tsx
      TasksPage.tsx
      CalendarPage.tsx
      InboxPage.tsx
      NewsPage.tsx
      AutomationsPage.tsx
      MemoryPage.tsx
      SettingsPage.tsx
    components/
      layout/
      cards/
      timeline/
      task/
      calendar/
      inbox/
      motion/
    styles/
      globals.css
      tokens.css
```

## Важное архитектурное правило

Ни один модуль не должен напрямую дергать MiniMax, Telegram, Gmail или Google Calendar без service/connector abstraction.

Правильно:

```text
AssistantOrchestrator -> LLMGateway -> MiniMaxProvider
CalendarService -> CalendarConnector -> GoogleCalendarClient
EmailService -> EmailConnector -> GmailClient
Bot handler -> AssistantOrchestrator
```

Неправильно:

```text
bot handler directly calls minimax
bot handler directly writes many tables
frontend directly calls Google APIs
LLM decides destructive action without backend confirmation
```

## Agent run lifecycle

Every AI/background operation should be traceable:

```text
created -> running -> waiting_confirmation -> completed
                       -> failed
                       -> cancelled
```

`agent_runs` should include:

- type;
- trigger;
- status;
- input summary;
- result summary;
- error;
- timestamps;
- related scheduled task id;
- related message id if run came from chat.

## Tool call lifecycle

Even if provider-native tool calling is not implemented, backend actions must be logged as tool calls:

```text
planned -> executed -> completed
        -> failed
        -> requires_confirmation
        -> skipped
```

This gives observability and auditability.

## Local-first assumptions

- Single user for MVP.
- One Telegram ID allowlisted.
- One main conversation.
- Local Postgres volume.
- Local Redis.
- Local files under `./data/files`.
- Mini App served by FastAPI static files.
- HTTPS tunnel optional for real iPad/Telegram Mini App.

## Future expansion points

Implement abstractions now so future changes are easy:

- `LLMProvider`: MiniMax -> OpenAI/Anthropic/OpenRouter/local.
- `EmailConnector`: Gmail -> Outlook.
- `CalendarConnector`: Google -> Microsoft.
- `FileStorage`: local -> S3.
- `MemoryRetriever`: keyword -> vector/pgvector.
- `BotTransport`: Telegram polling -> webhook.
- `AuthProvider`: Telegram-only -> multi-user OAuth.


---

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


---

# Lumi — Database Schema Spec

Use Postgres + SQLAlchemy 2 async + Alembic migrations.

All IDs should be UUID unless noted.

Use timezone-aware `timestamptz` for all timestamps.

Use JSONB for flexible metadata/config, but not instead of important queryable fields.

## Enums

Create Python enums and Postgres enum types where appropriate.

```text
message_role: user, assistant, system, tool
conversation_kind: main, system, scheduled, debug
memory_kind: preference, fact, project, instruction, contact, workflow, other
memory_status: active, archived, rejected
 task_status: inbox, active, done, cancelled
priority: low, medium, high, urgent
scheduled_task_type: news_digest, email_triage, daily_planning, calendar_sync, task_review, custom_prompt
agent_run_type: chat, news_digest, email_triage, daily_planning, calendar_sync, task_review, reminder, compaction, custom
run_status: queued, running, waiting_confirmation, completed, failed, cancelled
confirmation_status: pending, accepted, rejected, expired
calendar_source: internal, google
calendar_event_status: confirmed, tentative, cancelled, proposed
email_category: needs_reply, waiting_for_me, decision_needed, fyi, newsletter, invoice_document, ignore, unknown
connector_type: google
connector_status: disconnected, connected, error, needs_reauth
```

## users

Represents one Telegram user. MVP supports one allowlisted user but schema should allow more later.

Fields:

```text
id uuid pk
telegram_user_id bigint unique not null
telegram_chat_id bigint null
username text null
first_name text null
last_name text null
language_code text null
timezone text not null default 'Europe/Moscow'
locale text not null default 'ru'
settings jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
last_seen_at timestamptz null
```

Indexes:

```text
unique telegram_user_id
```

## conversations

One main conversation for MVP.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
kind conversation_kind not null default 'main'
title text not null default 'Lumi'
status text not null default 'active'
summary_current_id uuid null
compacted_until_message_id uuid null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
(user_id, kind)
```

Constraint:

```text
For MVP, enforce one main conversation per user via partial unique index:
unique (user_id) where kind = 'main'
```

## messages

Stores chat messages and tool/system messages.

Fields:

```text
id uuid pk
conversation_id uuid fk conversations.id not null
user_id uuid fk users.id not null
role message_role not null
content text not null
content_json jsonb null
telegram_message_id bigint null
telegram_chat_id bigint null
token_estimate int null
char_count int not null default 0
is_compacted boolean not null default false
metadata jsonb not null default '{}'
created_at timestamptz not null
```

Indexes:

```text
(conversation_id, created_at)
(user_id, created_at)
telegram_message_id where telegram_message_id is not null
```

## conversation_summaries

Compacted old messages.

Fields:

```text
id uuid pk
conversation_id uuid fk conversations.id not null
user_id uuid fk users.id not null
summary_text text not null
from_message_id uuid fk messages.id null
to_message_id uuid fk messages.id null
message_count int not null default 0
token_estimate int null
version int not null default 1
metadata jsonb not null default '{}'
created_at timestamptz not null
```

Indexes:

```text
(conversation_id, created_at desc)
```

## memories

Long-term memory. Must be visible/editable in Mini App.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
kind memory_kind not null
status memory_status not null default 'active'
text text not null
normalized_text text null
tags text[] not null default '{}'
importance int not null default 3 -- 1..5
confidence numeric(3,2) not null default 0.80
source_message_id uuid fk messages.id null
source_agent_run_id uuid fk agent_runs.id null
last_accessed_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
metadata jsonb not null default '{}'
```

Indexes:

```text
(user_id, status, importance desc)
(user_id, kind)
GIN(tags)
GIN(to_tsvector('simple', text)) optional
```

Rules:

- Do not store highly sensitive data unless user explicitly asks.
- Deduplicate similar memory texts.
- Store memory source.
- Allow archive/delete from Mini App.

## tasks

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
title text not null
description text null
status task_status not null default 'active'
priority priority not null default 'medium'
project text null
tags text[] not null default '{}'
due_at timestamptz null
reminder_at timestamptz null
snoozed_until timestamptz null
source text not null default 'manual' -- chat/email/agent/manual/calendar
source_ref_type text null
source_ref_id uuid null
source_message_id uuid fk messages.id null
calendar_event_id uuid null
created_by text not null default 'user' -- user/agent/system
completed_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
metadata jsonb not null default '{}'
```

Indexes:

```text
(user_id, status, due_at)
(user_id, reminder_at) where reminder_at is not null
GIN(tags)
```

## task_events

Audit trail for task changes.

Fields:

```text
id uuid pk
task_id uuid fk tasks.id not null
user_id uuid fk users.id not null
event_type text not null
before_json jsonb null
after_json jsonb null
actor text not null -- user/agent/system
agent_run_id uuid fk agent_runs.id null
created_at timestamptz not null
```

## scheduled_tasks

User automations.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
type scheduled_task_type not null
title text not null
cron_expression text not null
timezone text not null
config jsonb not null default '{}'
enabled boolean not null default true
last_run_at timestamptz null
next_run_at timestamptz null
locked_until timestamptz null
failure_count int not null default 0
last_error text null
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
(user_id, enabled, next_run_at)
(next_run_at) where enabled = true
```

## agent_runs

Every agent operation.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
type agent_run_type not null
status run_status not null default 'queued'
trigger text not null -- telegram_message/scheduled_task/manual_api/system
scheduled_task_id uuid fk scheduled_tasks.id null
conversation_id uuid fk conversations.id null
source_message_id uuid fk messages.id null
input_summary text null
result_summary text null
error_message text null
error_json jsonb null
started_at timestamptz null
finished_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
metadata jsonb not null default '{}'
```

Indexes:

```text
(user_id, created_at desc)
(user_id, type, created_at desc)
(status, created_at)
```

## llm_calls

Observability and cost estimation.

Fields:

```text
id uuid pk
agent_run_id uuid fk agent_runs.id null
user_id uuid fk users.id null
provider text not null
model text not null
request_kind text not null
status text not null -- success/error/timeout
input_char_count int null
output_char_count int null
input_token_estimate int null
output_token_estimate int null
latency_ms int null
request_hash text null
error_message text null
metadata jsonb not null default '{}'
created_at timestamptz not null
```

Do not store raw API key or full raw provider response if it may contain sensitive data. Raw prompts may be stored only in local dev if `STORE_LLM_DEBUG_PAYLOADS=true`.

## tool_calls

Fields:

```text
id uuid pk
agent_run_id uuid fk agent_runs.id not null
user_id uuid fk users.id not null
tool_name text not null
status text not null -- planned/executed/completed/failed/requires_confirmation/skipped
args_json jsonb not null default '{}'
result_json jsonb null
error_message text null
requires_confirmation boolean not null default false
confirmation_id uuid fk pending_confirmations.id null
started_at timestamptz null
finished_at timestamptz null
created_at timestamptz not null
```

Indexes:

```text
(agent_run_id, created_at)
(user_id, tool_name, created_at desc)
```

## pending_confirmations

For actions requiring explicit user confirmation.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
action_type text not null
action_payload jsonb not null
prompt text not null
status confirmation_status not null default 'pending'
telegram_message_id bigint null
expires_at timestamptz null
decided_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
metadata jsonb not null default '{}'
```

Indexes:

```text
(user_id, status, created_at desc)
```

## calendar_events

Internal and synced external calendar events.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
source calendar_source not null
external_calendar_id text null
external_event_id text null
title text not null
description text null
start_at timestamptz not null
end_at timestamptz not null
timezone text not null
all_day boolean not null default false
busy boolean not null default true
status calendar_event_status not null default 'confirmed'
created_by text not null default 'user' -- user/agent/external_sync
source_task_id uuid fk tasks.id null
agent_run_id uuid fk agent_runs.id null
last_synced_at timestamptz null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
(user_id, start_at, end_at)
(user_id, source, external_event_id)
```

Unique nullable:

```text
unique(user_id, source, external_calendar_id, external_event_id) where external_event_id is not null
```

## connectors

OAuth/connectors status.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
type connector_type not null
status connector_status not null default 'disconnected'
scopes text[] not null default '{}'
credentials_encrypted text null
credentials_file_path text null
last_sync_at timestamptz null
last_error text null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
unique(user_id, type)
```

## email_threads

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
provider text not null default 'google'
external_thread_id text not null
subject text null
participants jsonb not null default '[]'
labels text[] not null default '{}'
last_message_at timestamptz null
snippet text null
category email_category not null default 'unknown'
importance int not null default 3
triage_status text not null default 'new'
summary text null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
unique(user_id, provider, external_thread_id)
(user_id, last_message_at desc)
(user_id, category)
GIN(labels)
```

## email_messages

Fields:

```text
id uuid pk
thread_id uuid fk email_threads.id not null
user_id uuid fk users.id not null
provider text not null default 'google'
external_message_id text not null
sender text null
recipients jsonb not null default '[]'
cc jsonb not null default '[]'
subject text null
snippet text null
body_text text null -- optional; can be null if STORE_EMAIL_BODIES=false
date_at timestamptz null
metadata jsonb not null default '{}'
created_at timestamptz not null
```

Indexes:

```text
unique(user_id, provider, external_message_id)
(thread_id, date_at)
```

Privacy default:

- Store snippets and summaries by default.
- Store bodies only if `STORE_EMAIL_BODIES=true`, default false.
- For triage, body can be fetched, summarized, then discarded.

## news_topics

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
title text not null
query text not null
language text not null default 'ru'
enabled boolean not null default true
config jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes:

```text
(user_id, enabled)
```

## news_items

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
topic_id uuid fk news_topics.id null
title text not null
url text not null
source_name text null
published_at timestamptz null
snippet text null
content_summary text null
hash text not null
metadata jsonb not null default '{}'
created_at timestamptz not null
```

Indexes:

```text
unique(user_id, hash)
(user_id, published_at desc)
(topic_id, published_at desc)
```

## news_digest_runs

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
agent_run_id uuid fk agent_runs.id null
title text not null
digest_text text not null
items_json jsonb not null default '[]'
created_at timestamptz not null
```

## files

Local files metadata. No S3 in MVP.

Fields:

```text
id uuid pk
user_id uuid fk users.id not null
kind text not null
file_name text not null
mime_type text null
local_path text not null
size_bytes bigint null
metadata jsonb not null default '{}'
created_at timestamptz not null
```

## audit_logs

Fields:

```text
id uuid pk
user_id uuid fk users.id null
actor text not null -- user/agent/system
entity_type text not null
entity_id uuid null
action text not null
details jsonb not null default '{}'
created_at timestamptz not null
```

## ERD diagram

The implementation should include this Mermaid ERD in `docs/architecture.md`, adjusted to actual models:

```mermaid
erDiagram
    users ||--o{ conversations : has
    users ||--o{ messages : owns
    conversations ||--o{ messages : contains
    conversations ||--o{ conversation_summaries : summarized_by
    users ||--o{ memories : has
    users ||--o{ tasks : has
    tasks ||--o{ task_events : changes
    users ||--o{ scheduled_tasks : configures
    scheduled_tasks ||--o{ agent_runs : triggers
    users ||--o{ agent_runs : owns
    agent_runs ||--o{ llm_calls : uses
    agent_runs ||--o{ tool_calls : executes
    users ||--o{ pending_confirmations : approves
    pending_confirmations ||--o{ tool_calls : gates
    users ||--o{ calendar_events : has
    tasks ||--o{ calendar_events : scheduled_as
    users ||--o{ connectors : connects
    users ||--o{ email_threads : has
    email_threads ||--o{ email_messages : contains
    users ||--o{ news_topics : follows
    news_topics ||--o{ news_items : produces
    users ||--o{ news_digest_runs : receives
    users ||--o{ audit_logs : audits
```

## Migration requirements

Create Alembic migration for initial schema.

Include seed script:

- create user from Telegram user id if env provided;
- create main conversation;
- create default news topics;
- create default automations disabled or enabled based on env.

## Repository requirements

Use repository pattern or clean service-layer DB access. Do not put raw SQL everywhere unless justified.

Each repository should accept `AsyncSession`.

Example:

```python
class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
```


---

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


---

# Lumi — Connectors Spec

## Connector principles

Connectors must be isolated behind service interfaces.

Assistant/LLM should never directly call external APIs. Backend tools/services call connectors, log results, and pass summarized data to LLM.

## Connectors in MVP

1. Google Gmail
2. Google Calendar
3. RSS/News

Microsoft/Outlook is out of MVP but architecture should allow it later.

## Google OAuth strategy

MVP should support a local-friendly OAuth setup.

Implement at least one of these flows, preferably both:

### Option A — local CLI OAuth, recommended MVP fallback

Command:

```text
make google-auth-local
```

Behavior:

1. Reads `GOOGLE_OAUTH_CLIENT_SECRET_FILE`.
2. Uses `google_auth_oauthlib.flow.InstalledAppFlow`.
3. Opens browser locally.
4. User grants scopes.
5. Saves token securely to `./data/secrets/google_token.json` or encrypted DB field.
6. App uses token for Gmail/Calendar.

Pros:

- Easy for local testing.
- No public redirect URI required.
- Works before Mini App OAuth UI is polished.

Cons:

- Not production-grade.
- Host/browser/Docker path needs care.

### Option B — server OAuth via FastAPI redirect, optional but useful

Endpoints:

```text
GET /api/connectors/google/auth-url
GET /api/connectors/google/callback
```

Flow:

1. User opens Settings → Connect Google.
2. Frontend calls auth-url.
3. Backend returns Google OAuth authorization URL.
4. User grants access.
5. Google redirects to `APP_PUBLIC_URL/api/connectors/google/callback`.
6. Backend exchanges code for tokens.
7. Tokens encrypted and saved in connectors table.
8. Mini App shows connected status.

This requires stable HTTPS redirect URL; for local iPad testing use tunnel URL.

## Google scopes

MVP scopes:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/calendar.events
```

Rationale:

- Gmail read-only for triage.
- Calendar read-only for sync/free-busy.
- Calendar events for optional confirmed external event creation.

If Google marks Gmail scopes as sensitive/restricted, document setup steps clearly. For local personal testing, user can run app in test mode and add own Google account as test user.

## Token storage

Local MVP acceptable:

```text
./data/secrets/google_token.json
```

Better:

- encrypt with Fernet using `ENCRYPTION_KEY`;
- store encrypted token JSON in `connectors.credentials_encrypted`.

Do not print tokens in logs.

## Gmail connector

Class:

```python
class GmailConnector:
    async def list_recent_threads(self, user, since: datetime, max_results: int = 50) -> list[EmailThreadDTO]: ...
    async def get_thread_messages(self, user, thread_id: str) -> list[EmailMessageDTO]: ...
```

Because Google API Python client is sync, either:

- call it in threadpool via `asyncio.to_thread`; or
- keep connector sync and wrap at service boundary.

### Gmail triage flow

```mermaid
flowchart TD
    START[Run email triage] --> FETCH[List recent Gmail threads]
    FETCH --> STORE[Upsert email_threads/messages metadata]
    STORE --> BATCH[Build triage batch]
    BATCH --> LLM[LLM classify/summarize]
    LLM --> SAVE[Save categories/summaries/tasks]
    SAVE --> NOTIFY[Telegram digest]
```

### Data minimization

Default:

- Store subject, snippet, metadata, classification, summary.
- Do not store full body unless `STORE_EMAIL_BODIES=true`.
- Fetch full message body only for triage, then summarize and discard.

### Email triage prompt

```text
Ты модуль triage почты для Lumi.
Тебе передан список писем/тредов. Сгруппируй их по важности и действию.
Не выдумывай содержимое писем.
Верни JSON:
{
  "summary": "короткая выжимка",
  "threads": [
    {
      "external_thread_id": "...",
      "category": "needs_reply|waiting_for_me|decision_needed|fyi|newsletter|invoice_document|ignore|unknown",
      "importance": 1-5,
      "reason": "почему важно",
      "suggested_action": "что сделать",
      "task_candidate": {"title": "...", "due_at_local": null, "priority": "medium"} | null
    }
  ],
  "telegram_digest": "готовый текст для пользователя"
}
```
```

### Telegram email digest format

```text
Почта за утро: 34 письма.

Важно:
1. Иван ждет подтверждения встречи до 14:00.
2. Finance прислали invoice.
3. Клиент ответил по договору.

Нашел задачи:
- Ответить Ивану
- Проверить invoice
- Дать комментарии по договору

[Создать задачи] [Открыть Inbox]
```

For MVP, `Создать задачи` can create tasks from high-confidence task candidates or create pending confirmations.

## Google Calendar connector

Class:

```python
class GoogleCalendarConnector:
    async def list_events(self, user, start: datetime, end: datetime) -> list[CalendarEventDTO]: ...
    async def create_event(self, user, event: CalendarEventCreateDTO) -> ExternalEventRef: ...
```

### Calendar sync flow

```mermaid
flowchart TD
    RUN[calendar_sync job] --> FETCH[Fetch Google events next 14 days]
    FETCH --> UPSERT[Upsert calendar_events source=google]
    UPSERT --> CLEAN[Mark missing/cancelled if needed]
    CLEAN --> DONE[Update connector last_sync_at]
```

### Planning flow

```mermaid
flowchart TD
    PLAN[Daily planning] --> TASKS[Load active tasks]
    PLAN --> EVENTS[Load internal + external events]
    EVENTS --> SLOTS[Find free slots]
    TASKS --> LLM[LLM choose plan]
    SLOTS --> LLM
    LLM --> PROPOSE[Create proposed internal calendar_events]
    PROPOSE --> TELEGRAM[Send plan + confirmation buttons]
```

### Free slot algorithm MVP

Input:

- day start/end from user settings, default 09:00–19:00;
- busy events from calendar;
- tasks with due date/priority;
- minimum slot duration;
- buffer between meetings default 10 minutes.

Algorithm:

1. Build sorted busy intervals.
2. Merge overlapping intervals.
3. Subtract from working day interval.
4. Filter free intervals >= required duration.
5. Score slots:
   - earlier for urgent tasks;
   - avoid lunch if configured;
   - prefer longer uninterrupted blocks for deep work.

### External calendar writes

External writes always require confirmation.

Process:

1. Create proposed internal event with `status=proposed`.
2. Create `pending_confirmation` action `create_google_calendar_event`.
3. Telegram button “Добавить в Google Calendar”.
4. On confirmation, call Google Calendar API.
5. Update internal event `source=google` or store external ids.
6. Audit log.

## Internal calendar

Even without Google connected, Lumi must work with internal calendar.

Internal events:

- focus blocks;
- reminders;
- user-created events;
- proposed plans.

Internal events appear in Mini App Calendar.

## News connector

MVP source: RSS.

Use `feedparser`.

Default strategy:

- For each `news_topic.query`, build Google News RSS search URL or use configured RSS URLs.
- Fetch max N items per topic.
- Deduplicate by URL hash.
- Store items.
- Summarize with LLM.

### Config examples

```json
{
  "topics": [
    {"title": "AI agents", "query": "AI agents OR autonomous agents"},
    {"title": "Telegram Mini Apps", "query": "Telegram Mini Apps Bot API"},
    {"title": "LLM pricing", "query": "LLM pricing API MiniMax OpenAI Anthropic"}
  ],
  "max_items_per_topic": 10,
  "language": "ru",
  "digest_style": "executive_brief"
}
```

### News digest prompt

```text
Ты модуль новостной выжимки Lumi.
Тебе переданы новости по темам пользователя.
Сделай короткий полезный digest на русском.
Не выдумывай факты за пределами заголовка/описания/извлеченного текста.
Группируй по темам.
Для каждой темы дай:
- что произошло;
- почему это важно пользователю;
- что можно сделать/проверить.
```

Output:

```text
Главное за утро

1. AI agents
— ...

2. Telegram Mini Apps
— ...

3. LLM pricing
— ...

Что стоит сделать:
- ...
```

## Tool registry

Create backend tool registry, even if not using provider-native tool calls.

Tools:

```text
create_task
update_task
complete_task
create_reminder
find_free_calendar_slots
create_internal_calendar_block
request_external_calendar_confirmation
run_email_triage
run_news_digest
create_news_topic
create_scheduled_task
store_memory
archive_memory
```

Each tool has:

- name;
- description;
- input Pydantic schema;
- permission level;
- requires_confirmation bool/function;
- executor function;
- audit logging.

## Permissions matrix

| Tool | Auto allowed | Confirmation required |
|---|---:|---:|
| create_task | yes if clear | if low confidence |
| complete_task | yes if user explicitly says | if ambiguous |
| create_reminder | yes if clear | if ambiguous |
| store_memory | yes only explicit/high confidence | otherwise yes |
| create_internal_calendar_block | yes if user explicitly asks | if ambiguous |
| create_external_calendar_event | no | always |
| email_read_triage | yes | no, if connector already authorized |
| email_send | no | always; can be not implemented |
| email_archive/delete | no | always; not MVP |
| news_digest | yes | no |
| create_automation | no enabled by default | confirmation to enable |

## Connector status in Mini App

Settings page should show:

```text
Google: connected/disconnected/needs reauth
Gmail: available/unavailable
Calendar: available/unavailable
Last sync: ...
Scopes: ...
```

If disconnected, show setup instructions.

## Failure behavior

- Gmail unavailable: show “Google connector не подключен”.
- Calendar unavailable: Lumi still uses internal calendar.
- News RSS fetch fails: skip source, include warning in agent_run, digest with available items.
- LLM fails during triage/digest: save failed run, do not crash worker.


---

# Lumi — Frontend Mini App UI Spec

## Stack

Use:

- React
- TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- lucide-react icons
- optional: framer-motion for subtle transitions

Do not use Next.js for MVP. Mini App is a SPA served by FastAPI static files under `/app`.

## Telegram integration

Load Telegram WebApp script in `index.html`:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```

Create wrapper:

```ts
export function getTelegramWebApp(): TelegramWebApp | null
export function getInitData(): string
export function setupTelegramTheme(): void
export function haptic(type: 'light' | 'medium' | 'heavy' | 'success' | 'error'): void
```

On app startup:

1. call `Telegram.WebApp.ready()`;
2. call `Telegram.WebApp.expand()`;
3. read theme params;
4. set CSS variables;
5. include `X-Telegram-Init-Data` header on API requests.

## Visual direction

Previous UI examples were too functional and cheap. New UI must feel:

```text
premium
calm
mobile-first
elegant
soft but precise
high contrast where needed
spacious
not overloaded
```

Style keywords:

- clean glassy cards but not excessive glassmorphism;
- generous spacing;
- muted neutral palette;
- one accent color from Telegram theme;
- beautiful typography;
- subtle shadows;
- rounded cards;
- timeline with calm rhythm;
- smooth states;
- no childish gradients;
- no cluttered dashboard widgets.

## Layout

Mobile-first, iPad-friendly.

```text
AppShell
  TopBar
  Content
  BottomNav
```

Bottom navigation:

1. Today
2. Tasks
3. Calendar
4. Inbox
5. More

More page links:

- News
- Automations
- Memory
- Settings
- Agent Runs

On wider screens/iPad, optional side rail can appear.

## Design tokens

Use CSS variables:

```css
:root {
  --tg-bg: var(--tg-theme-bg-color, #f7f7f8);
  --tg-text: var(--tg-theme-text-color, #111827);
  --tg-hint: var(--tg-theme-hint-color, #6b7280);
  --tg-link: var(--tg-theme-link-color, #2481cc);
  --tg-button: var(--tg-theme-button-color, #2481cc);
  --tg-button-text: var(--tg-theme-button-text-color, #ffffff);
  --surface: rgba(255, 255, 255, 0.82);
  --surface-strong: rgba(255, 255, 255, 0.96);
  --border: rgba(15, 23, 42, 0.08);
  --shadow-soft: 0 12px 40px rgba(15, 23, 42, 0.08);
  --radius-xl: 24px;
  --radius-lg: 18px;
}
```

Respect Telegram safe area:

```css
padding-bottom: calc(env(safe-area-inset-bottom) + 72px);
```

## Pages

### 1. Today Page

This is the core wow page.

Sections:

1. Hero summary
2. Plan timeline
3. Needs attention
4. Assistant suggestions
5. Quick actions
6. Recent agent runs

Visual hierarchy:

```text
Good morning / Доброе утро
Сегодня: 4 встречи · 7 задач · 3 письма ждут ответа
```

Hero card example:

```text
┌─────────────────────────────────┐
│ Доброе утро                     │
│ Сегодня у тебя 4 встречи,       │
│ 7 задач и 3 письма с ответом.   │
│                                 │
│ [Собрать план] [Разобрать почту]│
└─────────────────────────────────┘
```

Timeline card:

```text
09:30  Standup
11:30  Focus: архитектура Lumi
14:00  Client call
16:30  Email catch-up
```

Needs attention card:

```text
Требует внимания
- Иван ждет подтверждения встречи
- 2 письма требуют ответа
- Задача “архитектура backend” без слота
```

Assistant suggestion card:

```text
Lumi предлагает
Заблокировать 14:30–16:00 под deep work.
[Принять] [Изменить]
```

API:

```text
GET /api/today
POST /api/calendar/plan-day
POST /api/inbox/triage/run
POST /api/news/digest/run
```

### 2. Tasks Page

Sections:

- quick input;
- filters: Today, Upcoming, Inbox, Done;
- task cards;
- project chips;
- swipe actions optional.

Task card:

```text
○ Написать Саше по договору
  Завтра 09:00 · medium · договор
```

Actions:

- complete;
- snooze;
- edit;
- add to calendar;
- delete/cancel.

### 3. Calendar Page

Sections:

- day switcher;
- timeline;
- external busy blocks;
- internal focus blocks;
- proposed blocks;
- free slots.

Visual distinction:

```text
Google event: solid but muted
Internal Lumi block: accent border
Proposed block: dashed border
Free slot: subtle ghost button
```

Actions:

- sync calendar;
- plan day;
- confirm proposed block;
- create internal block;
- add to Google Calendar with confirmation.

### 4. Inbox Page

Sections:

- triage summary;
- categories tabs;
- thread cards;
- suggested tasks.

Category cards:

```text
Needs reply: 3
Decision needed: 2
FYI: 8
Newsletters: 21
```

Thread card:

```text
Иван Петров · Re: договор
Ждет подтверждения времени до 14:00.
[Создать задачу] [Открыть Gmail]
```

### 5. News Page

Sections:

- topics;
- latest digest;
- run digest button;
- edit topic queries.

Topic card:

```text
AI agents
Будни 08:30 · 10 источников
[Run now] [Edit]
```

Digest card:

```text
Главное за утро
AI agents — ...
Telegram Mini Apps — ...
LLM pricing — ...
```

### 6. Automations Page

Automation cards:

```text
Утренние новости
Будни 08:30
Последний запуск: сегодня 08:31
[Run now] [Pause] [Edit]
```

Fields:

- title;
- type;
- cron;
- timezone;
- config JSON/simple form;
- enabled.

For MVP, provide simple forms for known types and optional advanced JSON editor.

### 7. Memory Page

Purpose: transparency and control.

Sections:

- active memories;
- filters by kind;
- importance;
- source if available;
- archive/delete.

Memory card:

```text
Preference
Рабочие задачи лучше группировать по проектам.
Importance 4 · from chat · last used yesterday
[Archive]
```

### 8. Settings Page

Sections:

- user profile;
- timezone;
- connector status;
- MiniMax/model status;
- Telegram bot status;
- safety settings;
- debug links.

Connector status:

```text
Google Calendar: Connected
Gmail: Connected
Last sync: 09:01
[Reconnect] [Disconnect]
```

### 9. Agent Runs Page

For backend developer visibility.

List runs:

```text
09:02 email_triage completed 12.3s
08:31 news_digest completed 18.1s
08:00 calendar_sync failed
```

Run details:

- status;
- inputs summary;
- output summary;
- tool calls;
- LLM calls;
- error.

## API client

Implement typed API client:

```ts
class LumiApiClient {
  getMe()
  getToday()
  listTasks(params)
  createTask(input)
  completeTask(id)
  listCalendarEvents(range)
  planDay(date)
  runEmailTriage()
  listNewsTopics()
  runNewsDigest()
  listAutomations()
  runAutomation(id)
  listMemories()
  archiveMemory(id)
  listAgentRuns()
}
```

Each request must include `X-Telegram-Init-Data`.

Handle 401:

- show “Открой Lumi внутри Telegram”;
- show debug details in local mode.

## Empty states

Empty states must look premium, not like errors.

Examples:

Tasks empty:

```text
Пока нет активных задач.
Напиши Lumi в чате: “Напомни завтра...”
```

Calendar disconnected:

```text
Google Calendar не подключен.
Lumi уже может вести внутренний календарь, а после подключения будет учитывать рабочие встречи.
[Подключить Google]
```

Inbox disconnected:

```text
Gmail не подключен.
После подключения Lumi сможет каждое утро показывать, где от тебя ждут ответа.
```

## Loading states

Use skeleton cards, not spinners everywhere.

## Error states

Use small inline error cards with retry.

```text
Не удалось загрузить календарь.
[Повторить]
```

## Responsive behavior

Phone:

- bottom nav;
- single column;
- large touch targets.

Tablet/iPad:

- max-width content 860px;
- optional side nav;
- cards can form 2-column grid;
- timeline remains readable.

## Accessibility

- Buttons have labels.
- Contrast must be sufficient.
- Do not rely only on color.
- Support reduced motion.

## Build/deploy

Frontend build:

```text
cd frontend && npm install && npm run build
```

FastAPI should serve `frontend/dist` at `/app`.

For local development, Vite dev server can proxy `/api` to backend.

## Quality bar

Do not leave raw unstyled HTML.
Do not build generic admin dashboard.
Do not use cheap-looking gradients or random colors.
Do not create dozens of tiny widgets.
Prioritize Today page polish.


---

# Lumi — Local Deployment and Docker Spec

## Goal

After implementation, user should be able to run Lumi locally on Mac:

```text
make setup
# fill .env
make up
make migrate
make seed
```

Then open Telegram and talk to the bot.

## Docker Compose services

Required:

```yaml
services:
  postgres:
    image: postgres:16-alpine

  redis:
    image: redis:7-alpine

  api:
    build: ./backend
    command: uvicorn lumi.main:app --host 0.0.0.0 --port 8000
    depends_on: [postgres, redis]

  bot:
    build: ./backend
    command: python -m lumi.bot.runner
    depends_on: [postgres, redis, api]

  worker:
    build: ./backend
    command: python -m lumi.worker.main
    depends_on: [postgres, redis]

  scheduler:
    build: ./backend
    command: python -m lumi.scheduler.main
    depends_on: [postgres, redis]
```

Volumes:

```text
postgres_data
redis_data optional
./data/files:/app/data/files
./data/secrets:/app/data/secrets
./frontend/dist:/app/static/app:ro optional
```

Ports:

```text
api: 8000:8000
postgres: optional 5432 local only
redis: optional 6379 local only
```

Do not expose Postgres/Redis publicly.

## .env.example

Must be complete and documented. See `13_ENV_TEMPLATE.md`.

## Makefile targets

Implement:

```makefile
setup:
	cp -n .env.example .env || true
	mkdir -p data/files data/secrets
	@echo "Fill .env with TELEGRAM_BOT_TOKEN, MINIMAX_API_KEY, ALLOWED_TELEGRAM_USER_IDS"

up:
	docker compose up --build

up-detached:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose run --rm api alembic upgrade head

revision:
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

seed:
	docker compose run --rm api python -m lumi.scripts.seed_local

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

smoke:
	docker compose run --rm api python -m lumi.scripts.smoke

google-auth-local:
	python scripts/google_auth_local.py
```

Adjust commands to actual package structure.

## Local Telegram bot setup

User actions:

1. Open BotFather.
2. Create bot.
3. Copy token.
4. Put token into `.env`:

```text
TELEGRAM_BOT_TOKEN=...
```

5. Get own Telegram user id via one of:
   - @userinfobot;
   - log unauthorized user id when sending `/start` with `LOG_UNAUTHORIZED_TELEGRAM_IDS=true`.
6. Put id:

```text
ALLOWED_TELEGRAM_USER_IDS=123456789
```

7. Run:

```text
make up
make migrate
make seed
```

8. Send `/start` to bot.

## Polling vs webhook

MVP uses polling.

Startup should call Telegram deleteWebhook or document how to run:

```text
https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true
```

In code, prefer aiogram polling and ensure webhook conflict is handled.

## Mini App local setup

Telegram Mini App requires a URL available to Telegram client.

For local testing on iPad, use HTTPS tunnel.

Recommended options:

```text
cloudflared tunnel --url http://localhost:8000
```

or:

```text
ngrok http 8000
```

Set:

```text
APP_PUBLIC_URL=https://your-tunnel-url.example
```

Then configure bot menu button or inline button to open:

```text
https://your-tunnel-url.example/app
```

Implementation should also send Mini App button from `/app` and `/start` based on `APP_PUBLIC_URL`.

If `APP_PUBLIC_URL` is empty, bot should say:

```text
Mini App URL еще не настроен. Укажи APP_PUBLIC_URL в .env после запуска HTTPS tunnel.
```

## Serving frontend

Two acceptable modes:

### Static mode

1. Build frontend.
2. FastAPI serves `frontend/dist` from `/app`.
3. Tunnel points to backend API on port 8000.

This is preferred for iPad.

### Dev mode

1. Vite dev server on localhost:5173.
2. API on localhost:8000.
3. Proxy `/api` to backend.
4. For Telegram Mini App, either tunnel Vite or use static mode.

## Database migrations

Use Alembic.

At startup, do not auto-run migrations unless `AUTO_MIGRATE=true` in local mode. Prefer explicit `make migrate`.

## Seed data

Seed script should:

1. Create user if `BOOTSTRAP_TELEGRAM_USER_ID` or allowed id exists.
2. Create main conversation.
3. Create default news topics:
   - AI agents
   - Telegram Mini Apps
   - LLM pricing
4. Create default scheduled tasks, probably disabled until user enables:
   - daily news digest weekdays 08:30
   - email triage weekdays 09:00
   - daily planning weekdays 08:45
   - calendar sync every 30 minutes
5. Print what was created.

## Secrets

Never commit:

```text
.env
data/secrets/*
google client secrets
google tokens
```

`.gitignore` must include:

```text
.env
.env.*
!.env.example
data/
secrets/
*.sqlite
frontend/dist/
__pycache__/
.pytest_cache/
node_modules/
```

## Local security

- Allowlist Telegram id.
- Reject groups.
- Do not expose DB publicly.
- Mini App API requires Telegram initData.
- Dev auth only in local mode and off by default.
- No shell/file tools for LLM.

## Mac sleep

Document that bot only runs while Mac is awake. User can temporarily prevent sleep:

```text
caffeinate -dimsu
```

Or configure macOS energy settings.

Do not make the app install system launch agents in MVP unless explicitly requested.

## Production migration later

MVP should be easy to move to VPS:

```text
polling -> webhook
local tunnel -> domain + HTTPS
local files -> S3-compatible storage
single user -> multi-user auth
manual secrets -> secrets manager
Docker Compose local -> Docker Compose VPS or managed platform
```

But do not implement production deployment now beyond clean Docker Compose.


---

# Lumi — Security and Privacy Spec

## MVP threat model

Lumi runs locally on user's Mac but receives input from Telegram and may connect to Google APIs and MiniMax.

Main risks:

1. Unauthorized Telegram user talks to bot.
2. Mini App API opened outside Telegram or by wrong user.
3. Secrets accidentally committed.
4. LLM hallucinates or executes unsafe action.
5. Email/calendar external actions happen without confirmation.
6. Over-storing personal data.
7. Logs leak sensitive content or tokens.
8. Tunnel exposes local backend to internet.

## Required controls

### Telegram allowlist

Every bot update must check:

```text
message.chat.type == "private"
message.from_user.id in ALLOWED_TELEGRAM_USER_IDS
```

Unauthorized users:

- In normal mode: ignore or minimal “Access denied”.
- In local debug mode: log user id to help setup.

No group chats in MVP.

### Mini App auth

All `/api/*` requests must validate Telegram `initData` on backend.

Reject request if:

- missing initData;
- invalid signature;
- auth date too old if expiration check implemented;
- user id not allowlisted.

Do not trust frontend-provided user object.

### Secrets

Files never committed:

```text
.env
data/secrets/*
client_secret*.json
token*.json
*.key
```

Secrets in env:

```text
TELEGRAM_BOT_TOKEN
MINIMAX_API_KEY
GOOGLE_CLIENT_SECRET
APP_SECRET_KEY
ENCRYPTION_KEY
```

Do not print secrets.

Create helper:

```python
redact_secret(value: str) -> str
```

### Encryption

Use Fernet encryption for OAuth token JSON if stored in DB.

`ENCRYPTION_KEY` must be generated locally.

Provide script:

```text
python -m lumi.scripts.generate_encryption_key
```

### Permission model

Actions requiring confirmation:

- external Google Calendar write;
- email send;
- email delete/archive/label modification;
- enabling recurring automation if extracted from ambiguous chat;
- storing sensitive memory;
- any action with confidence below threshold.

Auto-allowed actions:

- create internal task from clear user request;
- create internal reminder from clear request;
- run read-only news digest;
- run read-only email triage if connector authorized;
- run read-only calendar sync;
- create internal proposed calendar block if user explicitly asks.

### LLM tool safety

LLM never gets direct tools for:

- shell execution;
- filesystem access;
- environment variables;
- database raw SQL;
- email destructive actions;
- external calendar writes without backend confirmation.

Backend executes only registered tools.

### Audit logs

Create audit logs for:

- task created/updated/completed;
- memory stored/archived;
- external calendar write;
- email action if implemented;
- connector connected/disconnected;
- automation created/updated/run;
- confirmation accepted/rejected.

### Data minimization

Email:

- store snippets/summaries, not full bodies by default;
- full body caching controlled by `STORE_EMAIL_BODIES=false` default;
- if fetched, use for immediate triage then discard.

LLM calls:

- don't store full raw prompts by default;
- store estimates and request kind;
- raw debug payload only with explicit local flag.

Memory:

- store only useful long-term context;
- allow review/delete in Mini App;
- include source and confidence.

News:

- store source URL, title, snippet, summary.

### Tunnel risk

When using HTTPS tunnel:

- only `/app` and `/api` are exposed;
- `/api` must require auth;
- no DB/Redis exposed;
- debug endpoints require local mode and auth;
- consider IP restrictions impossible via Telegram WebView, so rely on initData validation and allowlist.

### CORS

For local:

- allow `APP_PUBLIC_URL` origin;
- allow localhost origins for dev;
- do not use `*` with credentials.

Since Telegram Mini App requests may originate from webview, test carefully. Auth should not rely on cookies.

### Error messages

Do not expose stack traces to user/API.

API returns:

```json
{"error": "unauthorized"}
```

Logs include detailed trace but no secrets.

## Privacy UI

Memory page must allow:

- see what Lumi remembers;
- archive/delete memory;
- see source type if possible;
- toggle memory auto-save later if desired.

Settings page must show:

- connected services;
- last sync time;
- whether email bodies are stored;
- debug payload storage status.

## Local-only disclaimer in docs

Document clearly:

- MVP is local/personal.
- It is not a hardened multi-user SaaS.
- For production, add stronger auth, secrets management, backups, monitoring, rate limits, and security review.


---

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


---

# Lumi — .env.example template

Create `.env.example` in repo with at least:

```dotenv
# ==========================================================
# Lumi local MVP configuration
# ==========================================================

APP_ENV=local
APP_NAME=Lumi
APP_PUBLIC_URL=
BACKEND_BASE_URL=http://localhost:8000
FRONTEND_PUBLIC_PATH=/app
DEFAULT_TIMEZONE=Europe/Moscow

# Generate with: python -m lumi.scripts.generate_secret_key
APP_SECRET_KEY=change-me-local-secret
# Generate with: python -m lumi.scripts.generate_encryption_key
ENCRYPTION_KEY=change-me-fernet-key

# ==========================================================
# Database / Redis
# ==========================================================
DATABASE_URL=postgresql+asyncpg://lumi:lumi@postgres:5432/lumi
POSTGRES_DB=lumi
POSTGRES_USER=lumi
POSTGRES_PASSWORD=lumi
REDIS_URL=redis://redis:6379/0

# ==========================================================
# Telegram
# ==========================================================
TELEGRAM_BOT_TOKEN=
ALLOWED_TELEGRAM_USER_IDS=
LOG_UNAUTHORIZED_TELEGRAM_IDS=true

# ==========================================================
# LLM
# ==========================================================
LLM_PROVIDER=minimax
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M3
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=3
LLM_CONTEXT_MAX_CHARS=120000
STORE_LLM_DEBUG_PAYLOADS=false

# ==========================================================
# Google connector
# ==========================================================
GOOGLE_OAUTH_CLIENT_SECRET_FILE=/app/data/secrets/google_client_secret.json
GOOGLE_OAUTH_TOKEN_FILE=/app/data/secrets/google_token.json
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly,https://www.googleapis.com/auth/calendar.events
STORE_EMAIL_BODIES=false

# ==========================================================
# News
# ==========================================================
NEWS_DEFAULT_TOPICS=AI agents,Telegram Mini Apps,LLM pricing
NEWS_MAX_ITEMS_PER_TOPIC=10

# ==========================================================
# Scheduler
# ==========================================================
SCHEDULER_TICK_SECONDS=30
SCHEDULER_LOCK_SECONDS=300

# ==========================================================
# Local dev only
# ==========================================================
DEV_AUTH_ENABLED=false
DEV_AUTH_TELEGRAM_USER_ID=
AUTO_MIGRATE=false
```


---

# Official/current sources to consult during implementation

These are implementation-relevant sources. If a detail conflicts with current official docs, prefer current official docs.

## Telegram

- Telegram Bot API: https://core.telegram.org/bots/api
  - getUpdates vs webhooks
  - polling/webhook mutual exclusion
  - setWebhook/deleteWebhook
  - WebAppInfo / Mini App button types
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
  - initData/initDataUnsafe
  - validating initData on backend
  - Telegram WebApp JS API
  - Mini App HTTPS/test environment behavior
- aiogram WebApp utilities: https://docs.aiogram.dev/en/latest/utils/web_app.html
  - safe_parse_webapp_init_data
  - check_webapp_signature

## MiniMax

- MiniMax text generation/model invocation: https://platform.minimax.io/docs/guides/text-generation
  - MiniMax-M3 model name
  - OpenAI-compatible base URL
  - Anthropic-compatible base URL
- MiniMax pay-as-you-go pricing: https://platform.minimax.io/docs/guides/pricing-paygo
- MiniMax Token Plan FAQ: https://platform.minimax.io/docs/token-plan/faq
- MiniMax M3 blog/release: https://www.minimax.io/blog/minimax-m3

## Google

- Google Calendar API Python quickstart: https://developers.google.com/workspace/calendar/api/quickstart/python
- Gmail API Python quickstart: https://developers.google.com/workspace/gmail/api/quickstart/python
- Google OAuth 2.0 overview: https://developers.google.com/identity/protocols/oauth2
- google-auth-oauthlib flow: https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html

## Python libraries

- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy asyncio: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic: https://alembic.sqlalchemy.org/
- aiogram: https://docs.aiogram.dev/
- arq: https://arq-docs.helpmanual.io/
- croniter: https://github.com/pallets-eco/croniter
- Pydantic: https://docs.pydantic.dev/

## Frontend

- Vite: https://vite.dev/
- React: https://react.dev/
- Tailwind CSS: https://tailwindcss.com/
- TanStack Query: https://tanstack.com/query/latest
