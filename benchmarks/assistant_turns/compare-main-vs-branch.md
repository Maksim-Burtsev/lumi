# MiniMax Benchmark: main vs branch

| case | main total | branch total | delta | main first progress | branch first progress | main calls | branch calls | quality | branch reply |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| `en_calendar_next_monday` | 7.3s | 6.7s | -0.6s | 7.3s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `ru_calendar_followup_tuesday` | 8.6s | 6.1s | -2.5s | 8.6s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `it_calendar_next_tuesday` | 6.2s | 8.6s | +2.4s | 6.2s | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `ru_generic_small` | 6.5s | 5.6s | -0.9s | - | 0.0s | agent_planner | agent_planner | main: pass / branch: pass | Фокус на одной задаче нужен, чтобы снизить когнитивную нагрузку: мозг тратит энергию на переключение между задачами, и каждое переключение снижает продуктивность. Когда вы работае… |
| `ru_task_create` | 22.0s | 7.7s | -14.3s | 18.7s | 0.0s | agent_planner, action_reply_renderer | agent_planner, action_reply_renderer | main: pass / branch: pass | Задача создана: «проверить latency progress», на 29.06 в 10:00. |
| `recent_media_unrelated_calendar` | 8.0s | 5.2s | -2.8s | 8.0s | 0.0s | agent_planner, media_reference | agent_planner | main: fail: media_reference called / branch: pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `recent_media_explicit_followup` | 6.2s | 19.7s | +13.5s | - | 0.0s | agent_planner | agent_planner, media_reference, focused_vision | main: check: no media path / branch: pass | The text highlighted in red is "S/N:LXRJ00C058135065891601". |
| `attached_image_question` | 23.2s | 8.9s | -14.2s | 0.0s | 0.0s | media_understanding, agent_planner | media_understanding, agent_planner | main: pass / branch: pass | The image shows an ACER device label with a serial number highlighted by a red rectangular border. The visible text reads "ACER LABEL" and "S/N:LXRJ00C058135065891601". |

Main JSONL: `benchmarks/assistant_turns/20260628-125409/main-minimax-clean.jsonl`
Branch JSONL: `benchmarks/assistant_turns/20260628-125240/branch-minimax-clean.jsonl`
