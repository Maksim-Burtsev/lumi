# Lumi — Security and Privacy Spec

## MVP threat model

Lumi runs locally on user's Mac but receives input from Telegram and may connect to Google APIs and MiniMax.

Main risks:

1. Unauthorized Telegram user talks to bot.
2. Mini App API opened outside Telegram or by wrong user.
3. Secrets accidentally committed.
4. LLM hallucinates or executes unsafe action.
5. Email/calendar external actions happen without confirmation.
6. Over-storing personal data.
7. Logs leak sensitive content or tokens.
8. Tunnel exposes local backend to internet.

## Required controls

### Telegram allowlist

Every bot update must check:

```text
message.chat.type == "private"
message.from_user.id in ALLOWED_TELEGRAM_USER_IDS
```

Unauthorized users:

- In normal mode: ignore or minimal “Access denied”.
- In local debug mode: log user id to help setup.

No group chats in MVP.

### Mini App auth

All `/api/*` requests must validate Telegram `initData` on backend.

Reject request if:

- missing initData;
- invalid signature;
- auth date too old if expiration check implemented;
- user id not allowlisted.

Do not trust frontend-provided user object.

### Secrets

Files never committed:

```text
.env
data/secrets/*
client_secret*.json
token*.json
*.key
```

Secrets in env:

```text
TELEGRAM_BOT_TOKEN
MINIMAX_API_KEY
GOOGLE_CLIENT_SECRET
APP_SECRET_KEY
ENCRYPTION_KEY
```

Do not print secrets.

Create helper:

```python
redact_secret(value: str) -> str
```

### Encryption

Use Fernet encryption for OAuth token JSON if stored in DB.

`ENCRYPTION_KEY` must be generated locally.

Provide script:

```text
python -m lumi.scripts.generate_encryption_key
```

### Permission model

Actions requiring confirmation:

- external Google Calendar write;
- email send;
- email delete/archive/label modification;
- enabling recurring automation if extracted from ambiguous chat;
- storing sensitive memory;
- any action with confidence below threshold.

Auto-allowed actions:

- create internal task from clear user request;
- create internal reminder from clear request;
- run read-only news digest;
- run read-only email triage if connector authorized;
- run read-only calendar sync;
- create internal proposed calendar block if user explicitly asks.

### LLM tool safety

LLM never gets direct tools for:

- shell execution;
- filesystem access;
- environment variables;
- database raw SQL;
- email destructive actions;
- external calendar writes without backend confirmation.

Backend executes only registered tools.

### Audit logs

Create audit logs for:

- task created/updated/completed;
- memory stored/archived;
- external calendar write;
- email action if implemented;
- connector connected/disconnected;
- automation created/updated/run;
- confirmation accepted/rejected.

### Data minimization

Email:

- store snippets/summaries, not full bodies by default;
- full body caching controlled by `STORE_EMAIL_BODIES=false` default;
- if fetched, use for immediate triage then discard.

LLM calls:

- don't store full raw prompts by default;
- store estimates and request kind;
- raw debug payload only with explicit local flag.

Memory:

- store only useful long-term context;
- allow review/delete in Mini App;
- include source and confidence.

News:

- store source URL, title, snippet, summary.

### Tunnel risk

When using HTTPS tunnel:

- only `/app` and `/api` are exposed;
- `/api` must require auth;
- no DB/Redis exposed;
- debug endpoints require local mode and auth;
- consider IP restrictions impossible via Telegram WebView, so rely on initData validation and allowlist.

### CORS

For local:

- allow `APP_PUBLIC_URL` origin;
- allow localhost origins for dev;
- do not use `*` with credentials.

Since Telegram Mini App requests may originate from webview, test carefully. Auth should not rely on cookies.

### Error messages

Do not expose stack traces to user/API.

API returns:

```json
{"error": "unauthorized"}
```

Logs include detailed trace but no secrets.

## Privacy UI

Memory page must allow:

- see what Lumi remembers;
- archive/delete memory;
- see source type if possible;
- toggle memory auto-save later if desired.

Settings page must show:

- connected services;
- last sync time;
- whether email bodies are stored;
- debug payload storage status.

## Local-only disclaimer in docs

Document clearly:

- MVP is local/personal.
- It is not a hardened multi-user SaaS.
- For production, add stronger auth, secrets management, backups, monitoring, rate limits, and security review.
