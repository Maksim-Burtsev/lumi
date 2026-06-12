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
