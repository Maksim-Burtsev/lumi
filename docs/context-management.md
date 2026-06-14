# Контекст, память и compaction

## Почему stateless

Lumi не доверяет провайдеру LLM хранить диалог. Каждый вызов — полный, свежесобранный
контекст из БД. Что это даёт: смена провайдера без потери истории, полный контроль
бюджета, отлаживаемый промпт (`GET /api/debug/context/latest`), один источник правды.

## Что входит в контекст (ContextBuilder)

Порядок секций (`backend/src/lumi/assistant/context_builder.py`):

1. **System prompt** — идентичность Lumi и правила поведения (`prompts.py: LUMI_SYSTEM_PROMPT`)
2. **Runtime** — текущие дата/время в TZ пользователя, locale, канал
3. **Профиль** — имя, username, timezone
4. **Permissions** — что можно автоматически, что только через подтверждение
5. **Активные задачи как текущее состояние** (≤15, с просрочкой) и **календарь на сегодня**
6. **Снимок почты** (счётчик «ждут ответа») и **активные автоматизации**
7. **Релевантная память** (top-10 по скорингу)
8. **Summary диалога** (последняя версия после compaction)
9. **Только результаты действий текущего сообщения** («Создана задача …») — чтобы модель не смешивала их с активным состоянием
10. **Последние сообщения** (до 30, в остаток бюджета)
11. **Текущее сообщение**

Бюджет: `LLM_CONTEXT_MAX_CHARS=120000` (~30k токенов, оценка chars/4). Секции 1–9 идут
всегда; история «последних сообщений» ужимается под остаток.

## Извлечение сигналов

Отдельный JSON-вызов (`signal_extraction`) до финального ответа. Схема: задачи, напоминания,
memory candidates, календарные запросы, автоматизации, команды почты/новостей + confidence
и requires_confirmation на каждый элемент. Сбой extraction никогда не ломает чат — просто
не будет авто-действий (есть и пофрагментный salvage невалидного JSON).

### Пороги применения (orchestrator)

```text
Задача:        confidence ≥ 0.85 и !requires_confirmation → создать
               0.50–0.85 → pending confirmation + кнопки
Память:        явное «запомни» и ≥ 0.85 → сохранить
               preference/instruction и ≥ 0.92 + !requires_confirmation → сохранить
               иначе игнор без pending confirmation
Внутр. блок:   явная просьба и ≥ 0.75 → создать
Внешний календарь: ВСЕГДА pending confirmation
Автоматизация: ≥ 0.60 → pending confirmation (включение только руками)
Почта send/delete: не реализовано вовсе
```

## Память

**Запись** (MemoryService.store_candidate): нормализация → поиск дубликата по
keyword-overlap ≥ 0.75 → дубликат обновляется (importance/confidence), а не вставляется;
overlap 0.45–0.75 — новая запись с пометкой `potential_conflict`.

**Чтение** (retrieve_relevant) — скоринг без векторов:

```python
score = importance*3 + keyword_overlap(query, text)*5 + tag_overlap*4
      + recency_boost(last_accessed_at < 7d: +1.5) + kind_boost(instruction 3, preference 2, …)
```

Top-10 попадают в контекст; у использованных обновляется `last_accessed_at`.
Память не вынесена в пользовательскую навигацию Mini App; это внутренняя часть контекста.
Замена на pgvector — один метод.

## Compaction

Триггер после ответа: больше `COMPACT_AFTER_MESSAGES=80` несжатых сообщений (сверх
защищённых 30 последних) или суммарно > `COMPACT_AFTER_CHARS=160000`. Бот кладёт джобу
`compact_conversation` в очередь — пользователь ничего не ждёт.

Джоба: предыдущее summary + старые сообщения → промпт сжатия → структурированный текст
(Summary / Decisions / Preferences / Projects / Open loops / Things to avoid) →
новая строка `conversation_summaries` (version+1) → старым сообщениям `is_compacted=true` →
указатели на conversation. Последние 30 сообщений не сжимаются никогда.

## Пример от и до

Пользователь: «Напомни завтра в 10 написать Саше»

```text
messages       + role=user «Напомни завтра в 10 написать Саше»
agent_runs     + type=chat, trigger=telegram_message, running
llm_calls      + signal_extraction (mock: 1ms / MiniMax: ~1-2s)
tasks          + «написать Саше», reminder_at=завтра 10:00 (TZ юзера → UTC)
task_events    + created (actor=agent)
tool_calls     + create_task completed {task_id}
audit_logs     + task created
llm_calls      + final_chat
messages       + role=assistant «Готово. Создал задачу…»
agent_runs     → completed, metadata.context_snapshot = {...}
```

Завтра в 10:00 worker-cron `send_due_reminders` найдёт задачу и пришлёт
«⏰ Напоминание: написать Саше [✓ Выполнено] [⏰ Через час] [📅 Завтра]».

## Где что менять

| Что | Где |
|---|---|
| Характер/правила Lumi | `assistant/prompts.py: LUMI_SYSTEM_PROMPT` |
| Пороги авто-действий | `assistant/orchestrator.py` (константы сверху) |
| Бюджеты контекста | `.env`: LLM_CONTEXT_MAX_CHARS, RECENT_MESSAGES_LIMIT, COMPACT_* |
| Скоринг памяти | `assistant/memory_service.py: retrieve_relevant` |
| Промпт compaction | `assistant/prompts.py: COMPACTION_SYSTEM` |
| Посмотреть готовый контекст | `GET /api/debug/context/latest` (только APP_ENV=local) |
