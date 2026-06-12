# Lumi — Frontend Mini App UI Spec

## Stack

Use:

- React
- TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- lucide-react icons
- optional: framer-motion for subtle transitions

Do not use Next.js for MVP. Mini App is a SPA served by FastAPI static files under `/app`.

## Telegram integration

Load Telegram WebApp script in `index.html`:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
```

Create wrapper:

```ts
export function getTelegramWebApp(): TelegramWebApp | null
export function getInitData(): string
export function setupTelegramTheme(): void
export function haptic(type: 'light' | 'medium' | 'heavy' | 'success' | 'error'): void
```

On app startup:

1. call `Telegram.WebApp.ready()`;
2. call `Telegram.WebApp.expand()`;
3. read theme params;
4. set CSS variables;
5. include `X-Telegram-Init-Data` header on API requests.

## Visual direction

Previous UI examples were too functional and cheap. New UI must feel:

```text
premium
calm
mobile-first
elegant
soft but precise
high contrast where needed
spacious
not overloaded
```

Style keywords:

- clean glassy cards but not excessive glassmorphism;
- generous spacing;
- muted neutral palette;
- one accent color from Telegram theme;
- beautiful typography;
- subtle shadows;
- rounded cards;
- timeline with calm rhythm;
- smooth states;
- no childish gradients;
- no cluttered dashboard widgets.

## Layout

Mobile-first, iPad-friendly.

```text
AppShell
  TopBar
  Content
  BottomNav
```

Bottom navigation:

1. Today
2. Tasks
3. Calendar
4. Inbox
5. More

More page links:

- News
- Automations
- Memory
- Settings
- Agent Runs

On wider screens/iPad, optional side rail can appear.

## Design tokens

Use CSS variables:

```css
:root {
  --tg-bg: var(--tg-theme-bg-color, #f7f7f8);
  --tg-text: var(--tg-theme-text-color, #111827);
  --tg-hint: var(--tg-theme-hint-color, #6b7280);
  --tg-link: var(--tg-theme-link-color, #2481cc);
  --tg-button: var(--tg-theme-button-color, #2481cc);
  --tg-button-text: var(--tg-theme-button-text-color, #ffffff);
  --surface: rgba(255, 255, 255, 0.82);
  --surface-strong: rgba(255, 255, 255, 0.96);
  --border: rgba(15, 23, 42, 0.08);
  --shadow-soft: 0 12px 40px rgba(15, 23, 42, 0.08);
  --radius-xl: 24px;
  --radius-lg: 18px;
}
```

Respect Telegram safe area:

```css
padding-bottom: calc(env(safe-area-inset-bottom) + 72px);
```

## Pages

### 1. Today Page

This is the core wow page.

Sections:

1. Hero summary
2. Plan timeline
3. Needs attention
4. Assistant suggestions
5. Quick actions
6. Recent agent runs

Visual hierarchy:

```text
Good morning / Доброе утро
Сегодня: 4 встречи · 7 задач · 3 письма ждут ответа
```

Hero card example:

```text
┌─────────────────────────────────┐
│ Доброе утро                     │
│ Сегодня у тебя 4 встречи,       │
│ 7 задач и 3 письма с ответом.   │
│                                 │
│ [Собрать план] [Разобрать почту]│
└─────────────────────────────────┘
```

Timeline card:

```text
09:30  Standup
11:30  Focus: архитектура Lumi
14:00  Client call
16:30  Email catch-up
```

Needs attention card:

```text
Требует внимания
- Иван ждет подтверждения встречи
- 2 письма требуют ответа
- Задача “архитектура backend” без слота
```

Assistant suggestion card:

```text
Lumi предлагает
Заблокировать 14:30–16:00 под deep work.
[Принять] [Изменить]
```

API:

```text
GET /api/today
POST /api/calendar/plan-day
POST /api/inbox/triage/run
POST /api/news/digest/run
```

### 2. Tasks Page

Sections:

- quick input;
- filters: Today, Upcoming, Inbox, Done;
- task cards;
- project chips;
- swipe actions optional.

Task card:

```text
○ Написать Саше по договору
  Завтра 09:00 · medium · договор
```

Actions:

- complete;
- snooze;
- edit;
- add to calendar;
- delete/cancel.

### 3. Calendar Page

Sections:

- day switcher;
- timeline;
- external busy blocks;
- internal focus blocks;
- proposed blocks;
- free slots.

Visual distinction:

```text
Google event: solid but muted
Internal Lumi block: accent border
Proposed block: dashed border
Free slot: subtle ghost button
```

Actions:

- sync calendar;
- plan day;
- confirm proposed block;
- create internal block;
- add to Google Calendar with confirmation.

### 4. Inbox Page

Sections:

- triage summary;
- categories tabs;
- thread cards;
- suggested tasks.

Category cards:

```text
Needs reply: 3
Decision needed: 2
FYI: 8
Newsletters: 21
```

Thread card:

```text
Иван Петров · Re: договор
Ждет подтверждения времени до 14:00.
[Создать задачу] [Открыть Gmail]
```

### 5. News Page

Sections:

- topics;
- latest digest;
- run digest button;
- edit topic queries.

Topic card:

```text
AI agents
Будни 08:30 · 10 источников
[Run now] [Edit]
```

Digest card:

```text
Главное за утро
AI agents — ...
Telegram Mini Apps — ...
LLM pricing — ...
```

### 6. Automations Page

Automation cards:

```text
Утренние новости
Будни 08:30
Последний запуск: сегодня 08:31
[Run now] [Pause] [Edit]
```

Fields:

- title;
- type;
- cron;
- timezone;
- config JSON/simple form;
- enabled.

For MVP, provide simple forms for known types and optional advanced JSON editor.

### 7. Memory Page

Purpose: transparency and control.

Sections:

- active memories;
- filters by kind;
- importance;
- source if available;
- archive/delete.

Memory card:

```text
Preference
Рабочие задачи лучше группировать по проектам.
Importance 4 · from chat · last used yesterday
[Archive]
```

### 8. Settings Page

Sections:

- user profile;
- timezone;
- connector status;
- MiniMax/model status;
- Telegram bot status;
- safety settings;
- debug links.

Connector status:

```text
Google Calendar: Connected
Gmail: Connected
Last sync: 09:01
[Reconnect] [Disconnect]
```

### 9. Agent Runs Page

For backend developer visibility.

List runs:

```text
09:02 email_triage completed 12.3s
08:31 news_digest completed 18.1s
08:00 calendar_sync failed
```

Run details:

- status;
- inputs summary;
- output summary;
- tool calls;
- LLM calls;
- error.

## API client

Implement typed API client:

```ts
class LumiApiClient {
  getMe()
  getToday()
  listTasks(params)
  createTask(input)
  completeTask(id)
  listCalendarEvents(range)
  planDay(date)
  runEmailTriage()
  listNewsTopics()
  runNewsDigest()
  listAutomations()
  runAutomation(id)
  listMemories()
  archiveMemory(id)
  listAgentRuns()
}
```

Each request must include `X-Telegram-Init-Data`.

Handle 401:

- show “Открой Lumi внутри Telegram”;
- show debug details in local mode.

## Empty states

Empty states must look premium, not like errors.

Examples:

Tasks empty:

```text
Пока нет активных задач.
Напиши Lumi в чате: “Напомни завтра...”
```

Calendar disconnected:

```text
Google Calendar не подключен.
Lumi уже может вести внутренний календарь, а после подключения будет учитывать рабочие встречи.
[Подключить Google]
```

Inbox disconnected:

```text
Gmail не подключен.
После подключения Lumi сможет каждое утро показывать, где от тебя ждут ответа.
```

## Loading states

Use skeleton cards, not spinners everywhere.

## Error states

Use small inline error cards with retry.

```text
Не удалось загрузить календарь.
[Повторить]
```

## Responsive behavior

Phone:

- bottom nav;
- single column;
- large touch targets.

Tablet/iPad:

- max-width content 860px;
- optional side nav;
- cards can form 2-column grid;
- timeline remains readable.

## Accessibility

- Buttons have labels.
- Contrast must be sufficient.
- Do not rely only on color.
- Support reduced motion.

## Build/deploy

Frontend build:

```text
cd frontend && npm install && npm run build
```

FastAPI should serve `frontend/dist` at `/app`.

For local development, Vite dev server can proxy `/api` to backend.

## Quality bar

Do not leave raw unstyled HTML.
Do not build generic admin dashboard.
Do not use cheap-looking gradients or random colors.
Do not create dozens of tiny widgets.
Prioritize Today page polish.
