# Runbook — операции и отладка

## Запуск с нуля

```bash
make setup              # .env из шаблона + data/
# .env: TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_IDS, MINIMAX_API_KEY
make frontend-build
make up-detached
make migrate
make seed
make smoke              # SMOKE OK = ядро живо (mock LLM, без ключей)
```

Бот: `/start` в Telegram. Mini App: см. чеклист ниже.

## Локальный Mini App в Telegram

Браузерная проверка без Telegram:

```bash
make frontend-build
make up-detached
make dev-auth-up
open http://localhost:8001/app/
```

Telegram-проверка:

```bash
make frontend-build
make up-detached
make tunnel
```

Скопируй HTTPS URL из `make tunnel` в `.env`:

```dotenv
APP_PUBLIC_URL=https://your-tunnel.trycloudflare.com
FRONTEND_PUBLIC_PATH=/app/
```

Перечитай `.env` и пересинхронизируй кнопку Mini App:

```bash
docker compose restart api bot
curl "$APP_PUBLIC_URL/health"
```

Открой `/app` у бота или кнопку меню. Если использовалась старая tunnel-ссылка,
закрой старое окно Mini App в Telegram и открой свежую кнопку.

Быстрая диагностика:

```bash
docker compose ps
docker compose logs api bot -f --tail 100
curl "$APP_PUBLIC_URL/app/"
```

В норме в логах `api` видны `GET /app`, загрузка ассетов и `GET /api/today` со статусом
`200`. Если Telegram показывает только белый экран с роботом, почти всегда причина одна из
трех: tunnel умер после сна Mac, `APP_PUBLIC_URL` указывает на старый tunnel, или Telegram
WebView открыл закешированную старую кнопку.

## Ежедневные команды

```bash
make logs                                   # все сервисы
docker compose logs bot -f --tail 100       # только бот
docker compose restart bot api              # после смены .env
make test                                   # 48 pytest в контейнере
make down / make up-detached                # стоп/старт
make reset-local-db                         # снести volumes (данные!) и начать заново
```

Логи — JSON-строки с корреляцией: `request_id` (API), `agent_run_id` (агентные операции),
`telegram_update_id` (бот). История запусков — Mini App → Agent Runs (статусы, длительности,
tool calls, LLM calls, ошибки).

## Типовые проблемы

| Симптом | Причина → решение |
|---|---|
| Бот молчит | 1) `docker compose logs bot` — крутится ли polling. 2) Твой id не в `ALLOWED_TELEGRAM_USER_IDS` — в логах будет `unauthorized telegram user` с id (включено `LOG_UNAUTHORIZED_TELEGRAM_IDS`). 3) Токен неверный. |
| `bot` в Restarting | `TELEGRAM_BOT_TOKEN` пуст — заполни .env, `docker compose restart bot` |
| Conflict: terminated by other getUpdates | Где-то запущен второй инстанс бота ИЛИ висит webhook. Бот сам делает deleteWebhook при старте; вручную: `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true` |
| Mini App: «Открой Lumi внутри Telegram» (401) | Mini App открыт не из Telegram. Для браузера используй `make dev-auth-up` и `http://localhost:8001/app/`. |
| Mini App не открывается с кнопки | URL должен быть **https** (туннель), `APP_PUBLIC_URL` должен быть текущим, после смены нужен `docker compose restart api bot`. |
| Mini App висит на белом экране с роботом | Старый/мертвый tunnel или stale Telegram WebView. Проверь `curl "$APP_PUBLIC_URL/health"`, логи `api`, закрой старое окно Mini App и открой свежую кнопку `/app`. |
| Ответы «Готово, я это зафиксировал» на всё | Работает mock LLM: `MINIMAX_API_KEY` пуст или `LLM_PROVIDER=mock`. В логах api/worker: `falling back to mock` |
| MiniMax error в ответах | `docker compose logs worker api \| grep -i minimax` — ключ/квота/таймаут; ретраи и фоллбеки уже встроены |
| «Очередь задач недоступна» | Redis упал: `docker compose ps redis`, `docker compose up -d redis` |
| Run висит в queued | Worker не жив: `docker compose logs worker`. Перезапусти `docker compose restart worker` |
| Автоматизация не срабатывает | Включена ли (Mini App → Automations)? `next_run_at` в будущем? Логи scheduler: `scheduled job enqueued` |
| Google: needs_reauth | Токен протух без refresh — повтори `make google-auth-local` |
| Миграция падает | `docker compose logs postgres`; крайний случай: `make reset-local-db && make migrate && make seed` |
| Напоминание не пришло | Worker-cron каждую минуту; проверь `reminder_at` (UTC в БД!), логи worker `cron:send_due_reminders` |

## Отладка контекста LLM

```bash
curl -s localhost:8000/api/debug/context/latest \
  -H "X-Telegram-Init-Data: <initData>" | python3 -m json.tool
```

(только `APP_ENV=local`; снапшот пишется в `agent_runs.metadata` каждого chat-рана).
Для разработки без Telegram: `DEV_AUTH_ENABLED=true` + `DEV_AUTH_TELEGRAM_USER_ID=<id>`
в .env — API будет аутентифицировать без initData. Не включай за туннелем!

## Mac засыпает — бот останавливается

```bash
caffeinate -dimsu          # держать Mac бодрым, пока терминал открыт
```

## Производство

MVP сознательно локальный. Путь на VPS:

```text
polling → webhook (bot/runner.py, нужен HTTPS-домен)
туннель → домен + reverse proxy (caddy/traefik)
.env → secrets manager
один пользователь → мультиюзер (allowlist уже список; добавить onboarding)
+ бэкапы Postgres, мониторинг, rate limits, security review
```

Docker Compose переносится на VPS как есть (`restart: unless-stopped` уже стоит).
