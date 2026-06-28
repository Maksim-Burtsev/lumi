# MiniMax Benchmark: main vs branch

| case | main total | branch total | delta | main first progress | branch first progress | main calls | branch calls | quality | branch reply |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| `en_calendar_next_monday` | 7.3s | 4.4s | -2.9s | 7.3s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `ru_calendar_followup_tuesday` | 8.6s | 15.9s | +7.3s | 8.6s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `it_calendar_next_tuesday` | 6.2s | 7.1s | +0.9s | 6.2s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `ru_generic_small` | 6.5s | 6.1s | -0.4s | - | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | Фокус на одной задаче нужен, чтобы: 1. Снизить расходы на переключение — мозгу нужно ~20 минут, чтобы заново войти в контекст после прерывания. 2. Удержать поток — глубокая работа… |
| `ru_task_create` | 22.0s | 7.1s | -14.9s | 18.7s | 0.0s | agent_planner, action_reply_renderer | agent_planner, action_reply_renderer | main: pass / branch: pass | Задача «проверить latency progress» добавлена на 29.06 в 10:00. |
| `recent_media_unrelated_calendar` | 8.0s | 3.9s | -4.1s | 8.0s | 0.0s | agent_planner, media_reference | agent_planner | main: fail: media_reference called / branch: pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `recent_media_explicit_followup` | 6.2s | 21.5s | +15.4s | - | 0.0s | agent_planner | agent_planner, focused_vision | main: check: no media path / branch: pass | LXRJ00C058135065891601 |
| `attached_image_question` | 23.2s | 33.2s | +10.0s | 0.0s | 0.0s | media_understanding, agent_planner | media_understanding, agent_planner | main: pass / branch: pass | The image shows an Acer product label. The serial number (S/N) is highlighted in a red rectangle: LXRJ00C058135065891601. The label also has the heading "ACER LABEL". |

Main JSONL: `benchmarks/assistant_turns/20260628-125409/main-minimax-clean.jsonl`
Branch JSONL: `benchmarks/assistant_turns/20260628-133036/branch-minimax-direct-vision.jsonl`
