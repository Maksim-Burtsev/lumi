.PHONY: setup up up-detached down logs migrate revision seed test lint smoke \
	frontend-install frontend-build frontend-dev google-auth-local reset-local-db help

help:
	@echo "Lumi — local commands"
	@echo ""
	@echo "  make setup             copy .env.example -> .env, create data dirs"
	@echo "  make frontend-build    build the Mini App (frontend/dist)"
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

google-auth-local:
	python3 scripts/google_auth_local.py

reset-local-db:
	docker compose down -v
	@echo "Postgres/Redis volumes removed. Run: make up-detached && make migrate && make seed"
