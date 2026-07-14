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
  "flags": {"store_llm_debug_payloads": bool, "dev_auth": bool},
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
    "tasks_overdue": int
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

AttentionItem = {"id": str, "kind": "overdue_task"|"due_task"|"confirmation",
                 "title": str, "subtitle": str|null, "ref_id": uuid|null,
                 "action_type": str|null, "action_payload": object|null,
                 "risk_class": str|null, "approval_mode": str|null, "ui_mode": str|null,
                 "primary_label": str|null, "secondary_label": str|null}

Suggestion = {"id": str, "kind": "focus_block"|"plan_day",
              "title": str, "description": str|null,
              "action": {"type": "plan_day"|"confirm_block", "payload": object}}

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

Tasks V2 uses the existing `status + target_at` columns; no schema migration is
required. Buckets are computed by the backend in the owning user's timezone:

| Bucket | Stored contract |
|---|---|
| `inbox` | `status=inbox` |
| `this_week` | `status=active` and `target_at` is before next Monday 00:00 local time |
| `later` | `status=active` and `target_at` is null or on/after that boundary |
| `done` | `status=done` |

Past `target_at` values stay in `this_week` so unfinished planned work remains
visible. `due_at` is a hard deadline and never changes the bucket. Project and
estimate are optional.

```
Task = {
  "id": uuid, "title": str, "description": str|null,
  "status": "inbox"|"active"|"done"|"cancelled",
  "priority": "low"|"medium"|"high"|"urgent",
  "project": str|null, "project_id": uuid|null, "tags": [str],
  "due_at": ts|null, "planned_for": ts|null, "target_at": ts|null,
  "reminder_at": ts|null,
  "snoozed_until": ts|null, "estimated_minutes": int|null,
  "estimate_source": str|null, "review_skips": object,
  "source": str, "created_at": ts, "completed_at": ts|null,
  "bucket": "inbox"|"this_week"|"later"|"done"|null
}

GET  /api/tasks?filter=inbox|this_week|later|done|today|upcoming|review|all&q=str&limit=100&offset=0&project_id=uuid
  → {"items": [Task], "has_more": bool, "next_offset": int|null}
POST /api/tasks  body: {"title": str, "description"?, "priority"?, "project"?, "project_id"?, "tags"?, "due_at"?, "planned_for"?, "reminder_at"?} → {"task": Task}  (201)
PATCH /api/tasks/{id}  body: any mutable subset → {"task": Task}
POST /api/tasks/{id}/complete → {"task": Task}
POST /api/tasks/{id}/snooze  body: {"preset": "1h"|"3h"|"tomorrow"|"next_week"} | {"until": ts} → {"task": Task}
```

Compatibility and transitions:

- `target_at` remains accepted and returned as a deprecated alias of
  `planned_for`; conflicting values are rejected.
- A capture without `planned_for` starts in Inbox. Setting a non-null
  `planned_for` activates it; setting `status=inbox` clears `planned_for`.
- Completing a task preserves its planning date and original open status.
  Existing `PATCH {"status":"active"}` is the undo operation: it restores
  Inbox versus Active and clears `completed_at`. Repeated completion is
  idempotent.
- Legacy `filter=review` is an alias for Inbox. Missing project, deadline, or
  estimate does not create a Review requirement.
- Existing `cancelled` rows remain compatible with explicit legacy status
  transitions and serialize with `bucket=null`.

## Projects

```
GET /api/projects → {"items": [Project]}

Project = {
  "id": uuid, "name": str, "status": "active"|"archived",
  "color": str|null, "system_key": str|null, "is_system": bool,
  "active_task_count": int, "completed_task_count": int,
  "estimated_minutes_total": int, "health_status": str,
  "health_reason": str, "next_task": Task|null, "created_at": ts|null
}
```

## Focus sessions

Focus timestamps are stored in UTC. `local_date` is calculated by the server in
the user's configured timezone and is the authoritative day key for the Mini App.
`project_snapshot` is immutable internal history; the public `project_name` is the
current owned project name, falling back to that snapshot if the project was removed.

```
FocusSession = {
  "id": uuid, "status": "active"|"completed"|"abandoned",
  "task": Task|null, "project_id": uuid|null, "project_name": str|null,
  "local_date": "YYYY-MM-DD", "intention": str, "planned_minutes": int,
  "started_at": ts, "target_end_at": ts, "ended_at": ts|null,
  "duration_seconds": int|null,
  "reflection": {
    "accomplished_text": str|null, "distraction_text": str|null,
    "next_step_text": str|null, "focus_score": 1..5|null
  }
}

GET /api/focus/state → {
  "active_session": FocusSession|null,
  "today": {"focus_seconds": int, "completed_sessions": int, "streak_days": int},
  "recent_sessions": [FocusSession]
}

GET /api/focus/summary?period=week|month|custom&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&q=&project_id=
  → {
    "period": str, "total_focus_seconds": int, "total_sessions": int,
    "streak_days": int, "average_focus_score": float|null,
    "average_daily_focus_seconds": int,
    "average_daily_focus_delta_percent": int|null,
    "total_focus_delta_percent": int|null,
    "most_focused_daypart": "morning"|"afternoon"|"evening"|"night"|null,
    "daypart_breakdown": [{"daypart": str, "focus_seconds": int}],
    "daily_activity": [{"date": "YYYY-MM-DD", "focus_seconds": int,
                         "session_count": int, "average_focus_score": float|null}],
    "project_breakdown": [{"project_id": uuid|null, "project_name": str|null,
                            "focus_seconds": int, "session_count": int}],
    "next_steps": [str]
  }

`q` and `project_id` filter the complete summary dataset, including comparison
baselines. Search covers intention, reflection fields, the immutable project
snapshot, the current owned project name, and task title. A single local day uses
`period=custom` with equal `from_date` and `to_date` values.

GET /api/focus/sessions?period=week|month|custom&from_date=&to_date=&q=&project_id=&limit=100&offset=0
  → {"items": [FocusSession], "has_more": bool, "next_offset": int|null}
GET /api/focus/sessions/{id} → {"session": FocusSession}

POST /api/focus/sessions
  body: {"task_id"?: uuid|null, "project_id"?: uuid|null,
         "project_name"?: str|null, "intention": str, "planned_minutes": 1..240}
  → {"session": FocusSession} (201)

POST /api/focus/sessions/log
  body: {"task_id"?: uuid|null, "project_id"?: uuid|null,
         "project_name"?: str|null, "intention": str, "logged_at": ts,
         "duration_minutes": 1..240, reflection fields...}
  → {"session": FocusSession} (201)

POST /api/focus/sessions/{id}/finish body: {reflection fields...}
  → {"session": FocusSession}
POST /api/focus/sessions/{id}/abandon → {"session": FocusSession}
PATCH /api/focus/sessions/{id} body: any mutable subset → {"session": FocusSession}
DELETE /api/focus/sessions/{id} → 204
```

Normal finish uses server time. Manual/edit ranges must end after start, cannot
extend more than 24 hours, and cannot end in the future beyond a small clock-skew
tolerance. Mutating an already transitioned session returns stable `409`; a second
concurrent start returns `409 active_focus_session_exists`. PATCH distinguishes an
omitted field (preserve it) from explicit `null` (clear it).

Week analytics use the rolling seven local days against the average of the four
preceding seven-day windows. Month analytics are month-to-date and compare the same
elapsed day count in the preceding four months. Custom ranges do not expose deltas.

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

## Removed product routes

`/api/inbox/*`, `/api/news/*`, and `/api/automations/*` are intentionally absent. Historical database rows remain for non-destructive audit compatibility, but they are not exposed or executed.

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
  "calendar_available": bool
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
queries for topics such as `tasks`, `focus`, `calendar`, `runs`, `memories`, and `settings`.

## Debug (local only, `APP_ENV=local`)

```
GET /api/debug/context/latest → last built LLM context snapshot (no secrets)
```
