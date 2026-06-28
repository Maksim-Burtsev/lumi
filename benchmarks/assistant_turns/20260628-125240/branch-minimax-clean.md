# Assistant Turn Benchmark: branch-minimax-clean

| case | locale/mode | media | total | first progress | llm calls | quality | reply |
|---|---:|---|---:|---:|---|---|---|
| `en_calendar_next_monday` | en/auto | none | 6.7s | 0.0s | agent_planner | pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `ru_calendar_followup_tuesday` | ru/auto | none | 6.1s | 0.0s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `it_calendar_next_tuesday` | en/auto | none | 8.6s | 0.0s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `ru_generic_small` | ru/auto | none | 5.6s | 0.0s | agent_planner | pass | Фокус на одной задаче нужен, чтобы снизить когнитивную нагрузку: мозг тратит энергию на переключение между задачами, и каждое переключение снижает продуктивность. Когда вы работае… |
| `ru_task_create` | ru/auto | none | 7.7s | 0.0s | agent_planner, action_reply_renderer | pass | Задача создана: «проверить latency progress», на 29.06 в 10:00. |
| `recent_media_unrelated_calendar` | en/auto | recent | 5.2s | 0.0s | agent_planner | pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `recent_media_explicit_followup` | en/auto | recent | 19.7s | 0.0s | agent_planner, media_reference, focused_vision | pass | The text highlighted in red is "S/N:LXRJ00C058135065891601". |
| `attached_image_question` | en/auto | attached_image | 8.9s | 0.0s | media_understanding, agent_planner | pass | The image shows an ACER device label with a serial number highlighted by a red rectangular border. The visible text reads "ACER LABEL" and "S/N:LXRJ00C058135065891601". |
