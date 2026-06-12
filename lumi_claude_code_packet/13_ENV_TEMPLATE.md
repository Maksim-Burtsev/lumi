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
