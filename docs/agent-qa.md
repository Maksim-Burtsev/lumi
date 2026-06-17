# Agent self-QA

Этот чеклист обязателен для нетривиальных изменений Lumi, особенно для бота,
Mini App, planner/orchestrator, tools, DB state, observability и Telegram UX.

## Canonical manual path

Основной ручной путь: Telegram Web в Chrome, автоматизированный через Chrome/CDP.
Он использует реальную сессию пользователя, настоящего Telegram-бота и тот же Mini App
iframe, который видит пользователь.

Native Telegram Desktop — только дополнительная ручная cross-check проверка. Ее не
считать обязательной для агента: стабильная автоматизация Desktop зависит от macOS
Accessibility и локальных разрешений.

## Isolated QA runtime

Для рискованных изменений не трогай основной compose project. Поднимай отдельный
worktree и отдельный project:

```bash
git worktree add -b codex/<task> .worktrees/<task> main
cd .worktrees/<task>
```

Перед запуском compose в новом worktree скопируй `.env` из основного checkout,
если файла нет: из `.worktrees/<task>` выполни `cp ../../.env .env`.

Используй override с отдельными портами:

```bash
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose up -d --build api bot worker
```

Не запускай второй Telegram poller на тот же token. Если `lumi_fix-bot-1` активен,
основной/default bot должен быть остановлен.

## Mini App setup

Mini App в Telegram требует HTTPS URL. `localhost` недостаточен.

```bash
make frontend-build
cloudflared tunnel --url http://localhost:18000
```

В `.env` worktree:

```dotenv
APP_PUBLIC_URL=https://your-fresh-tunnel.trycloudflare.com
FRONTEND_PUBLIC_PATH=/app/
```

После смены URL пересоздай процессы, которые читают `.env` и выставляют Telegram menu:

```bash
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose up -d --force-recreate api bot worker
```

Проверки:

```bash
curl http://localhost:18000/health
curl "$APP_PUBLIC_URL/health"
curl "$APP_PUBLIC_URL/app/"
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose logs bot --tail 200 | rg "mini app menu button set|mini app chat menu button set"
```

Если Mini App в Telegram показывает белый экран или робота, сначала проверь stale
tunnel/menu: текущий `APP_PUBLIC_URL`, fresh `curl "$APP_PUBLIC_URL/health"`, bot logs
и закрыто ли старое окно Mini App.

## Required real-user flows

Проверяй не только happy path и не только русский язык. Минимальный набор:

- Telegram chat action: создать задачу.
- Follow-up на недавнее действие: обновить эту/последнюю задачу, например привязать
  к проекту.
- Exact-title flow: обновить задачу по названию.
- Ambiguous flow: несколько похожих задач дают pending confirmation/buttons, а не
  ложный success.
- Missing-candidate flow: безопасное уточнение, без фейкового "готово".
- Ordinary no-tool question: обычный ответ без tool execution.
- English + Russian phrasing for realistic user messages.
- Mini App load from Telegram menu: `/app`, assets, `/api/settings`, `/api/today`.

Для planner/tool изменений дополнительно проверь:

- запросы на Lumi state идут через structured `tool_calls`;
- backend, а не final_chat, формирует success для выполненных actions;
- final_chat не пишет success, если backend action не был выполнен.

## Evidence to collect

После ручных Telegram flows проверь БД, логи и Mini App.

```bash
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose exec postgres psql -U lumi -d lumi
```

Полезные SQL:

```sql
select created_at, tool_name, status, result_json
from tool_calls
order by created_at desc
limit 20;

select created_at, title, project, status
from tasks
order by created_at desc
limit 20;

select created_at, status, prompt, metadata
from pending_confirmations
order by created_at desc
limit 20;

select created_at, status, result_summary, metadata->'planner_trace' as planner_trace
from agent_runs
order by created_at desc
limit 20;

select created_at, provider, model, status, metadata
from llm_calls
order by created_at desc
limit 20;
```

Логи:

```bash
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose logs api bot worker --tail 300
```

Минимальная evidence summary перед "готово":

- automated checks: exact commands + pass/fail;
- real Telegram Web flows: messages sent + observed bot replies;
- Mini App: tunnel URL + `/app` loaded + API endpoints seen in logs;
- DB: `tool_calls`, `tasks`/`pending_confirmations`, `agent_runs.metadata.planner_trace`,
  `llm_calls`;
- any skipped native-app/manual checks and why.

## Release gates

Не релизить, если выполняется хоть одно условие:

- action request не создает нужный `tool_call`;
- есть fake success без completed `tool_call` и соответствующей записи в
  `tasks`/`pending_confirmations`;
- follow-up на недавнее backend action теряет state;
- ambiguous task reference auto-updates не тот объект вместо confirmation;
- planner trace не пишет sanitized причину провала;
- Mini App menu указывает на stale tunnel;
- `backend/uv.lock` появился untracked;
- основной/default bot и QA bot одновременно poll один token.
