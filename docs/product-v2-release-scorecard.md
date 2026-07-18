# Product V2 release scorecard

Status snapshot: 2026-07-18. Steps 10–15 are integrated and technically
validated in `codex/product-v2-fast-track`. External-provider, elapsed-time, and
owner-acceptance gates remain separate below.

## Step mapping

| Step | Implemented contract | Deterministic evidence | Release status |
|---|---|---|---|
| 10 — Calendar ↔ Sessions | Task-backed internal WorkBlock, `planned_event_id`, linked focus, 25/5 · 50/10 · 90/15 · custom break state, planned-vs-actual, external-conflict alternative without moving the external event | `test_focus_api.py`, `test_work_blocks.py`, Calendar/Focus frontend tests | Implementation and local runtime flow complete; real external-calendar portion of User Gate D pending |
| 11 — Today planner | Real work-hour capacity, unified meetings/WorkBlocks/sessions timeline, startable Next block, planned tasks, today/tomorrow/replan modes, proposal expiry/idempotency and deterministic safety validation | `test_api.py`, `test_work_blocks.py`, `test_schedule_delivery.py`, `TodayPage.test.tsx` | Implementation present; two-workday User Gate E pending |
| 12 — command core | Narrow typed productivity commands, deterministic policy/validation/replies and sanitized RU/EN/mixed golden corpus; no real provider call in fixtures | `test_assistant_command_core.py`, `fixtures/assistant_command_golden.json`, assistant-core suites | Mock/contract implementation present; real MiniMax smoke and User Gate F pending |
| 13 — reflection extraction | Optional user-authored quick review, immutable version snapshots, idempotent async extraction, retry/supersede lifecycle and literal evidence | `test_reflection_analysis.py`, `fixtures/reflection_extraction_golden.json` | Implementation present; real-provider smoke remains part of MiniMax verification |
| 14 — weekly insights | Deterministic aggregates, bounded evidence-backed hypotheses, exact supporting sessions, Try/Dismiss without schedule or preference mutation | `test_focus_insights.py`, `fixtures/focus_weekly_insights.json`, Focus analytics frontend tests | Fixture implementation present; real-data User Gate G pending |
| 15 — hardening | One coherent task → plan/WorkBlock → linked focus → break → reflection → planned-vs-actual → insight integration contract plus tracked release documentation | `test_product_v2_integration.py` | Consolidated technical QA complete; seven-day dogfood pending |

## Automated gates

- [x] `make qa-required` selector captured for the complete current diff.
- [x] `ruff check backend/tests/test_product_v2_integration.py`.
- [x] `pytest --collect-only -q tests/test_product_v2_integration.py` — one
  deterministic integration test collected.
- [x] `make lint` — Ruff clean; mypy clean across 117 source files.
- [x] `make frontend-check` — 170 tests passed, production build complete;
  six existing Fast Refresh warnings and the existing 608.51 kB chunk warning.
- [x] `make focus-check` — 26 passed.
- [x] `make tasks-check` — 46 passed.
- [x] `make planning-check` — 79 passed.
- [x] `make auth-check` — 29 passed.
- [x] `make analytics-check` — 16 passed.
- [x] `make assistant-core` — 15 passed.
- [x] `make assistant-core-task` — 6 passed, 7 skipped by area selection.
- [x] `make assistant-core-calendar` — 3 passed, 10 skipped by area selection.
- [x] `make assistant-core-memory` — 4 passed, 9 skipped by area selection.
- [x] `make assistant-eval-coverage` — 2 passed.
- [ ] `make minimax-planner-smoke` — intentionally pending until the coordinator
  confirms a working MiniMax key.
- [x] Full backend CI-equivalent suite (`make test`) — 482 passed, including
  `test_product_v2_integration.py`.
- [x] Fresh Alembic upgrade, downgrade-to-base/upgrade-to-head, and schema-drift
  check — `No new upgrade operations detected.`
- [x] Final `git diff --check`.

## Consolidated runtime evidence

- [x] Desktop standalone Web and 390×844 mobile responsive QA. No horizontal
  overflow at 1440×1000 or 390×844.
- [x] Local Product V2 loop: task → linked confirmed WorkBlock → linked focus →
  planned-vs-actual → quick reflection; separate 25/5 session → persisted break
  across navigation → skip break.
- [x] Browser regression found and fixed: Calendar `Plan day`/`Sync` clicks no
  longer pass the React event as an agent start function. The repeated live
  `Plan day` returned `plan: 0 blocks proposed` with no new console error.
- [x] Real Telegram Web delivery and fresh `Lumi` menu verified against
  `https://seen-arbitration-pan-hood.trycloudflare.com/app/`; public `/health`
  and `/app/` both returned 200, and default plus chat-specific menu URLs
  matched. Native Mini App iframe interaction is a manual skip: macOS denied
  Accessibility control and the installed Telegram Desktop requires an update.
- [x] External create/move/cancel, conflict recovery, and no-silent-move
  contracts passed in deterministic `calendar_sync`/planning tests.
- [ ] Real external-provider create/move/cancel was unavailable: the QA account
  reports the Google connector as `disconnected`.
- [x] Security evidence: unauthenticated `/api/today` returned 401; isolated
  dev-auth Today returned 200; auth/ownership suites passed.
- [x] Local latency samples: Today 0.120 s, focus state 0.017 s, calendar
  0.015 s. Public tunnel health/app checks returned 200.
- [x] DB evidence: linked WorkBlock `confirmed`; linked 60-minute session
  `completed`; 25/5 session `completed` with `break_ended=true`; both reflection
  analyses `ready` under the mock provider. Runtime logs contain no error,
  traceback, exception, or critical entry.
- [x] Final screenshots:
  [desktop Sessions](assets/product-v2-release/web-desktop-sessions.png),
  [mobile Today](assets/product-v2-release/web-mobile-today.png), and
  [Telegram Web menu](assets/product-v2-release/telegram-web-menu.png).

## Pending external gates

These gates require a working external provider, elapsed real usage, or explicit
owner judgment. Deterministic fixtures and prior technical QA do not mark them
complete.

- **MiniMax real smoke:** working key is not yet confirmed.
- **Real calendar-provider mutation:** the isolated QA account has no connected
  Google/Yandex calendar, so live provider create/move/cancel remains pending.
- **User Gate F:** at least 20 owner formulations in RU, EN, mixed, typo-heavy,
  follow-up, relative-date, correction, ambiguity, and adversarial cases; zero
  unintended writes or fake success.
- **User Gate E:** use Plan tomorrow across two real working days and judge
  capacity/replan quality.
- **User Gate G:** accumulate 20–30 real sessions across at least seven distinct
  days, then review 3–5 generated insights and their evidence.
- **User Gate A:** desktop/phone Sessions feel, reopen/overtime/alarm/reflection
  acceptance — no explicit owner confirmation recorded.
- **User Gate B:** ten-minute scope-cut/IA acceptance — no explicit owner
  confirmation recorded.
- **User Gate C:** 15–20 real-task Tasks V2 acceptance — no explicit owner
  confirmation recorded.
- **User Gate D:** real external-calendar, WorkBlock-linked session,
  planned-vs-actual, conflict recovery, and focus/break acceptance — no explicit
  owner confirmation recorded.
- **Final seven-day owner dogfood:** pending after the consolidated technical
  gates; Product V2 is not release-approved until it completes without a blocker.
