# AGENTS.md

For non-trivial Lumi changes, read `docs/agent-qa.md` and include automated checks plus real Telegram Web/Mini App evidence before claiming done.

## Fast local startup

When asked to run Lumi locally from `main` or a feature worktree, do not rediscover
the startup flow. Use the repo commands directly.

For local browser-only Mini App checks:

1. Ensure `.env` exists. In `.worktrees/<task>`, run `cp ../../.env .env` if it is missing.
2. Run `make frontend-build && make up-detached && make migrate && make seed && make dev-auth-up`.
3. Verify `http://localhost:8001/app/`, `http://localhost:8001/health`, and `docker compose ps`.

For real Telegram Mini App checks:

1. Ensure `.env` exists. In `.worktrees/<task>`, run `cp ../../.env .env` if it is missing.
2. Run `make miniapp-local-up`.
3. Treat success as: fresh `APP_PUBLIC_URL`, `/health` OK, `/app/` OK, frontend asset 200, default Telegram menu URL matches, and chat-specific menu URL matches every `ALLOWED_TELEGRAM_USER_IDS`.
4. If Telegram shows a blank page or robot icon, first suspect a stale Mini App window or stale/dead tunnel. Close the Telegram Mini App window with `X`, reopen from the bot menu, then check `APP_PUBLIC_URL`, `curl "$APP_PUBLIC_URL/health"`, and `docker compose logs api bot --tail=200`.

For risky branch QA, read `docs/agent-qa.md` before claiming done.

## Agent Docker cleanup

When a branch task starts Docker, set a branch-specific `COMPOSE_PROJECT_NAME`
(`lumi_<task_slug>`) before `docker compose`/`make up-detached`. After the task
finishes or the PR is confirmed merged, run
`COMPOSE_PROJECT_NAME=lumi_<task_slug> make agent-clean` and report the cleanup
proof. Use `make agent-clean-full` only for disposable QA runtimes where deleting
DB/Redis volumes is acceptable.
