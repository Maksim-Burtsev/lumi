import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { ConfirmationDecisionResponse, SettingsResponse, TodayResponse, User } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import TodayPage from './TodayPage';

vi.mock('../components/timeline/Timeline', () => {
  type Entry = {
    id: string;
    title: string;
    start_at: string;
    end_at: string;
    hasPersonalNote?: boolean;
    onPress?: () => void;
    action?: { label: string; onClick: () => void; busy?: boolean };
    secondaryAction?: { label: string; onClick: () => void; busy?: boolean };
  };
  const time = (value: string) => value.slice(11, 16);

  return {
    Timeline: ({ entries }: { entries: Entry[] }) => (
      <div>
        {entries.map((entry) => (
          <div key={entry.id}>
            <button type="button" onClick={entry.onPress}>
              <span>{entry.title}</span>
              {entry.hasPersonalNote && <span role="img" aria-label="Есть личная заметка" />}
            </button>
            <span>
              {time(entry.start_at)}–{time(entry.end_at)}
            </span>
            {entry.secondaryAction && (
              <button type="button" onClick={entry.secondaryAction.onClick}>
                {entry.secondaryAction.label}
              </button>
            )}
            {entry.action && (
              <button type="button" onClick={entry.action.onClick}>
                {entry.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    ),
  };
});

const firstConfirmationId = '11111111-1111-4111-8111-111111111111';
const secondConfirmationId = '22222222-2222-4222-8222-222222222222';

function makeUser(locale: 'en' | 'ru' = 'ru'): User {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'Asia/Yerevan',
    locale,
    settings: { reply_language_mode: 'auto' },
    created_at: '2026-06-12T00:00:00Z',
    last_seen_at: null,
  };
}

function makeSettingsResponse(locale: 'en' | 'ru' = 'ru'): SettingsResponse {
  return {
    user: makeUser(locale),
    llm: { provider: 'mock', model: 'mock-1', configured: true },
    google: {
      status: 'disconnected',
      gmail_available: false,
      calendar_available: false,
      scopes: [],
      last_sync_at: null,
      last_error: null,
    },
    yandex: { status: 'disconnected', username: null, last_sync_at: null, last_error: null },
    flags: { store_email_bodies: false, store_llm_debug_payloads: false, dev_auth: true },
    app: { public_url: null, env: 'local' },
  };
}

function makeTodayResponse(overrides: Partial<TodayResponse> = {}): TodayResponse {
  return {
    date: '2026-06-12',
    greeting: 'Добрый вечер',
    summary: {
      meetings_today: 0,
      tasks_active: 0,
      tasks_due_today: 0,
      tasks_overdue: 0,
      emails_need_reply: 0,
    },
    timeline: [],
    needs_attention: [
      {
        id: `confirmation-${firstConfirmationId}`,
        kind: 'confirmation',
        title: 'Создать задачу «Alpha»?',
        subtitle: 'Ждет решения',
        ref_id: firstConfirmationId,
        action_type: 'create_task',
        action_payload: { title: 'Alpha', project: 'Lumi' },
        risk_class: 'write_internal',
        approval_mode: 'auto_or_confirm',
        ui_mode: 'inline_confirm',
        primary_label: 'Создать',
        secondary_label: 'Отклонить',
      },
      {
        id: `confirmation-${secondConfirmationId}`,
        kind: 'confirmation',
        title: 'Создать задачу «Beta»?',
        subtitle: 'Ждет решения',
        ref_id: secondConfirmationId,
        action_type: 'create_task',
        action_payload: { title: 'Beta', project: 'Lumi' },
        risk_class: 'write_internal',
        approval_mode: 'auto_or_confirm',
        ui_mode: 'inline_confirm',
        primary_label: 'Создать',
        secondary_label: 'Отклонить',
      },
    ],
    suggestions: [],
    slot_suggestions: [],
    recent_runs: [],
    ...overrides,
  };
}

function makeDecisionResponse(): ConfirmationDecisionResponse {
  return {
    executed: true,
    result_text: 'Создал задачу: «Alpha».',
    confirmation: {
      id: firstConfirmationId,
      action_type: 'create_task',
      title: 'Создать задачу «Alpha»?',
      status: 'accepted',
      action_payload: { title: 'Alpha', project: 'Lumi' },
      created_at: '2026-06-12T00:00:00Z',
      expires_at: null,
      decided_at: '2026-06-12T00:00:01Z',
      risk_class: 'write_internal',
      approval_mode: 'auto_or_confirm',
      ui_mode: 'inline_confirm',
      primary_label: 'Создать',
      secondary_label: 'Отклонить',
    },
  };
}

function makeRejectResponse(): ConfirmationDecisionResponse {
  return {
    ...makeDecisionResponse(),
    executed: false,
    result_text: 'Ок, не делаю.',
    confirmation: {
      ...makeDecisionResponse().confirmation,
      status: 'rejected',
    },
  };
}

function makeTimelineEvent(overrides: Partial<TodayResponse['timeline'][number]> = {}): TodayResponse['timeline'][number] {
  return {
    id: 'event-1',
    kind: 'event',
    title: 'Product sync',
    start_at: '2026-06-12T10:00:00+04:00',
    end_at: '2026-06-12T10:45:00+04:00',
    source: 'internal',
    status: 'confirmed',
    busy: true,
    ...overrides,
  } as TodayResponse['timeline'][number];
}

function renderTodayPage(locale: 'en' | 'ru' = 'ru') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse(locale));
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
          <TodayPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );

  return queryClient;
}

describe('TodayPage timeline gaps', () => {
  it('shows free blocks for 30 minute gaps between meetings and hides shorter gaps', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [
          {
            id: 'event-1',
            kind: 'event',
            title: 'Тутория 2.0 стендап',
            start_at: '2026-06-12T13:00:00+04:00',
            end_at: '2026-06-12T13:15:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'event-2',
            kind: 'event',
            title: 'Стендап календаря',
            start_at: '2026-06-12T13:15:00+04:00',
            end_at: '2026-06-12T13:30:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'event-3',
            kind: 'event',
            title: 'Daily MT',
            start_at: '2026-06-12T14:00:00+04:00',
            end_at: '2026-06-12T14:30:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'event-4',
            kind: 'event',
            title: 'Short buffer check',
            start_at: '2026-06-12T14:45:00+04:00',
            end_at: '2026-06-12T15:00:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'event-5',
            kind: 'event',
            title: '1v1',
            start_at: '2026-06-12T15:30:00+04:00',
            end_at: '2026-06-12T16:00:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
        ],
        needs_attention: [],
      }),
    );

    renderTodayPage();

    expect(await screen.findAllByText('Свободно · 30 мин')).toHaveLength(2);
    expect(screen.getByText('13:30–14:00')).toBeInTheDocument();
    expect(screen.getByText('15:00–15:30')).toBeInTheDocument();
    expect(screen.queryByText('14:30–14:45')).not.toBeInTheDocument();
    expect(screen.getByText('Daily MT')).toBeInTheDocument();
  });

  it('shows precomputed quick wins as an inline free-slot nudge, not a duplicate suggestion list', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [
          {
            id: 'event-1',
            kind: 'event',
            title: 'Planning',
            start_at: '2026-06-12T13:00:00+04:00',
            end_at: '2026-06-12T13:30:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'event-2',
            kind: 'event',
            title: 'Demo',
            start_at: '2026-06-12T14:00:00+04:00',
            end_at: '2026-06-12T14:30:00+04:00',
            source: 'yandex',
            status: 'confirmed',
            busy: true,
          },
        ],
        needs_attention: [],
        suggestions: [
          {
            id: 'suggest-plan',
            kind: 'plan_day',
            title: "Build today's plan",
            description: 'Generic suggestion should stay hidden while quick wins are ready',
            action: { type: 'plan_day', payload: {} },
          },
        ],
        slot_suggestions: [
          {
            id: 'slot-1',
            title: '30 min free',
            description: 'Lumi already picked 2 quick wins for 20 min',
            start_at: '2026-06-12T13:30:00+04:00',
            end_at: '2026-06-12T14:00:00+04:00',
            tasks: [
              { id: 'task-mail', title: 'Проверить почту', project: 'Operations', estimated_minutes: 5, priority: 'medium' },
              { id: 'task-contract', title: 'Ответить по договору', project: 'Work', estimated_minutes: 15, priority: 'high' },
            ],
            reason: 'Both fit this window.',
            source: 'llm',
          },
        ],
      }),
    );

    renderTodayPage('en');

    await user.click(await screen.findByRole('button', { name: /30 min free · 2 quick wins ready/i }));

    expect(screen.getByRole('dialog', { name: 'Quick wins ready' })).toBeInTheDocument();
    expect(screen.getByText('Проверить почту')).toBeInTheDocument();
    expect(screen.getByText('Ответить по договору')).toBeInTheDocument();
    expect(screen.queryByText('Lumi suggests')).not.toBeInTheDocument();
  });
});

describe('TodayPage personal notes', () => {
  it('marks timeline cards that already have a personal note', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [
          makeTimelineEvent({
            private_note: 'Ask about launch risk.',
            private_note_summary: null,
            private_note_summary_status: 'not_needed',
            private_note_updated_at: '2026-06-12T06:00:00Z',
            private_note_summary_updated_at: null,
          } as Partial<TodayResponse['timeline'][number]>),
        ],
        needs_attention: [],
      }),
    );

    renderTodayPage();

    expect(await screen.findByText('Product sync')).toBeInTheDocument();
    expect(await screen.findByRole('img', { name: 'Есть личная заметка' })).toBeInTheDocument();
  });

  it('opens the event sheet from Today schedule and shows the personal-note section', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [makeTimelineEvent()],
        needs_attention: [],
      }),
    );

    renderTodayPage();

    await user.click(await screen.findByRole('button', { name: /Product sync/ }));

    expect(await screen.findByRole('dialog', { name: 'Product sync' })).toBeInTheDocument();
    expect(screen.getByText('Личная заметка')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Добавить заметку' })).toBeInTheDocument();
  });

  it('uses English personal-note copy when app language is English', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [makeTimelineEvent()],
        needs_attention: [],
      }),
    );

    renderTodayPage('en');

    await user.click(await screen.findByRole('button', { name: /Product sync/ }));

    expect(await screen.findByText('Personal note')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add note' })).toBeInTheDocument();
    expect(screen.queryByText('Личная заметка')).not.toBeInTheDocument();
  });

  it('labels long ready summaries with localized copy', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [
          makeTimelineEvent({
            private_note: 'Long private note. '.repeat(60),
            private_note_summary: 'AI summary: Short generated summary.',
            private_note_summary_status: 'ready',
            private_note_updated_at: '2026-06-12T06:00:00Z',
            private_note_summary_updated_at: '2026-06-12T06:01:00Z',
          } as Partial<TodayResponse['timeline'][number]>),
        ],
        needs_attention: [],
      }),
    );

    renderTodayPage();

    await user.click(await screen.findByRole('button', { name: /Product sync/ }));

    expect(await screen.findByText('AI-резюме')).toBeInTheDocument();
    expect(screen.getByText('Short generated summary.')).toBeInTheDocument();
    expect(screen.queryByText('AI summary: Short generated summary.')).not.toBeInTheDocument();
  });

  it('adds a personal note from the Today event sheet', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        timeline: [makeTimelineEvent()],
        needs_attention: [],
      }),
    );
    const updateSpy = vi.spyOn(api, 'updateCalendarPrivateNote').mockResolvedValue({
      event: {
        ...makeTimelineEvent(),
        description: null,
        all_day: false,
        created_by: 'user',
        location: null,
        meeting_url: null,
        external_url: null,
        links: [],
        last_synced_at: null,
        organizer: null,
        attendees: [],
        attendee_count: 0,
        user_response_status: null,
        private_note: 'Ask about launch risk.',
        private_note_summary: null,
        private_note_summary_status: 'not_needed',
        private_note_updated_at: '2026-06-12T06:00:00Z',
        private_note_summary_updated_at: null,
      },
    });

    renderTodayPage();

    await user.click(await screen.findByRole('button', { name: /Product sync/ }));
    await user.click(await screen.findByRole('button', { name: 'Добавить заметку' }));
    fireEvent.change(screen.getByPlaceholderText('Короткий личный контекст'), {
      target: { value: 'Ask about launch risk.' },
    });
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith('event-1', { note: 'Ask about launch risk.' });
    });
  });
});

describe('TodayPage locale', () => {
  it('renders the empty state in English when the app locale is English', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        greeting: 'Good evening',
        needs_attention: [],
        suggestions: [],
        timeline: [],
      }),
    );

    renderTodayPage('en');

    expect(await screen.findByText('No meetings or blocks today')).toBeInTheDocument();
    expect(screen.getByText('Build plan')).toBeInTheDocument();
    expect(screen.getByText('Nothing urgent — everything is under control')).toBeInTheDocument();
    expect(screen.queryByText('Сегодня нет встреч и блоков')).not.toBeInTheDocument();
  });
});

describe('TodayPage confirmation decisions', () => {
  it('expands and collapses confirmation details inline without opening a sheet', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());

    renderTodayPage();

    const alpha = await screen.findByRole('button', { name: /Создать задачу «Alpha»/ });
    await user.click(alpha);

    expect(screen.queryByRole('dialog', { name: 'Решение' })).not.toBeInTheDocument();
    expect(screen.getByText('Изменение останется внутри Lumi.')).toBeInTheDocument();
    expect(screen.getByText('Задача')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Создать' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отклонить' })).toBeInTheDocument();

    await user.click(alpha);

    expect(screen.queryByText('Изменение останется внутри Lumi.')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Решение' })).not.toBeInTheDocument();
  });

  it('handles an accepted confirmation inline and keeps the remaining item', async () => {
    const user = userEvent.setup();
    const todaySpy = vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());
    const acceptSpy = vi.spyOn(api, 'acceptConfirmation').mockResolvedValue(makeDecisionResponse());

    renderTodayPage();

    await screen.findByRole('button', { name: /Создать задачу «Alpha»/ });
    await user.click(screen.getByRole('button', { name: /Создать задачу «Alpha»/ }));

    expect(screen.queryByRole('dialog', { name: 'Решение' })).not.toBeInTheDocument();
    expect(screen.getByText('Задача')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Создать' }));

    await waitFor(() => {
      expect(screen.getByText('Создал задачу: «Alpha».')).toBeInTheDocument();
    });
    expect(acceptSpy).toHaveBeenCalledWith(firstConfirmationId);
    expect(screen.queryByRole('button', { name: /Создать задачу «Alpha»/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Создать задачу «Beta»/ })).toBeInTheDocument();
    expect(todaySpy).toHaveBeenCalledTimes(1);
  });

  it('handles a rejected confirmation inline and keeps the remaining item', async () => {
    const user = userEvent.setup();
    const todaySpy = vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());
    const rejectSpy = vi.spyOn(api, 'rejectConfirmation').mockResolvedValue(makeRejectResponse());

    renderTodayPage();

    await screen.findByRole('button', { name: /Создать задачу «Alpha»/ });
    await user.click(screen.getByRole('button', { name: /Создать задачу «Alpha»/ }));

    expect(screen.queryByRole('dialog', { name: 'Решение' })).not.toBeInTheDocument();
    expect(screen.getByText('Задача')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Отклонить' }));

    await waitFor(() => {
      expect(screen.getByText('Ок, не делаю.')).toBeInTheDocument();
    });
    expect(rejectSpy).toHaveBeenCalledWith(firstConfirmationId);
    expect(screen.queryByRole('button', { name: /Создать задачу «Alpha»/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Создать задачу «Beta»/ })).toBeInTheDocument();
    expect(todaySpy).toHaveBeenCalledTimes(1);
  });
});
