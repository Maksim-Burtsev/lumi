# Connectors

All external integrations are isolated behind interfaces in `backend/src/lumi/connectors/`. The LLM never calls external APIs; only backend services call connectors, with logging in `tool_calls` / `audit_logs`.

## Google Calendar

### Connection: local OAuth (recommended for the MVP)

```bash
# 1. Google Cloud Console: project -> OAuth client "Desktop app"
#    Enable API: Google Calendar API
#    OAuth consent screen -> test users -> add your account
# 2. Downloaded JSON ->
cp ~/Downloads/client_secret_*.json data/secrets/google_client_secret.json
# 3. On the host, not in Docker:
make google-auth-local
```

`scripts/google_auth_local.py` starts `InstalledAppFlow`, opens a browser, and stores the token in `data/secrets/google_token.json`. The directory is mounted into containers, so the backend picks up the token immediately, refreshes it, and writes the refreshed token back.

Scopes: calendar read and event creation after confirmation:

```text
calendar.readonly · calendar.events
```

Status: Mini App -> Settings -> Google, or `GET /api/connectors/google/status`.
Disconnect: the Disconnect button removes the token file.

### Google Calendar

`GoogleCalendarConnector.list_events(start, end)` syncs the configured window into `calendar_events (source=google)`, upserts by external id, and runs through the hidden system `calendar_sync` scheduled task.

`create_event(...)` is called **only** from `ConfirmationExecutor` after an explicit "yes" from the user in Telegram. Without Google, the internal calendar is fully functional.

## Yandex.Calendar (CalDAV, read-only)

Connected directly from the Mini App: **Settings -> Yandex.Calendar**.

1. Create an app password: id.yandex.ru -> Security -> App passwords -> Calendar CalDAV.
2. Enter the Yandex username and app password in the form. Lumi verifies access by listing calendars and stores credentials **encrypted with Fernet** in the `connectors` table.
3. Regular sync uses the `CALENDAR_SYNC_DAYS_BACK` / `CALENDAR_SYNC_DAYS_AHEAD` window (default: 1 day back and 90 days ahead) in shared `calendar_sync` together with Google if Google is also connected. The agent tool `read_calendar_events` also performs on-demand sync for the exact requested window before reading from `calendar_events`.

Read-only: Lumi never writes to Yandex.Calendar, even with confirmation. Implementation: `connectors/yandex/caldav_client.py` (caldav library, recurring events expanded server-side).

## Permission matrix

| Action | Automatic | Confirmation |
|---|---|---|
| create task/reminder | yes, for clear requests (conf >= 0.85) | for low confidence |
| store memory | only explicit "remember this" / very high confidence | otherwise yes |
| internal calendar block | yes, for explicit requests | for ambiguity |
| **write to external Google Calendar** | never | **always** |
| read Yandex.Calendar | yes, if connected | - |
| write to Yandex.Calendar | never | not implemented (read-only by design) |
