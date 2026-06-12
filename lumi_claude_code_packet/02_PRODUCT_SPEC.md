# Lumi — Product Spec MVP

## Название

**Lumi** — личный AI-ассистент в Telegram.

## Позиционирование

Lumi — не просто чат с моделью. Это персональный операционный слой поверх задач, календаря, почты, новостей и долгосрочного пользовательского контекста. Главная ценность: Lumi каждый день превращает хаос из сообщений, писем, задач, встреч и информационного шума в понятный план действий.

## Главный пользовательский сценарий MVP

Пользователь открывает Telegram, пишет Lumi обычным языком, например:

```text
Напомни завтра утром написать Саше по договору и сегодня после встреч найди слот на архитектуру Lumi.
```

Lumi должен:

1. Понять сообщение.
2. Создать задачу.
3. Создать напоминание.
4. Посмотреть календарь.
5. Предложить фокус-блок.
6. Сохранить важный контекст при необходимости.
7. Ответить в Telegram человеческим, коротким, полезным сообщением.
8. Отобразить изменения в Mini App.

## Core-wow фокус

Не делать 100 случайных функций. Сделать небольшой, но сильный набор:

1. **Единый личный чат в Telegram** — пользователь пишет Lumi как ассистенту.
2. **Извлечение задач из диалога** — Lumi превращает естественный язык в задачи, напоминания, фокус-блоки.
3. **Today command center в Mini App** — красивый мобильный экран: встречи, задачи, письма, предложения ассистента.
4. **Планирование дня** — Lumi смотрит задачи и календарь, предлагает слоты.
5. **Новости по темам** — scheduled digest по темам, важным пользователю.
6. **Email triage** — Lumi разгребает почту read-only, находит важное, предлагает действия.
7. **Внутренний календарь + внешний Google Calendar** — внутренний календарь для proposed/AI blocks, внешний как источник занятости и опциональная запись после подтверждения.
8. **Память и context management** — Lumi помнит предпочтения, проекты, правила, но делает это явно, прозрачно и управляемо.

## Что точно входит в MVP

### Telegram bot

- Только private 1:1 чат.
- Никаких групповых чатов.
- Ответы только allowlisted Telegram user id.
- Long polling для локального запуска.
- Команды:
  - `/start`
  - `/help`
  - `/app`
  - `/today`
  - `/tasks`
  - `/plan`
  - `/news`
  - `/email`
  - `/settings`
- Inline buttons для подтверждения действий:
  - создать задачу
  - принять план
  - создать календарный блок
  - отклонить действие
  - открыть Mini App

### AI chat

- MiniMax M3 как default real provider.
- Mock provider для тестов и локального smoke без ключа.
- Stateless LLM calls: все состояние хранится в backend БД, а не в “чате на стороне LLM”.
- Собственный context builder.
- Собственный compaction/summarization.
- Собственная память пользователя.
- Логи LLM-вызовов без хранения секретов.

### Tasks

- Создание задач из чата.
- Создание задач из email triage.
- Ручное создание задач в Mini App.
- Статусы: inbox, active, done, cancelled.
- Приоритеты: low, medium, high, urgent.
- Due date, reminder date, tags, project.
- Напоминания через scheduler.
- История изменений задачи.

### Calendar

- Internal calendar в БД.
- Google Calendar sync как внешний источник.
- Свободные окна.
- Proposed focus blocks.
- Confirm before writing external calendar.
- Daily planning run.

### Email

- Google Gmail read-only MVP.
- Сбор новых писем за период.
- Классификация:
  - needs_reply
  - waiting_for_me
  - decision_needed
  - fyi
  - newsletter
  - invoice_document
  - ignore
- Summary digest в Telegram.
- Proposed tasks from email.
- Никаких delete/send/archive без отдельного явного подтверждения. В MVP можно вообще не реализовывать destructive actions.

### News

- Scheduled digest по темам.
- Источник MVP: RSS, включая Google News RSS query URL или ручные RSS sources.
- LLM summary с группировкой по темам.
- Сохранение items и digest runs.

### Mini App

Страницы:

1. Today
2. Tasks
3. Calendar
4. Inbox
5. News
6. Automations
7. Memory
8. Settings

Тон UI: premium, calm, elegant, mobile-first. Не дешёвый dashboard.

### Automations

Пользователь может иметь scheduled tasks:

- daily_news_digest
- email_morning_triage
- daily_planning
- calendar_sync
- task_review
- custom_prompt

Для MVP обязательно реализовать создание/редактирование/включение/выключение automation в Mini App, а также ручной `Run now`.

## Что не входит в MVP

- Group chats.
- Multi-user SaaS.
- Payments.
- S3/object storage.
- Production Kubernetes.
- Complex vector search.
- Multi-workspace/team mode.
- Голосовые сообщения, speech-to-text, text-to-speech.
- Отправка email без подтверждения.
- Удаление email.
- Агент, который имеет доступ к shell/файлам Mac.

## Главный UX принцип

Lumi не должен вести себя как “универсальная LLM без памяти”. Он должен вести себя как аккуратный личный операционный ассистент:

- коротко отвечает;
- сам предлагает следующий шаг;
- явно говорит, что создал/не создал;
- не делает рискованных действий без подтверждения;
- показывает пользователю, что он понял контекст;
- не перегружает интерфейс;
- ведёт аккуратный audit trail.

## Примеры пользовательских команд

```text
Напомни завтра в 10 написать Ивану.
```

```text
Разбери почту за утро и скажи, где от меня ждут ответа.
```

```text
Сделай мне план на сегодня с учетом встреч и задач.
```

```text
Каждый будний день в 8:30 присылай новости по AI agents, Telegram Mini Apps и pricing LLM.
```

```text
У меня сегодня созвон в 15, после него поставь 90 минут на архитектуру backend.
```

```text
Запомни: рабочие задачи лучше группировать по проектам.
```

```text
Что ты про меня помнишь?
```

## Ответы Lumi должны быть такими

Хороший ответ:

```text
Готово.

Создал задачу: написать Ивану.
Напоминание: завтра в 10:00.

Еще вижу свободное окно завтра 10:30–12:00, могу поставить туда фокус-блок, если нужно.
```

Плохой ответ:

```text
Конечно! Я могу помочь вам с большим количеством задач, включая напоминания, календарь, почту...
```

## Product definition of done

MVP считается готовым, когда пользователь может:

1. Запустить проект локально через Docker Compose.
2. Указать Telegram bot token и MiniMax API key.
3. Написать своему боту в Telegram.
4. Получить AI-ответ от Lumi через MiniMax M3.
5. Создать задачу из обычного сообщения.
6. Получить напоминание по задаче.
7. Открыть Mini App из Telegram.
8. Увидеть Today, Tasks, Calendar, Automations.
9. Запустить вручную news digest.
10. Подключить или подготовить Google connector для Gmail/Calendar.
11. Запустить email triage и calendar sync при наличии Google credentials.
12. Посмотреть memory и удалить memory.
13. Посмотреть логи agent runs/tool calls.
14. Прочитать документацию по архитектуре.
