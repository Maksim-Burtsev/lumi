.PHONY: setup up up-detached down logs migrate revision seed test lint smoke \
	frontend-install frontend-build frontend-dev dev-auth-up dev-auth-down tunnel \
	google-auth-local reset-local-db help

help:
	@echo "Lumi — local commands"
	@echo ""
	@echo "  make setup             copy .env.example -> .env, create data dirs"
	@echo "  make frontend-build    build the Mini App (frontend/dist)"
	@echo "  make dev-auth-up       local Mini App at http://localhost:8001/app/"
	@echo "  make tunnel            HTTPS tunnel to api:8000 for Telegram Mini App"
	@echo "  make up                docker compose up --build (foreground)"
	@echo "  make up-detached       docker compose up --build -d"
	@echo "  make migrate           apply DB migrations"
	@echo "  make seed              create user/conversation/topics/automations"
	@echo "  make smoke             end-to-end smoke test with mock LLM"
	@echo "  make test              run backend pytest inside docker"
	@echo "  make logs              tail logs of all services"
	@echo "  make google-auth-local local Google OAuth flow (browser)"
	@echo "  make down              stop everything"

setup:
	cp -n .env.example .env || true
	mkdir -p data/files data/secrets
	@echo ""
	@echo "Now fill .env with:"
	@echo "  TELEGRAM_BOT_TOKEN        (from @BotFather)"
	@echo "  ALLOWED_TELEGRAM_USER_IDS (your numeric Telegram id)"
	@echo "  MINIMAX_API_KEY           (or set LLM_PROVIDER=mock)"
	@echo "  APP_SECRET_KEY / ENCRYPTION_KEY (see comments in .env)"

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
	docker compose run --rm -e LLM_PROVIDER=mock api pytest -q

lint:
	docker compose run --rm api ruff check .

smoke:
	docker compose run --rm -e LLM_PROVIDER=mock api python -m lumi.scripts.smoke

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm install && npm run build

frontend-dev:
	cd frontend && npm run dev

dev-auth-up:
	@if [ ! -f .env ]; then echo "Missing .env. Run: make setup"; exit 1; fi
	@if [ ! -f frontend/dist/index.html ]; then echo "Missing frontend/dist. Run: make frontend-build"; exit 1; fi
	@telegram_id=$$(grep -E '^ALLOWED_TELEGRAM_USER_IDS=' .env | head -n1 | cut -d= -f2- | cut -d, -f1 | tr -d '[:space:]'); \
	if [ -z "$$telegram_id" ]; then echo "ALLOWED_TELEGRAM_USER_IDS is empty in .env"; exit 1; fi; \
	docker network inspect lumi_default >/dev/null 2>&1 || { echo "Missing lumi_default network. Run: make up-detached"; exit 1; }; \
	docker rm -f lumi-api-dev-auth >/dev/null 2>&1 || true; \
	docker run -d --name lumi-api-dev-auth \
		--network lumi_default \
		--env-file .env \
		-e SERVICE_ROLE=api \
		-e DEV_AUTH_ENABLED=true \
		-e DEV_AUTH_TELEGRAM_USER_ID=$$telegram_id \
		-p 127.0.0.1:8001:8000 \
		-v "$(CURDIR)/data/files:/app/data/files" \
		-v "$(CURDIR)/data/secrets:/app/data/secrets" \
		-v "$(CURDIR)/frontend/dist:/app/static/app:ro" \
		lumi-backend:latest \
		uvicorn lumi.main:app --host 0.0.0.0 --port 8000 >/dev/null; \
	echo "Dev-auth Mini App: http://localhost:8001/app/"

dev-auth-down:
	docker rm -f lumi-api-dev-auth >/dev/null 2>&1 || true

tunnel:
	cloudflared tunnel --url http://localhost:8000

google-auth-local:
	python3 scripts/google_auth_local.py

reset-local-db:
	docker compose down -v
	@echo "Postgres/Redis volumes removed. Run: make up-detached && make migrate && make seed"
