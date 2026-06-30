# Lumi API Contract (v1)

Source of truth for both backend (FastAPI) and frontend (Mini App).
All `/api/*` endpoints require header `X-Telegram-Init-Data` (Telegram WebApp initData).
In local dev, when `DEV_AUTH_ENABLED=true`, requests without initData authenticate as `DEV_AUTH_TELEGRAM_USER_ID`.

Errors: non-2xx responses return `{"error": "<machine_code>", "detail": "<human text, optional>"}`.
401 → `{"error": "unauthorized"}`. All timestamps are ISO-8601 with timezone offset.

## Health

```
GET /health → 200 {"status": "ok", "app": "Lumi", "env": "local", "version": "0.1.0"}
```

## Me / Settings

```
GET /api/me → {"user": User}

User = {
  "id": uuid, "telegram_user_id": int, "username": str|null,
  "first_name": str|null, "last_name": str|null,
  "timezone": str, "locale": "en", "settings": object,
  "created_at": ts, "last_seen_at": ts|null
}

GET /api/settings → {
  "user": User,
  "llm": {"provider": "minimax"|"mock", "model": str, "configured": bool},
  "google": GoogleStatus,
  "yandex": YandexStatus,
  "flags": {"store_email_bodies": bool, "store_llm_debug_payloads": bool, "dev_auth": bool},
  "app": {"public_url": str|null, "env": str}
}

PATCH /api/settings  body: {
  "timezone"?: str,
  "time_format"?: "auto"|"12h"|"24h",
  "theme_mode"?: "telegram"|"light"|"dark",
  "settings"?: object
} → {"user": User}

Mini App UI language is English-only. Assistant replies automatically match the latest user message language.
```

## Today

```
GET /api/today → {
  "date": "YYYY-MM-DD",
  "greeting": str,                      // localized greeting, e.g. Good morning / Good afternoon / ...
  "summary": {
    "meetings_today": int, "tasks_active": int, "tasks_due_today": int,
    "tasks_overdue": int, "emails_need_reply": int
  },
  "timeline": [TimelineItem],           // today's events + focus blocks, sorted by start
  "needs_attention": [AttentionItem],
  "suggestions": [Suggestion],
  "slot_suggestions": [SlotSuggestion], // precomputed micro-slot task options
  "recent_runs": [AgentRunBrief]        // last 5
}

TimelineItem = {
  "id": uuid, "kind": "event"|"focus"|"proposed", "title": str,
  "start_at": ts, "end_at": ts, "source": "internal"|"google"|"yandex",
  "status": "confirmed"|"tentative"|"proposed"|"cancelled", "busy": bool
}

AttentionItem = {"id": str, "kind": "overdue_task"|"due_task"|"email"|"confirmation",
                 "title": str, "subtitle": str|null, "ref_id": uuid|null,
                 "action_type": str|null, "action_payload": object|null,
                 "risk_class": str|null, "approval_mode": str|null, "ui_mode": str|null,
                 "primary_label": str|null, "secondary_label": str|null}

Suggestion = {"id": str, "kind": "focus_block"|"plan_day"|"email_triage"|"news_digest",
              "title": str, "description": str|null,
              "action": {"type": "plan_day"|"run_triage"|"run_digest"|"confirm_block", "payload": object}}

SlotSuggestion = {"id": uuid, "title": str, "description": str|null,
                  "start_at": ts, "end_at": ts,
                  "tasks": [{"id": uuid, "title": str, "project": str|null,
                             "estimated_minutes": int|null, "priority": str|null}],
                  "reason": str|null, "source": str|null}

AgentRunBrief = {"id": uuid, "type": str, "status": str, "created_at": ts,
                 "finished_at": ts|null, "duration_ms": int|null, "result_summary": str|null}
```

## Chat history (read-only)

```
GET /api/messages?limit=50 → {"items": [{"id": uuid, "role": "user"|"assistant", "content": str, "created_at": ts}]}
```

## Confirmations

```
POST /api/confirmations/{id}/accept → {
  "confirmation": PendingConfirmation, "result_text": str, "executed": bool
}
POST /api/confirmations/{id}/reject → {
  "confirmation": PendingConfirmation, "result_text": str, "executed": false
}

PendingConfirmation = {"id": uuid, "action_type": str, "title": str,
  "status": "pending"|"accepted"|"rejected"|"expired",
  "action_payload": object, "risk_class": str, "approval_mode": str,
  "ui_mode": str, "primary_label": str, "secondary_label": str,
  "created_at": ts|null, "expires_at": ts|null, "decided_at": ts|null}
```

## Tasks

```
Task = {
  "id": uuid, "title": str, "description": str|null,
  "status": "inbox"|"active"|"done"|"cancelled",
  "priority": "low"|"medium"|"high"|"urgent",
  "project": str|null, "tags": [str],
  "due_at": ts|null, "reminder_at": ts|null, "snoozed_until": ts|null,
  "source": str, "created_at": ts, "completed_at": ts|null
}

GET  /api/tasks?filter=today|upcoming|inbox|done|all&limit=100 → {"items": [Task]}
POST /api/tasks  body: {"title": str, "description"?, "priority"?, "project"?, "tags"?, "due_at"?, "reminder_at"?} → {"task": Task}  (201)
PATCH /api/tasks/{id}  body: any mutable subset → {"task": Task}
POST /api/tasks/{id}/complete → {"task": Task}
POST /api/tasks/{id}/snooze  body: {"preset": "1h"|"3h"|"tomorrow"|"next_week"} | {"until": ts} → {"task": Task}
```

## Calendar

```
CalendarEvent = {
  "id": uuid, "title": str, "description": str|null,
  "start_at": ts, "end_at": ts, "all_day": bool, "busy": bool,
  "status": "confirmed"|"tentative"|"cancelled"|"proposed",
  "source": "internal"|"google"|"yandex", "created_by": str
}

GET  /api/calendar/events?start=ts&end=ts → {"items": [CalendarEvent]}
POST /api/calendar/events  body: {"title": str, "start_at": ts, "end_at": ts, "description"?} → {"event": CalendarEvent}  (201, internal block)
POST /api/calendar/plan-day  body: {"date"?: "YYYY-MM-DD"} → {"run_id": uuid, "status": "queued"}
POST /api/calendar/blocks/{id}/confirm → {"event": CalendarEvent}        // proposed -> confirmed (internal)
POST /api/calendar/sync → {"run_id": uuid, "status": "queued"}           // requires Google; 409 {"error":"calendar_not_connected"} when no external calendar is configured
GET  /api/calendar/free-slots?date=YYYY-MM-DD&duration=60 → {"items": [{"start_at": ts, "end_at": ts}]}
```

## Inbox (email)

```
GET /api/inbox/summary → {
  "connected": bool,
  "last_triage_at": ts|null,
  "counts": {"needs_reply": int, "waiting_for_me": int, "decision_needed": int,
             "fyi": int, "newsletter": int, "invoice_document": int, "ignore": int, "unknown": int},
  "threads": [EmailThread]              // most recent 50
}

EmailThread = {
  "id": uuid, "subject": str|null, "sender": str|null, "snippet": str|null,
  "category": str, "importance": int, "summary": str|null,
  "suggested_action": str|null, "last_message_at": ts|null,
  "task_candidate": {"title": str, "due_at": ts|null, "priority": str}|null
}

POST /api/inbox/triage/run → {"run_id": uuid, "status": "queued"}   // 409 {"error":"google_not_connected"} if no connector
POST /api/inbox/threads/{id}/create-task → {"task": Task}
```

## News

```
NewsTopic = {"id": uuid, "title": str, "query": str, "language": str, "enabled": bool, "created_at": ts}

GET   /api/news/topics → {"items": [NewsTopic]}
POST  /api/news/topics  body: {"title": str, "query": str, "language"?} → {"topic": NewsTopic} (201)
PATCH /api/news/topics/{id}  body: subset → {"topic": NewsTopic}
GET   /api/news/digests?limit=5 → {"items": [{"id": uuid, "title": str, "digest_text": str, "created_at": ts}]}
POST  /api/news/digest/run → {"run_id": uuid, "status": "queued"}
```

## Automations

```
Automation = {
  "id": uuid, "type": "news_digest"|"email_triage"|"daily_planning"|"calendar_sync"|"task_review"|"custom_prompt",
  "title": str, "cron_expression": str, "timezone": str, "enabled": bool,
  "config": object, "last_run_at": ts|null, "next_run_at": ts|null,
  "failure_count": int, "last_error": str|null
}

GET   /api/automations → {"items": [Automation]}
POST  /api/automations  body: {"type", "title", "cron_expression", "timezone"?, "config"?, "enabled"?} → {"automation": Automation} (201)
PATCH /api/automations/{id}  body: subset → {"automation": Automation}
POST  /api/automations/{id}/run → {"run_id": uuid, "status": "queued"}
```

## Memory

Memory endpoints are internal/admin surface for now; the Mini App does not expose memory management in user navigation.

```
Memory = {
  "id": uuid, "kind": "preference"|"fact"|"project"|"instruction"|"contact"|"workflow"|"other",
  "status": "active"|"archived", "text": str, "tags": [str],
  "importance": int, "confidence": float, "source": "chat"|"email"|"agent"|"manual"|null,
  "created_at": ts, "last_accessed_at": ts|null
}

GET    /api/memories?kind=&status=active → {"items": [Memory]}
PATCH  /api/memories/{id}  body: {"status"?: "archived"|"active", "text"?, "importance"?} → {"memory": Memory}
DELETE /api/memories/{id} → {"ok": true}
```

## Agent runs

```
GET /api/agent-runs?limit=30&type= → {"items": [AgentRunBrief & {"trigger": str, "input_summary": str|null, "error_message": str|null}]}
GET /api/agent-runs/{id} → {
  "run": {...full agent run...},
  "tool_calls": [{"id", "tool_name", "status", "args_json", "result_json", "error_message", "created_at"}],
  "llm_calls": [{"id", "provider", "model", "request_kind", "status", "latency_ms",
                 "input_char_count", "output_char_count", "created_at"}]
}
```

## Connectors

```
GoogleStatus = {
  "status": "disconnected"|"connected"|"error"|"needs_reauth",
  "scopes": [str], "last_sync_at": ts|null, "last_error": str|null,
  "gmail_available": bool, "calendar_available": bool
}

GET  /api/connectors/google/status → GoogleStatus
POST /api/connectors/google/disconnect → {"ok": true}

YandexStatus = {"status": "disconnected"|"connected"|"error"|"needs_reauth",
                "username": str|null, "last_sync_at": ts|null, "last_error": str|null}

GET  /api/connectors/yandex/status → YandexStatus
POST /api/connectors/yandex/connect  body: {"username": str, "app_password": str} → YandexStatus  (422 yandex_auth_failed)
POST /api/connectors/yandex/disconnect → {"ok": true}
```

## Run lifecycle for the frontend

`POST .../run` endpoints enqueue a background job and return `{"run_id","status":"queued"}` immediately.
Frontend polls `GET /api/agent-runs/{run_id}` every 1.5s (up to 120s) until status is
`completed`/`failed`, then refetches the relevant data and shows `result_summary` or error.

## Real-time UI invalidation

```
GET /api/realtime?after=<last_event_id> → text/event-stream
```

Auth is the same as other Mini App endpoints: `X-Telegram-Init-Data`. The frontend uses
`fetch` streaming instead of native `EventSource` because `EventSource` cannot set that header.

SSE events:

```
id: 123
event: ui_event
data: {"id":123,"topics":["tasks"],"event_type":"task.updated","payload":{"task_id":"..."}}

event: resync
data: {"topics":["*"],"event_type":"resync","payload":{"reason":"client_queue_overflow"}}
```

Events are invalidation hints, not source-of-truth payloads. The Mini App refetches existing REST
queries for topics such as `tasks`, `calendar`, `runs`, `inbox`, `news`, `automations`, `memories`,
and `settings`.

## Debug (local only, `APP_ENV=local`)

```
GET /api/debug/context/latest → last built LLM context snapshot (no secrets)
```
