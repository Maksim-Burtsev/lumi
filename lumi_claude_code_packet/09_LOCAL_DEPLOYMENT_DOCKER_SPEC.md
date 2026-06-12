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
