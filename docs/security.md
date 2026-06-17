# Security and Privacy

The MVP is a local personal product, but it accepts Telegram input and calls Google/MiniMax, so the controls are real, not decorative.

## Threat model -> controls

| Risk | Control |
|---|---|
| Someone else messages the bot | `ALLOWED_TELEGRAM_USER_IDS` allowlist + private chat only; outsiders are ignored and their id is logged for setup. |
| Mini App API is called outside Telegram | HMAC validation of `initData` with the bot token (`security/telegram_auth.py`), `auth_date` check (24h), then allowlist. `initDataUnsafe` is not trusted. |
| Secrets in git | `.gitignore`: `.env*`, `data/`, `client_secret*.json`, `token*.json`, `*.key`; repo contains only `.env.example`. |
| Secrets in logs | JSON logger masks token/key/secret/password/credential values; `redact_secret()` for display. |
| LLM performs dangerous actions | The model has NO tools: the backend executes actions after extraction; shell/files/SQL are unavailable by design. |
| External writes without consent | Google Calendar writes and enabling automations go only through `pending_confirmations` + explicit tap; email send/delete is not implemented. |
| Conversation leakage in DB | Email bodies are not stored (`STORE_EMAIL_BODIES=false`), raw LLM prompts are not stored (`STORE_LLM_DEBUG_PAYLOADS=false`), and `llm_calls` stores only metrics. |
| Public tunnel exposure | Only `/app` (static) and `/api` (initData-auth) are exposed; Postgres/Redis bind to 127.0.0.1; `/docs` and debug are only for `APP_ENV=local`; dev-auth is disabled by default. |
| OAuth tokens | Stored locally in `data/secrets/` outside git; Fernet is ready for DB storage (`security/crypto.py`, `ENCRYPTION_KEY`). |
| Stack traces to user | API returns `{"error": "internal_error"}`; details stay in logs. |

## Key generation

```bash
docker compose run --rm api python -m lumi.scripts.generate_secret_key      # APP_SECRET_KEY
docker compose run --rm api python -m lumi.scripts.generate_encryption_key  # ENCRYPTION_KEY (Fernet)
```

## User transparency

- **Memory**: internal context memory; the user does not manage it manually.
- **Agent Runs**: every agent run, tool call, and LLM call with timings.
- **audit_logs**: tasks, memory, calendar, connectors, confirmations.
- **Settings**: connection statuses and active privacy flags.

## Disclaimer

This is a local single-user MVP, not a hardened SaaS product. Before production for external users: full secrets manager, backups, monitoring, rate limiting, and penetration testing. See the Production section in the runbook.
