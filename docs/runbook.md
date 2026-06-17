# Runbook: Operations and Debugging

## Start from scratch

```bash
make setup              # .env from template + data/
# .env: TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_IDS, MINIMAX_API_KEY
make frontend-build
make up-detached
make migrate
make seed
make smoke              # SMOKE OK = core is alive (mock LLM, no external keys)
```

Bot: send `/start` in Telegram. Mini App: see the checklist below.

## Local Telegram Mini App

Browser check without Telegram:

```bash
make frontend-build
make up-detached
make dev-auth-up
open http://localhost:8001/app/
```

Telegram check:

```bash
make miniapp-local-up
```

The command builds the frontend, starts Docker, creates a fresh `cloudflared` tunnel, updates `.env`, recreates `api/bot`, and verifies the Telegram menu button for the default menu and every `ALLOWED_TELEGRAM_USER_IDS` chat.

Manual path:

```bash
make frontend-build
make up-detached
make tunnel
```

Copy the HTTPS URL from `make tunnel` into `.env`:

```dotenv
APP_PUBLIC_URL=https://your-tunnel.trycloudflare.com
FRONTEND_PUBLIC_PATH=/app/
```

Reload `.env` and resync the Mini App button:

```bash
docker compose up -d --force-recreate api bot
curl "$APP_PUBLIC_URL/health"
```

Open `/app` from the bot or use the menu button. If an old tunnel URL was used, close the old Mini App window in Telegram and open the fresh button.

Quick diagnostics:

```bash
docker compose ps
docker compose logs api bot -f --tail 100
curl "$APP_PUBLIC_URL/app/"
python3 scripts/miniapp_local_up.py
```

Expected API logs: `GET /app`, asset loads, and `GET /api/today` with status `200`. If Telegram shows only a blank page or robot icon, the cause is almost always one of four things: the tunnel died after the Mac slept, `APP_PUBLIC_URL` points at an old tunnel, containers were only restarted and did not reread `.env`, or Telegram opened a stale chat-specific button. The bot syncs both the default menu and per-chat menu for `ALLOWED_TELEGRAM_USER_IDS` on startup; logs should include `mini app menu button set` and `mini app chat menu button set`.

## Daily commands

```bash
make logs                                      # all services
docker compose logs bot -f --tail 100          # bot only
docker compose up -d --force-recreate bot api  # after .env changes
make test                                      # pytest in container
make down / make up-detached                   # stop/start
make reset-local-db                            # remove volumes (data!) and start over
```

Logs are JSON lines with correlation fields: `request_id` (API), `agent_run_id` (agent operations), `telegram_update_id` (bot). Run history is in Mini App -> Agent Runs: statuses, durations, tool calls, LLM calls, errors.

## Agent self-QA

For non-trivial bot, Mini App, planner/tools, or observability changes, the agent must pass [agent self-QA](agent-qa.md): isolated worktree/runtime, Telegram Web through Chrome/CDP, Mini App through HTTPS tunnel, DB/log evidence, and release gates.

## Common issues

| Symptom | Cause -> fix |
|---|---|
| Bot is silent | 1) `docker compose logs bot`: check whether polling is running. 2) Your id is not in `ALLOWED_TELEGRAM_USER_IDS`; logs show `unauthorized telegram user` with the id when `LOG_UNAUTHORIZED_TELEGRAM_IDS` is enabled. 3) Token is wrong. |
| `bot` is Restarting | `TELEGRAM_BOT_TOKEN` is empty; fill `.env`, then `docker compose restart bot`. |
| Conflict: terminated by other getUpdates | A second bot instance is running somewhere OR a webhook is still set. The bot calls deleteWebhook on startup; manual fix: `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true`. |
| Mini App says "Open Lumi inside Telegram" (401) | Mini App was opened outside Telegram. For browser checks use `make dev-auth-up` and `http://localhost:8001/app/`. |
| Mini App does not open from the button | URL must be **https** (tunnel), `APP_PUBLIC_URL` must be current, and after changing it you need `docker compose up -d --force-recreate api bot`. |
| Mini App hangs on a blank page or robot icon | Old/dead tunnel, containers did not reread `.env`, or stale chat-specific menu. Run `make miniapp-local-up`; check `curl "$APP_PUBLIC_URL/health"`, `api/bot` logs, close the old Mini App window, and reopen the fresh `/app` button. |
| Bot replies "Done, I recorded that" to everything | Mock LLM is active: `MINIMAX_API_KEY` is empty or `LLM_PROVIDER=mock`. API/worker logs show `falling back to mock`. |
| MiniMax error in replies | `docker compose logs worker api \| grep -i minimax`; check key/quota/timeout. Retries and fallbacks are already built in. |
| "Task queue unavailable" | Redis is down: `docker compose ps redis`, `docker compose up -d redis`. |
| Run is stuck in queued | Worker is not alive: `docker compose logs worker`; restart with `docker compose restart worker`. |
| Automation does not run | Is it enabled in Mini App -> Automations? Is `next_run_at` in the future? Scheduler logs should show `scheduled job enqueued`. |
| Google: needs_reauth | Token expired without refresh; rerun `make google-auth-local`. |
| Migration fails | `docker compose logs postgres`; last resort: `make reset-local-db && make migrate && make seed`. |
| Reminder did not arrive | Worker cron runs every minute; check `reminder_at` (UTC in DB) and worker logs for `cron:send_due_reminders`. |

## Debug LLM context

```bash
curl -s localhost:8000/api/debug/context/latest \
  -H "X-Telegram-Init-Data: <initData>" | python3 -m json.tool
```

Only with `APP_ENV=local`; the snapshot is written to `agent_runs.metadata` for every chat run. For development without Telegram, set `DEV_AUTH_ENABLED=true` + `DEV_AUTH_TELEGRAM_USER_ID=<id>` in `.env`; the API will authenticate without initData. Do not enable this behind the tunnel.

## Mac sleeps, bot stops

```bash
caffeinate -dimsu          # keep the Mac awake while the terminal is open
```

## Production

The MVP is intentionally local. VPS path:

```text
polling -> webhook (bot/runner.py, requires HTTPS domain)
tunnel -> domain + reverse proxy (caddy/traefik)
.env -> secrets manager
single user -> multi-user (allowlist is already a list; add onboarding)
+ Postgres backups, monitoring, rate limits, security review
```

Docker Compose can be moved to a VPS as-is (`restart: unless-stopped` is already set).

For Mini App real-time `/api/realtime`, use a long-running backend and a reverse proxy without SSE response buffering: disable response buffering/gzip for this path and configure a long read timeout. Serverless request runtime is not suitable for this endpoint.
