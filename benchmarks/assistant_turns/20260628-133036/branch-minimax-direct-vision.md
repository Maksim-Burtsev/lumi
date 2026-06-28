# Assistant Turn Benchmark: branch-minimax-direct-vision

| case | locale/mode | media | total | first progress | llm calls | quality | reply |
|---|---:|---|---:|---:|---|---|---|
| `en_calendar_next_monday` | en/auto | none | 4.4s | 0.0s | agent_planner | pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `ru_calendar_followup_tuesday` | ru/auto | none | 15.9s | 0.0s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `it_calendar_next_tuesday` | en/auto | none | 7.1s | 0.0s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `ru_generic_small` | ru/auto | none | 6.1s | 0.0s | agent_planner | pass | Фокус на одной задаче нужен, чтобы: 1. Снизить расходы на переключение — мозгу нужно ~20 минут, чтобы заново войти в контекст после прерывания. 2. Удержать поток — глубокая работа… |
| `ru_task_create` | ru/auto | none | 7.1s | 0.0s | agent_planner, action_reply_renderer | pass | Задача «проверить latency progress» добавлена на 29.06 в 10:00. |
| `recent_media_unrelated_calendar` | en/auto | recent | 3.9s | 0.0s | agent_planner | pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `recent_media_explicit_followup` | en/auto | recent | 21.5s | 0.0s | agent_planner, focused_vision | pass | LXRJ00C058135065891601 |
| `attached_image_question` | en/auto | attached_image | 33.2s | 0.0s | media_understanding, agent_planner | pass | The image shows an Acer product label. The serial number (S/N) is highlighted in a red rectangle: LXRJ00C058135065891601. The label also has the heading "ACER LABEL". |
