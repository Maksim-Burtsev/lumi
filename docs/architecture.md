# Архитектура Lumi

Главный принцип: **LLM stateless, backend stateful**. Провайдер модели не хранит ничего —
каждый вызов получает свежесобранный контекст из Postgres. Это делает систему переносимой
между провайдерами, отлаживаемой и дешёвой в управлении контекстом.

## Сервисы (Docker Compose)

| Сервис | Команда | Назначение |
|---|---|---|
| `postgres` | postgres:16-alpine | вся правда: сообщения, задачи, память, календарь, журналы |
| `redis` | redis:7-alpine | очередь arq, координация |
| `api` | `uvicorn lumi.main:app` | REST для Mini App, валидация initData, статика `/app` |
| `bot` | `python -m lumi.bot.runner` | aiogram long polling, команды, колбэки |
| `worker` | `python -m lumi.worker.main` | arq: дайджесты, triage, планирование, синк, напоминания (cron), compaction |
| `scheduler` | `python -m lumi.scheduler.main` | каждые 30 с: due `scheduled_tasks` → очередь |

Все четыре python-процесса используют один образ `lumi-backend` (один `build`, разные команды).

## Карта системы

```mermaid
flowchart TD
    U[Пользователь в Telegram] -->|private chat| TG[Telegram Bot API]
    TG -->|long polling| BOT[bot · aiogram]
    BOT --> GUARD[allowlist + private-only]
    GUARD --> ORCH[AssistantOrchestrator]
    ORCH --> EXTR[SignalExtractor]
    ORCH --> CTX[ContextBuilder]
    ORCH --> LLMGW[LLMGateway]
    LLMGW --> MMX[MiniMax M3]
    LLMGW --> MOCK[MockLLM]
    ORCH --> SVCS[TaskService · CalendarService · MemoryService · ConfirmationService]
    SVCS --> PG[(Postgres)]
    CTX --> PG

    MA[Mini App · React/Vite] -->|X-Telegram-Init-Data| API[api · FastAPI]
    API --> AUTH[validate_init_data + allowlist]
    API --> SVCS

    SCHED[scheduler] -->|due tasks| Q[(Redis · arq)]
    API -->|run now| Q
    BOT -->|/plan /news /email| Q
    Q --> WRK[worker]
    WRK --> SVCS
    WRK --> LLMGW
    WRK --> GOOGLE[Gmail / Google Calendar]
    WRK --> RSS[Google News RSS]
    WRK -->|sendMessage| TG
```

## Поток сообщения в чате

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant B as bot
    participant O as Orchestrator
    participant DB as Postgres
    participant L as LLM (MiniMax/mock)

    U->>B: «Напомни завтра в 10 написать Саше»
    B->>O: handle_user_message()
    O->>DB: save Message(user), create AgentRun(chat)
    O->>L: signal_extraction → JSON
    O->>DB: create Task + reminder, log ToolCall
    O->>DB: ContextBuilder: profile/tasks/calendar/memory/summary/recent
    O->>L: final_chat (полный контекст + результаты действий)
    O->>DB: save Message(assistant), AgentRun completed
    B-->>U: ответ + кнопки [✓ Выполнено] [⏰ Отложить]
    B->>B: needs_compaction? → enqueue compact_conversation
```

Ключевая деталь: extraction и финальный ответ — **два разных вызова LLM**. Extraction
возвращает строгий JSON и может тихо упасть (чат продолжит работать); финальный ответ
получает в контексте список уже выполненных backend-действий, поэтому не выдумывает.

## Поток Mini App

```mermaid
sequenceDiagram
    participant WA as Mini App
    participant API as FastAPI
    participant DB as Postgres

    WA->>WA: Telegram.WebApp.initData
    WA->>API: GET /api/today + X-Telegram-Init-Data
    API->>API: HMAC-проверка initData (токен бота)
    API->>API: id ∈ ALLOWED_TELEGRAM_USER_IDS?
    API->>DB: ensure_user + агрегация Today
    API-->>WA: JSON → premium UI
```

«Run now»-эндпоинты (`plan-day`, `triage/run`, `digest/run`, `automations/{id}/run`)
создают `agent_run`, **коммитят** и кладут джобу в Redis; фронт поллит
`GET /api/agent-runs/{id}` каждые 1.5 с до `completed/failed` и перезапрашивает данные.

## Поток автоматизаций

```mermaid
sequenceDiagram
    participant S as scheduler
    participant DB as Postgres
    participant R as Redis
    participant W as worker
    participant TG as Telegram

    S->>DB: SELECT scheduled_tasks WHERE next_run_at <= now FOR UPDATE SKIP LOCKED
    S->>DB: locked_until = now + 300s (защита от двойного запуска)
    S->>DB: create AgentRun(queued)
    S->>R: enqueue_job(run_news_digest, …)
    S->>DB: next_run_at = croniter.next() в TZ пользователя
    W->>R: consume
    W->>DB: mark running → выполняет → mark completed/failed
    W->>DB: failure_count/last_error на scheduled_task
    W->>TG: дайджест/план/напоминание пользователю
```

Напоминания — отдельный arq-cron в worker (каждую минуту): `find_due_reminders()`
по всем пользователям, отправка с кнопками, идемпотентность через `metadata.reminder_sent_at`.

## Слои кода

```text
bot/api  →  assistant/orchestrator  →  services  →  connectors / llm  →  DB / внешние API
```

- `lumi/assistant/` — orchestrator, context_builder, signal_extractor, memory_service, compaction, prompts
- `lumi/services/` — tasks, calendar, planning, email, news, automations, confirmations, today, runs, audit, users, notifier
- `lumi/connectors/` — google (auth/gmail/calendar), news (rss)
- `lumi/llm/` — base (протокол), minimax, mock, gateway (логирование llm_calls), json_utils
- `lumi/security/` — telegram_auth (HMAC initData), crypto (Fernet)
- `lumi/api/` — deps (auth), routes/*, serializers, run_helper
- `lumi/bot/` — handlers, keyboards, formatting, runner
- `lumi/worker/`, `lumi/scheduler/` — фоновая часть

Правило: хендлеры бота и роуты API не трогают MiniMax/Gmail/Calendar напрямую — только
через сервисы и коннекторы. Каждое действие агента — строка в `tool_calls`, каждый вызов
модели — в `llm_calls`, каждый запуск — в `agent_runs` (см. страницу Agent Runs в Mini App).

## Жизненный цикл agent run

```text
queued → running → completed
                 → failed (error_message, error_json)
```

`trigger`: `telegram_message` / `telegram_command` / `telegram_callback` / `scheduled_task` / `manual_api` / `system`.

## Подтверждения (двухфазные действия)

Рискованные или низкоуверенные действия не выполняются сразу:

```text
SignalExtractor → PendingConfirmation(pending) + кнопки [✓]/[✗] в Telegram
→ callback confirm:<id> → ConfirmationExecutor → действие → audit_log
```

Всегда через подтверждение: запись во внешний Google Calendar, включение автоматизаций,
задачи/память с confidence ниже порога. Email-отправка/удаление не реализованы вовсе (by design).

## Точки расширения

| Сегодня | Замена | Где менять |
|---|---|---|
| MiniMax M3 | OpenAI/Anthropic/локальная | `lumi/llm/` — новый провайдер за `LLMProvider` |
| Gmail | Outlook | `lumi/connectors/` + `EmailService` |
| keyword-память | pgvector | `MemoryService.retrieve_relevant` |
| polling | webhook | `bot/runner.py` |
| локальные файлы | S3 | `files`-таблица уже есть |
