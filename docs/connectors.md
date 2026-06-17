# Connectors

All external integrations are isolated behind interfaces in `backend/src/lumi/connectors/`. The LLM never calls external APIs; only backend services call connectors, with logging in `tool_calls` / `audit_logs`.

## Google (Gmail + Calendar)

### Connection: local OAuth (recommended for the MVP)

```bash
# 1. Google Cloud Console: project -> OAuth client "Desktop app"
#    Enable APIs: Gmail API, Google Calendar API
#    OAuth consent screen -> test users -> add your account
# 2. Downloaded JSON ->
cp ~/Downloads/client_secret_*.json data/secrets/google_client_secret.json
# 3. On the host, not in Docker:
make google-auth-local
```

`scripts/google_auth_local.py` starts `InstalledAppFlow`, opens a browser, and stores the token in `data/secrets/google_token.json`. The directory is mounted into containers, so the backend picks up the token immediately, refreshes it, and writes the refreshed token back.

Scopes: read-only mail, calendar read, and event creation after confirmation:

```text
gmail.readonly · calendar.readonly · calendar.events
```

Status: Mini App -> Settings -> Google, or `GET /api/connectors/google/status`.
Disconnect: the Disconnect button removes the token file.

### Gmail: read-only

`GmailConnector.list_recent_threads(since, max_results)` returns threads with metadata (From/To/Subject/Date/labels/snippet). Email bodies are loaded only when `STORE_EMAIL_BODIES=true`; by default this is false to minimize stored data.

Triage (`EmailService.triage_inbox`): sync 36h -> LLM category classification into needs_reply / waiting_for_me / decision_needed / fyi / newsletter / invoice_document / ignore -> importance 1-5, summary, suggested_action, task_candidate -> Telegram digest with a "Create tasks (N)" button. Send/delete/archive are intentionally not implemented.

### Google Calendar

`GoogleCalendarConnector.list_events(start, end)` syncs 14 days ahead into `calendar_events (source=google)`, upserts by external id, and runs every 30 minutes via automation.

`create_event(...)` is called **only** from `ConfirmationExecutor` after an explicit "yes" from the user in Telegram. Without Google, the internal calendar is fully functional.

## Yandex.Calendar (CalDAV, read-only)

Connected directly from the Mini App: **Settings -> Yandex.Calendar**.

1. Create an app password: id.yandex.ru -> Security -> App passwords -> Calendar CalDAV.
2. Enter the Yandex username and app password in the form. Lumi verifies access by listing calendars and stores credentials **encrypted with Fernet** in the `connectors` table.
3. Regular sync uses the `CALENDAR_SYNC_DAYS_BACK` / `CALENDAR_SYNC_DAYS_AHEAD` window (default: 1 day back and 90 days ahead) in shared `calendar_sync` together with Google if Google is also connected. The agent tool `read_calendar_events` also performs on-demand sync for the exact requested window before reading from `calendar_events`.

Read-only: Lumi never writes to Yandex.Calendar, even with confirmation. Implementation: `connectors/yandex/caldav_client.py` (caldav library, recurring events expanded server-side).

## News (RSS / Google News)

`RssNewsConnector.fetch_topic(query, language, max_items)`: by default it builds a Google News search RSS feed (`news.google.com/rss/search?q=...`), or uses explicit `feed_urls` from topic config. Deduplication is by sha256(url). Dead feeds are skipped with a warning; the digest is built from the remaining feeds. If the LLM is unavailable, the digest degrades to a headline list.

Topic config (JSONB `news_topics.config`):

```json
{"max_items": 10, "feed_urls": ["https://example.com/feed.xml"]}
```

## Permission matrix

| Action | Automatic | Confirmation |
|---|---|---|
| create task/reminder | yes, for clear requests (conf >= 0.85) | for low confidence |
| store memory | only explicit "remember this" / very high confidence | otherwise yes |
| internal calendar block | yes, for explicit requests | for ambiguity |
| **write to external Google Calendar** | never | **always** |
| read Yandex.Calendar | yes, if connected | - |
| write to Yandex.Calendar | never | not implemented (read-only by design) |
| read email / triage | yes, if connected | - |
| **send/delete email** | never | not implemented in the MVP |
| news digest | yes | - |
| enable automation | never | always |

## Adding Outlook after the MVP

1. `connectors/microsoft/`: auth (MSAL) + `OutlookMailConnector` with the same DTOs as `GmailConnector` (`EmailThreadDTO` / `EmailMessageDTO`).
2. `EmailService` receives the connector in its constructor; connector selection uses `connectors.type`.
3. New `connector_type` enum value + Settings UI row.

The DTO structure is provider-neutral by design, so services and LLM prompts do not need to change.
