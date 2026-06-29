# Assistant Turn Benchmark: main-minimax-clean

| case | locale/mode | media | total | first progress | llm calls | quality | reply |
|---|---:|---|---:|---:|---|---|---|
| `en_calendar_next_monday` | en/auto | none | 7.3s | 7.3s | agent_planner | pass | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `ru_calendar_followup_tuesday` | ru/auto | none | 8.6s | 8.6s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `it_calendar_next_tuesday` | en/auto | none | 6.2s | 6.2s | agent_planner | pass | 📅 Вт, 30.06 11:00 Dentist · 1ч 12:00 Свободно · 4ч 16:00 Lumi sync · 30м |
| `ru_generic_small` | ru/auto | none | 6.5s | - | agent_planner | pass | Фокус на одной задаче нужен, чтобы: • снизить переключения контекста — каждый переход между задачами съедает время и внимание; • быстрее довести дело до результата — меньше разрыв… |
| `ru_task_create` | ru/auto | none | 22.0s | 18.7s | agent_planner, action_reply_renderer | pass | Задача «проверить latency progress» добавлена на 29.06 в 10:00. |
| `recent_media_unrelated_calendar` | en/auto | recent | 8.0s | 8.0s | agent_planner, media_reference | fail: media_reference called | 📅 Mon, 29 Jun 10:00 Team standup · 30m 10:30 Free · 4h 30m 15:00 Product review · 45m |
| `recent_media_explicit_followup` | en/auto | recent | 6.2s | - | agent_planner | check: no media path | LXRJ00C058135065891601 |
| `attached_image_question` | en/auto | attached_image | 23.2s | 0.0s | media_understanding, agent_planner | pass | The image is a close-up of an Acer device label with the serial number highlighted by a red rectangular box. Visible text: • Header: ACER LABEL • Serial number (S/N): LXRJ00C05813… |
