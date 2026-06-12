# Коннекторы

Все внешние интеграции изолированы за интерфейсами в `backend/src/lumi/connectors/`.
LLM никогда не вызывает внешние API — только backend-сервисы через коннекторы,
с логированием в `tool_calls`/`audit_logs`.

## Google (Gmail + Calendar)

### Подключение — локальный OAuth (рекомендуемый для MVP)

```bash
# 1. Google Cloud Console: проект → OAuth client "Desktop app"
#    Включить APIs: Gmail API, Google Calendar API
#    OAuth consent screen → test users → добавить свой аккаунт
# 2. Скачанный JSON →
cp ~/Downloads/client_secret_*.json data/secrets/google_client_secret.json
# 3. На хосте (не в Docker):
make google-auth-local
```

Скрипт `scripts/google_auth_local.py` поднимает `InstalledAppFlow`, открывает браузер
и сохраняет токен в `data/secrets/google_token.json`. Каталог смонтирован в контейнеры —
backend подхватывает токен сразу, рефрешит сам и пишет обновлённый обратно.

Scopes (read-only почта, чтение календаря + создание событий после подтверждения):

```text
gmail.readonly · calendar.readonly · calendar.events
```

Статус: Mini App → Settings → Google, или `GET /api/connectors/google/status`.
Отключение: кнопка Disconnect (удаляет токен-файл).

### Gmail — только чтение

`GmailConnector.list_recent_threads(since, max_results)` → треды с метаданными
(From/To/Subject/Date/labels/snippet). Тела писем загружаются только при
`STORE_EMAIL_BODIES=true` (по умолчанию false — данные минимизированы).

Triage (`EmailService.triage_inbox`): синк за 36 ч → LLM-классификация по категориям
needs_reply / waiting_for_me / decision_needed / fyi / newsletter / invoice_document /
ignore → важность 1–5, summary, suggested_action, task_candidate → дайджест в Telegram
с кнопкой «Создать задачи (N)». Send/delete/archive не реализованы намеренно.

### Google Calendar

`GoogleCalendarConnector.list_events(start, end)` — синк 14 дней вперёд в
`calendar_events (source=google)`, upsert по внешнему id, каждые 30 минут автоматизацией.

`create_event(...)` вызывается **только** из `ConfirmationExecutor` после явного «да»
пользователя в Telegram. Без Google внутренний календарь полностью функционален.

## Яндекс.Календарь (CalDAV, read-only)

Подключается прямо из Mini App: **Settings → Яндекс.Календарь**.

1. Создай пароль приложения: id.yandex.ru → Безопасность → Пароли приложений → «Календарь CalDAV».
2. Введи логин Яндекса и этот пароль в форму — Lumi проверит доступ (листинг календарей)
   и сохранит креды **зашифрованными Fernet** в таблице `connectors`.
3. Синк каждые 14 дней вперёд входит в общий `calendar_sync` (вместе с Google, если он
   тоже подключен): события появляются в `calendar_events (source=yandex)` и учитываются
   в свободных слотах и плане дня.

Только чтение: записи в Яндекс.Календарь нет вообще (даже с подтверждением).
Реализация: `connectors/yandex/caldav_client.py` (библиотека caldav, развёрнутые
повторяющиеся события через server-side expand).

## Новости (RSS / Google News)

`RssNewsConnector.fetch_topic(query, language, max_items)`:
по умолчанию строится Google News search RSS (`news.google.com/rss/search?q=…`),
либо явные `feed_urls` в config темы. Дедуп по sha256(url). Мёртвый фид пропускается
с warning — дайджест собирается из остального. Если LLM недоступна, дайджест
деградирует до списка заголовков (graceful fallback).

Конфиг темы (JSONB `news_topics.config`):

```json
{"max_items": 10, "feed_urls": ["https://example.com/feed.xml"]}
```

## Матрица разрешений

| Действие | Авто | Подтверждение |
|---|---|---|
| создать задачу/напоминание | да, при ясном запросе (conf ≥ 0.85) | при низкой уверенности |
| сохранить память | только явное «запомни» / очень высокая уверенность | иначе да |
| внутренний блок календаря | да, при явной просьбе | при неоднозначности |
| **запись во внешний Google Calendar** | никогда | **всегда** |
| чтение Яндекс.Календаря | да (если подключен) | — |
| запись в Яндекс.Календарь | никогда | не реализовано (RO by design) |
| чтение почты / triage | да (если подключено) | — |
| **отправка/удаление почты** | никогда | не реализовано в MVP |
| новостной дайджест | да | — |
| включить автоматизацию | никогда | всегда |

## Как добавить Outlook (после MVP)

1. `connectors/microsoft/` — auth (MSAL) + `OutlookMailConnector` с теми же DTO,
   что у `GmailConnector` (`EmailThreadDTO`/`EmailMessageDTO`).
2. `EmailService` принимает коннектор в конструкторе — выбор по `connectors.type`.
3. Новый `connector_type` enum-значение + строка в Settings UI.
Структура DTO специально провайдер-нейтральна — менять сервис/LLM-промпты не придётся.
