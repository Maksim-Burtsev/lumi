import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type {
  AgentRunDetailResponse,
  ConfirmationDecisionResponse,
  FocusSessionResponse,
  SettingsResponse,
  Task,
  TodayResponse,
  User,
} from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import TodayPage from './TodayPage';

vi.mock('../components/timeline/Timeline', () => {
  type Entry = {
    id: string;
    title: string;
    start_at: string;
    end_at: string;
    subtitle?: string;
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
              {entry.hasPersonalNote && <span role="img" aria-label="Has personal note" />}
            </button>
            <span>
              {time(entry.start_at)}–{time(entry.end_at)}
            </span>
            {entry.subtitle && <span>{entry.subtitle}</span>}
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
    greeting: 'Good evening',
    summary: {
      meetings_today: 0,
      tasks_active: 0,
      tasks_due_today: 0,
      tasks_overdue: 0,
      emails_need_reply: 0,
    },
    capacity: {
      work_minutes: 480,
      meeting_minutes: 0,
      planned_minutes: 0,
      focus_minutes: 0,
      free_minutes: 480,
      utilization_percent: 0,
      over_capacity: false,
    },
    next_block: null,
    planned_tasks: [],
    planning: {
      tomorrow_date: '2026-06-13',
      can_replan: true,
      proposal_expires_at: null,
    },
    timeline: [],
    needs_attention: [
      {
        id: `confirmation-${firstConfirmationId}`,
        kind: 'confirmation',
        title: 'Create task "Alpha"?',
        subtitle: 'Pending decision',
        ref_id: firstConfirmationId,
        action_type: 'create_task',
        action_payload: { title: 'Alpha', project: 'Lumi' },
        risk_class: 'write_internal',
        approval_mode: 'auto_or_confirm',
        ui_mode: 'inline_confirm',
        primary_label: 'Create',
        secondary_label: 'Decline',
      },
      {
        id: `confirmation-${secondConfirmationId}`,
        kind: 'confirmation',
        title: 'Create task "Beta"?',
        subtitle: 'Pending decision',
        ref_id: secondConfirmationId,
        action_type: 'create_task',
        action_payload: { title: 'Beta', project: 'Lumi' },
        risk_class: 'write_internal',
        approval_mode: 'auto_or_confirm',
        ui_mode: 'inline_confirm',
        primary_label: 'Create',
        secondary_label: 'Decline',
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
    result_text: 'Task created: Alpha.',
    confirmation: {
      id: firstConfirmationId,
      action_type: 'create_task',
      title: 'Create task "Alpha"?',
      status: 'accepted',
      action_payload: { title: 'Alpha', project: 'Lumi' },
      created_at: '2026-06-12T00:00:00Z',
      expires_at: null,
      decided_at: '2026-06-12T00:00:01Z',
      risk_class: 'write_internal',
      approval_mode: 'auto_or_confirm',
      ui_mode: 'inline_confirm',
      primary_label: 'Create',
      secondary_label: 'Decline',
    },
  };
}

function makeRejectResponse(): ConfirmationDecisionResponse {
  return {
    ...makeDecisionResponse(),
    executed: false,
    result_text: "Ok, I won't do it.",
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

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Write launch brief',
    description: null,
    status: 'active',
    priority: 'high',
    project: 'Lumi',
    project_id: null,
    tags: [],
    due_at: '2026-06-12T18:00:00+04:00',
    planned_for: '2026-06-12T11:00:00+04:00',
    target_at: '2026-06-12T11:00:00+04:00',
    reminder_at: null,
    snoozed_until: null,
    estimated_minutes: 45,
    estimate_source: 'user',
    review_skips: {},
    source: 'user',
    created_at: '2026-06-11T10:00:00Z',
    completed_at: null,
    bucket: 'this_week',
    ...overrides,
  };
}

function makeActiveFocusSession(): FocusSessionResponse {
  return {
    session: {
      id: 'focus-1',
      status: 'active',
      planned_event_id: 'block-1',
      task: null,
      project_id: null,
      project_name: null,
      local_date: '2026-06-12',
      intention: 'Deep work',
      planned_minutes: 50,
      started_at: '2026-06-12T10:00:00+04:00',
      target_end_at: '2026-06-12T10:50:00+04:00',
      ended_at: null,
      duration_seconds: null,
      actual_minutes: null,
      planned_vs_actual_minutes: null,
      cycle: {
        preset: '50/10',
        focus_minutes: 50,
        break_minutes: 10,
        phase: 'focus',
        break_started_at: null,
        break_target_end_at: null,
        break_ended_at: null,
      },
      reflection: {
        outcome: null,
        raw_text: null,
        accomplished_text: null,
        distraction_text: null,
        next_step_text: null,
        focus_score: null,
        input_hash: null,
        analysis: null,
      },
    },
  };
}

function makeCompletedRun(id: string): AgentRunDetailResponse {
  return {
    run: {
      id,
      type: 'plan_day',
      status: 'completed',
      created_at: '2026-06-12T08:00:00Z',
      finished_at: '2026-06-12T08:00:01Z',
      duration_ms: 1000,
      result_summary: 'Plan ready',
      error_message: null,
    },
    tool_calls: [],
    llm_calls: [],
  };
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

describe('TodayPage workday', () => {
  it('shows real capacity, a unified timeline, and tasks planned for today', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        capacity: {
          work_minutes: 480,
          meeting_minutes: 120,
          planned_minutes: 180,
          focus_minutes: 50,
          free_minutes: 180,
          utilization_percent: 62.5,
          over_capacity: false,
        },
        timeline: [
          {
            id: 'meeting-1',
            kind: 'meeting',
            title: 'Product review',
            start_at: '2026-06-12T13:00:00+04:00',
            end_at: '2026-06-12T14:00:00+04:00',
            source: 'google',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'block-1',
            kind: 'work_block',
            title: 'Launch brief',
            start_at: '2026-06-12T14:00:00+04:00',
            end_at: '2026-06-12T14:50:00+04:00',
            source: 'internal',
            status: 'confirmed',
            busy: true,
          },
          {
            id: 'session-1',
            kind: 'focus_session',
            title: 'Architecture notes',
            start_at: '2026-06-12T09:00:00+04:00',
            end_at: '2026-06-12T09:50:00+04:00',
            source: 'internal',
            status: 'confirmed',
            busy: false,
          },
          {
            id: 'proposal-1',
            kind: 'proposed',
            title: 'Alternative focus interval',
            start_at: '2026-06-12T16:00:00+04:00',
            end_at: '2026-06-12T16:50:00+04:00',
            source: 'internal',
            status: 'proposed',
            busy: true,
            expires_at: '2026-06-12T15:30:00+04:00',
          },
        ],
        planned_tasks: [makeTask()],
        needs_attention: [],
      }),
    );

    renderTodayPage('en');

    expect(await screen.findByText('3 h free')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Capacity' })).toHaveAttribute('aria-valuenow', '63');
    expect(screen.getByText('Product review')).toBeInTheDocument();
    expect(screen.getByText('Launch brief')).toBeInTheDocument();
    expect(screen.getByText('Architecture notes')).toBeInTheDocument();
    expect(screen.getByText(/Lumi proposal · valid until/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Write launch brief/ })).toBeInTheDocument();
  });

  it('starts the next confirmed WorkBlock with its linked event and cycle', async () => {
    const block = makeTimelineEvent({
      id: 'block-1',
      kind: 'work_block',
      title: 'Deep work',
      start_at: '2026-06-12T10:00:00+04:00',
      end_at: '2026-06-12T10:50:00+04:00',
    });
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({ next_block: block, timeline: [block], needs_attention: [] }),
    );
    const startSpy = vi.spyOn(api, 'startFocusSession').mockResolvedValue(makeActiveFocusSession());

    renderTodayPage('en');

    await screen.findByRole('button', { name: 'Start' });
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));

    await waitFor(() => {
      expect(startSpy).toHaveBeenCalledWith({
        planned_event_id: 'block-1',
        intention: 'Deep work',
        planned_minutes: 50,
        break_minutes: 10,
      });
    });
  });

  it('plans tomorrow through the deterministic plan-day mode', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse({ needs_attention: [] }));
    const planSpy = vi.spyOn(api, 'planDay').mockResolvedValue({ run_id: 'run-tomorrow', status: 'queued' });
    vi.spyOn(api, 'getAgentRun').mockResolvedValue(makeCompletedRun('run-tomorrow'));

    renderTodayPage('en');

    await screen.findByRole('button', { name: 'Plan tomorrow' });
    fireEvent.click(screen.getByRole('button', { name: 'Plan tomorrow' }));

    await waitFor(() => expect(planSpy).toHaveBeenCalledWith({ mode: 'tomorrow' }));
  });

  it('soft-replans only the remaining day through replan mode', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse({ needs_attention: [] }));
    const planSpy = vi.spyOn(api, 'planDay').mockResolvedValue({ run_id: 'run-replan', status: 'queued' });
    vi.spyOn(api, 'getAgentRun').mockResolvedValue(makeCompletedRun('run-replan'));

    renderTodayPage('en');

    await screen.findByRole('button', { name: 'Replan remaining' });
    fireEvent.click(screen.getByRole('button', { name: 'Replan remaining' }));

    await waitFor(() => expect(planSpy).toHaveBeenCalledWith({ mode: 'replan' }));
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
    expect(await screen.findByRole('img', { name: 'Has personal note' })).toBeInTheDocument();
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
    expect(screen.getByText('Personal note')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add note' })).toBeInTheDocument();
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

    expect(await screen.findByText('AI summary')).toBeInTheDocument();
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
    await user.click(await screen.findByRole('button', { name: 'Add note' }));
    fireEvent.change(screen.getByPlaceholderText('Context just for yourself'), {
      target: { value: 'Ask about launch risk.' },
    });
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith('event-1', { note: 'Ask about launch risk.' });
    });
  });
});

describe('TodayPage query states', () => {
  it('exposes an accessible loading state', () => {
    vi.spyOn(api, 'getToday').mockReturnValue(new Promise<TodayResponse>(() => undefined));

    renderTodayPage('en');

    expect(screen.getByRole('status', { name: 'Loading workday' })).toBeInTheDocument();
  });

  it('shows a localized error with retry', async () => {
    vi.spyOn(api, 'getToday').mockRejectedValue(new Error('offline'));

    renderTodayPage('en');

    expect(await screen.findByText('Could not load the day plan.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: 'Plan tomorrow' })).toBeInTheDocument();
    expect(screen.getByText('No upcoming WorkBlock')).toBeInTheDocument();
    expect(screen.getByText('No tasks planned for today')).toBeInTheDocument();
    expect(screen.getByText('Nothing urgent — everything is under control')).toBeInTheDocument();
    expect(screen.queryByText('Сегодня нет встреч и блоков')).not.toBeInTheDocument();
  });
});

describe('TodayPage product scope', () => {
  it('filters legacy email and news payloads before calculating the all-clear state', async () => {
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        summary: {
          meetings_today: 0,
          tasks_active: 0,
          tasks_due_today: 0,
          tasks_overdue: 0,
          emails_need_reply: 3,
        },
        needs_attention: [
          {
            id: 'email-thread-1',
            kind: 'email',
            title: 'Reply to launch email',
            subtitle: 'Waiting for you',
            ref_id: 'thread-1',
          },
        ],
        suggestions: [
          {
            id: 'email-triage',
            kind: 'email_triage',
            title: 'Triage the inbox',
            description: null,
            action: { type: 'run_triage', payload: {} },
          },
          {
            id: 'news-digest',
            kind: 'news_digest',
            title: 'Build a news digest',
            description: null,
            action: { type: 'run_digest', payload: {} },
          },
        ],
      }),
    );

    renderTodayPage('en');

    expect(await screen.findByText('Quiet day — focus on important work')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Triage inbox' })).not.toBeInTheDocument();
    expect(screen.queryByText('Reply to launch email')).not.toBeInTheDocument();
    expect(screen.queryByText('Triage the inbox')).not.toBeInTheDocument();
    expect(screen.queryByText('Build a news digest')).not.toBeInTheDocument();
    expect(screen.getByText('Nothing urgent — everything is under control')).toBeInTheDocument();
  });

  it('keeps confirmations and dedicated planning actions visible without generic plan cards', async () => {
    const confirmation = makeTodayResponse().needs_attention[0];
    vi.spyOn(api, 'getToday').mockResolvedValue(
      makeTodayResponse({
        needs_attention: [confirmation],
        suggestions: [
          {
            id: 'plan-tomorrow',
            kind: 'plan_day',
            title: 'Plan tomorrow',
            description: 'Block out the important work.',
            action: { type: 'plan_day', payload: { date: '2026-06-13' } },
          },
        ],
      }),
    );

    renderTodayPage('en');

    expect(await screen.findByRole('button', { name: /Create task "Alpha"/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Plan tomorrow' })).toBeInTheDocument();
    expect(screen.queryByText('Lumi suggests')).not.toBeInTheDocument();
  });
});

describe('TodayPage confirmation decisions', () => {
  it('expands and collapses confirmation details inline without opening a sheet', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());

    renderTodayPage();

    const alpha = await screen.findByRole('button', { name: /Create task "Alpha"/ });
    await user.click(alpha);

    expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    expect(screen.getByText('This change stays inside Lumi.')).toBeInTheDocument();
    expect(screen.getByText('Task')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Decline' })).toBeInTheDocument();

    await user.click(alpha);

    expect(screen.queryByText('This change stays inside Lumi.')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
  });

  it('handles an accepted confirmation inline and keeps the remaining item', async () => {
    const user = userEvent.setup();
    const todaySpy = vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());
    const acceptSpy = vi.spyOn(api, 'acceptConfirmation').mockResolvedValue(makeDecisionResponse());

    renderTodayPage();

    await screen.findByRole('button', { name: /Create task "Alpha"/ });
    await user.click(screen.getByRole('button', { name: /Create task "Alpha"/ }));

    expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    expect(screen.getByText('Task')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(screen.getByText('Task created: Alpha.')).toBeInTheDocument();
    });
    expect(acceptSpy).toHaveBeenCalledWith(firstConfirmationId);
    expect(screen.queryByRole('button', { name: /Create task "Alpha"/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create task "Beta"/ })).toBeInTheDocument();
    expect(todaySpy).toHaveBeenCalledTimes(1);
  });

  it('handles a rejected confirmation inline and keeps the remaining item', async () => {
    const user = userEvent.setup();
    const todaySpy = vi.spyOn(api, 'getToday').mockResolvedValue(makeTodayResponse());
    const rejectSpy = vi.spyOn(api, 'rejectConfirmation').mockResolvedValue(makeRejectResponse());

    renderTodayPage();

    await screen.findByRole('button', { name: /Create task "Alpha"/ });
    await user.click(screen.getByRole('button', { name: /Create task "Alpha"/ }));

    expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    expect(screen.getByText('Task')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Decline' }));

    await waitFor(() => {
      expect(screen.getByText("Ok, I won't do it.")).toBeInTheDocument();
    });
    expect(rejectSpy).toHaveBeenCalledWith(firstConfirmationId);
    expect(screen.queryByRole('button', { name: /Create task "Alpha"/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create task "Beta"/ })).toBeInTheDocument();
    expect(todaySpy).toHaveBeenCalledTimes(1);
  });
});
