# Agent self-QA

This checklist is mandatory for non-trivial Lumi changes, especially bot, Mini App, planner/orchestrator, tools, DB state, observability, and Telegram UX changes.

## Canonical manual path

Primary manual path: Telegram Web in Chrome, automated through Chrome/CDP. It uses the real user session, the real Telegram bot, and the same Mini App iframe the user sees.

Native Telegram Desktop is only an additional manual cross-check. Do not treat it as mandatory for the agent: stable Desktop automation depends on macOS Accessibility and local permissions.

## Isolated QA runtime

For risky changes, do not touch the main compose project. Use a separate worktree and compose project:

```bash
git worktree add -b codex/<task> .worktrees/<task> main
cd .worktrees/<task>
```

Before running compose in a new worktree, copy `.env` from the main checkout if it is missing. From `.worktrees/<task>`, run `cp ../../.env .env`.

Use a branch-specific compose project with separate ports:

```bash
export COMPOSE_PROJECT_NAME=lumi_<task_slug>
export LUMI_API_PORT=18000
export LUMI_POSTGRES_PORT=15432
export LUMI_REDIS_PORT=16379
export LUMI_DEV_AUTH_PORT=18001
docker compose up -d --build api bot worker
```

Use a unique `COMPOSE_PROJECT_NAME` for every agent branch. Do not run a second Telegram poller on the same token. If `lumi_<task_slug>-bot-1` is active, the main/default bot must be stopped.

## Mini App setup

Telegram Mini App requires an HTTPS URL. `localhost` is not enough.

```bash
make frontend-build
cloudflared tunnel --url http://localhost:${LUMI_API_PORT:-18000}
```

In the worktree `.env`:

```dotenv
APP_PUBLIC_URL=https://your-fresh-tunnel.trycloudflare.com
FRONTEND_PUBLIC_PATH=/app/
```

After changing the URL, recreate processes that read `.env` and set the Telegram menu:

```bash
docker compose up -d --force-recreate api bot worker
```

Checks:

```bash
curl "http://localhost:${LUMI_API_PORT:-18000}/health"
curl "$APP_PUBLIC_URL/health"
curl "$APP_PUBLIC_URL/app/"
docker compose logs bot --tail 200 | rg "mini app menu button set|mini app chat menu button set"
```

If Telegram Mini App shows a blank page or robot icon, first check for stale tunnel/menu: current `APP_PUBLIC_URL`, fresh `curl "$APP_PUBLIC_URL/health"`, bot logs, and whether the old Mini App window was closed.

## Required real-user flows

Check more than the happy path, and check both English and Russian phrasing. Minimum set:

- Telegram chat action: create a task.
- Follow-up on a recent action: update this/the latest task, for example attach it to a project.
- Exact-title flow: update a task by title.
- Ambiguous flow: several similar tasks produce pending confirmation/buttons, not a false success.
- Missing-candidate flow: safe clarification, no fake "done".
- Ordinary no-tool question: normal answer without tool execution.
- English + Russian phrasing for realistic user messages.
- Mini App load from Telegram menu: `/app`, assets, `/api/settings`, `/api/today`.

For planner/tool changes, also verify:

- requests for Lumi state go through structured `tool_calls`;
- backend, not final_chat, forms success for executed actions;
- final_chat does not claim success if the backend action was not executed.

## Evidence to collect

After manual Telegram flows, check DB, logs, and Mini App.

```bash
COMPOSE_PROJECT_NAME=lumi_fix \
COMPOSE_FILE=docker-compose.yml:/tmp/lumi-fix.override.yml \
docker compose exec postgres psql -U lumi -d lumi
```

Useful SQL:

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

Logs:

```bash
docker compose logs api bot worker --tail 300
```

Minimum evidence summary before saying "done":

- automated checks: exact commands + pass/fail;
- real Telegram Web flows: messages sent + observed bot replies;
- Mini App: tunnel URL + `/app` loaded + API endpoints seen in logs;
- DB: `tool_calls`, `tasks`/`pending_confirmations`, `agent_runs.metadata.planner_trace`, `llm_calls`;
- any skipped native-app/manual checks and why.

## Release gates

Do not release if any condition is true:

- action request does not create the required `tool_call`;
- fake success exists without completed `tool_call` and a matching row in `tasks`/`pending_confirmations`;
- follow-up on a recent backend action loses state;
- ambiguous task reference auto-updates the wrong object instead of asking for confirmation;
- planner trace does not write a sanitized failure reason;
- Mini App menu points at a stale tunnel;
- `backend/uv.lock` appears untracked;
- main/default bot and QA bot poll the same token at the same time.

## Finish cleanup

If an agent started Docker, a dev-auth container, or a cloudflared tunnel, it must clean its own runtime after the task finishes or after the PR is confirmed merged:

```bash
COMPOSE_PROJECT_NAME=lumi_<task_slug> make agent-clean
docker ps --filter "label=com.docker.compose.project=lumi_<task_slug>"
```

Use `make agent-clean-full` only for disposable QA runtimes where removing Postgres/Redis volumes is acceptable. Never clean the default/shared `lumi` compose project unless the user explicitly asked for that runtime to stop.
