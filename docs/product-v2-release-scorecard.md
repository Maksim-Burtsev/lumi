# Product V2 release scorecard

Status snapshot: 2026-07-18. Steps 10–15 are integrated in
`codex/product-v2-fast-track`; this scorecard records implementation presence,
not release or owner acceptance.

## Step mapping

| Step | Implemented contract | Deterministic evidence | Release status |
|---|---|---|---|
| 10 — Calendar ↔ Sessions | Task-backed internal WorkBlock, `planned_event_id`, linked focus, 25/5 · 50/10 · 90/15 · custom break state, planned-vs-actual, external-conflict alternative without moving the external event | `test_focus_api.py`, `test_work_blocks.py`, Calendar/Focus frontend tests | Implementation present; consolidated runtime QA and User Gate D pending |
| 11 — Today planner | Real work-hour capacity, unified meetings/WorkBlocks/sessions timeline, startable Next block, planned tasks, today/tomorrow/replan modes, proposal expiry/idempotency and deterministic safety validation | `test_api.py`, `test_work_blocks.py`, `test_schedule_delivery.py`, `TodayPage.test.tsx` | Implementation present; two-workday User Gate E pending |
| 12 — command core | Narrow typed productivity commands, deterministic policy/validation/replies and sanitized RU/EN/mixed golden corpus; no real provider call in fixtures | `test_assistant_command_core.py`, `fixtures/assistant_command_golden.json`, assistant-core suites | Mock/contract implementation present; real MiniMax smoke and User Gate F pending |
| 13 — reflection extraction | Optional user-authored quick review, immutable version snapshots, idempotent async extraction, retry/supersede lifecycle and literal evidence | `test_reflection_analysis.py`, `fixtures/reflection_extraction_golden.json` | Implementation present; real-provider smoke remains part of MiniMax verification |
| 14 — weekly insights | Deterministic aggregates, bounded evidence-backed hypotheses, exact supporting sessions, Try/Dismiss without schedule or preference mutation | `test_focus_insights.py`, `fixtures/focus_weekly_insights.json`, Focus analytics frontend tests | Fixture implementation present; real-data User Gate G pending |
| 15 — hardening | One coherent task → plan/WorkBlock → linked focus → break → reflection → planned-vs-actual → insight integration contract plus tracked release documentation | `test_product_v2_integration.py` | Deterministic deliverables present; consolidated QA and seven-day dogfood pending |

## Automated gates

- [x] `make qa-required` selector captured for the complete current diff.
- [x] `ruff check backend/tests/test_product_v2_integration.py`.
- [x] `pytest --collect-only -q tests/test_product_v2_integration.py` — one
  deterministic integration test collected.
- [ ] `make lint`.
- [ ] `make frontend-check`.
- [ ] `make focus-check`.
- [ ] `make tasks-check`.
- [ ] `make planning-check`.
- [ ] `make auth-check`.
- [ ] `make analytics-check`.
- [ ] `make assistant-core`.
- [ ] `make assistant-core-task`.
- [ ] `make assistant-core-calendar`.
- [ ] `make assistant-eval-coverage`.
- [ ] `make minimax-planner-smoke` — intentionally pending until the coordinator
  confirms a working MiniMax key.
- [ ] Full backend CI-equivalent suite (`make test`), including
  `test_product_v2_integration.py`.
- [ ] Fresh Alembic upgrade, downgrade/upgrade, and schema-drift check.
- [ ] Final `git diff --check` after all fixes.

## Consolidated runtime evidence

- [ ] Desktop standalone Web and mobile responsive browser QA.
- [ ] Real Telegram Web/Mini App end-to-end Product V2 loop.
- [ ] External calendar create, move, cancel, conflict recovery, and proof that
  no external/confirmed event was silently moved.
- [ ] Cross-device realtime, auth expiry/logout, offline/provider-error,
  timezone/DST, empty-state, and large-data checks.
- [ ] Performance and latency baseline for Today, planning, command, focus, and
  insight flows.
- [ ] Security checks for auth/session/CSRF, ownership boundaries, and
  external-event non-mutation.
- [ ] DB/log/trace evidence and final Web/Telegram screenshots.

## Pending external gates

These gates require a working external provider, elapsed real usage, or explicit
owner judgment. Deterministic fixtures and prior technical QA do not mark them
complete.

- **MiniMax real smoke:** working key is not yet confirmed.
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
