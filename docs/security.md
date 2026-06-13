# Безопасность и приватность

MVP — локальный персональный продукт, но принимает ввод из Telegram и ходит в Google/MiniMax,
поэтому контроли реальные, не декоративные.

## Модель угроз → контроли

| Риск | Контроль |
|---|---|
| Чужой пишет боту | allowlist `ALLOWED_TELEGRAM_USER_IDS` + только private chat; чужие игнорируются (id логируется для настройки) |
| Mini App API снаружи Telegram | HMAC-валидация `initData` токеном бота (`security/telegram_auth.py`), проверка `auth_date` (24 ч), затем allowlist. `initDataUnsafe` не доверяем |
| Секреты в git | `.gitignore`: `.env*`, `data/`, `client_secret*.json`, `token*.json`, `*.key`; в репо только `.env.example` |
| Секреты в логах | JSON-логгер маскирует ключи token/key/secret/password/credential; `redact_secret()` для отображения |
| LLM делает опасное | у модели НЕТ инструментов: backend сам исполняет действия после extraction; shell/файлы/SQL недоступны принципиально |
| Внешние записи без спроса | Google Calendar write и включение автоматизаций — только через `pending_confirmations` + явный тап; email send/delete не реализованы |
| Утечка переписки в БД | тела писем не хранятся (`STORE_EMAIL_BODIES=false`), сырые промпты LLM не хранятся (`STORE_LLM_DEBUG_PAYLOADS=false`), у llm_calls только метрики |
| Туннель наружу | наружу смотрят только `/app` (статика) и `/api` (initData-auth); Postgres/Redis на 127.0.0.1; `/docs` и debug — только `APP_ENV=local`; dev-auth выключен по умолчанию |
| OAuth-токены | локально в `data/secrets/` (вне git); для БД-хранения готов Fernet (`security/crypto.py`, `ENCRYPTION_KEY`) |
| Stack traces пользователю | API отдает `{"error": "internal_error"}`, детали только в логах |

## Генерация ключей

```bash
docker compose run --rm api python -m lumi.scripts.generate_secret_key      # APP_SECRET_KEY
docker compose run --rm api python -m lumi.scripts.generate_encryption_key  # ENCRYPTION_KEY (Fernet)
```

## Прозрачность для пользователя

- **Memory** — внутренняя память контекста; пользователь не занимается её ручным менеджментом
- **Agent Runs** — каждый запуск агента, каждый tool call и LLM call с таймингами
- **audit_logs** — задачи/память/календарь/коннекторы/подтверждения
- **Settings** — статусы подключений, какие флаги приватности активны

## Дисклеймер

Это локальный однопользовательский MVP, не hardened SaaS. Перед продакшеном для
посторонних пользователей: полноценный secrets manager, бэкапы, мониторинг,
rate limiting, пентест. Список — в runbook → «Производство».
