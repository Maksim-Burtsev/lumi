import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { FocusSession, FocusStateResponse, FocusSummaryResponse, ProjectsResponse, SettingsResponse, TasksResponse, User } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import { localRangeToIso } from '../lib/focusTime';
import FocusPage, { aggregateActivityForChart, getDialMetrics } from './FocusPage';

const LUMI_PROJECT_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const CONTENT_PROJECT_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const QA_PROJECT_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

const TASKS: TasksResponse = {
  items: [
    {
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Focus timer v1',
      description: null,
      status: 'active',
      priority: 'medium',
      project: 'Lumi',
      project_id: LUMI_PROJECT_ID,
      tags: [],
      due_at: null,
      target_at: null,
      reminder_at: null,
      snoozed_until: null,
      estimated_minutes: null,
      estimate_source: null,
      review_skips: {},
      source: 'manual',
      created_at: '2026-06-24T10:00:00Z',
      completed_at: null,
    },
    {
      id: '33333333-3333-4333-8333-333333333333',
      title: 'Написать пост про фокус',
      description: null,
      status: 'inbox',
      priority: 'medium',
      project: 'Content',
      project_id: CONTENT_PROJECT_ID,
      tags: [],
      due_at: null,
      target_at: null,
      reminder_at: null,
      snoozed_until: null,
      estimated_minutes: null,
      estimate_source: null,
      review_skips: {},
      source: 'manual',
      created_at: '2026-06-24T11:00:00Z',
      completed_at: null,
    },
    {
      id: '44444444-4444-4444-8444-444444444444',
      title: 'Закрытая задача',
      description: null,
      status: 'done',
      priority: 'medium',
      project: 'Lumi',
      project_id: LUMI_PROJECT_ID,
      tags: [],
      due_at: null,
      target_at: null,
      reminder_at: null,
      snoozed_until: null,
      estimated_minutes: null,
      estimate_source: null,
      review_skips: {},
      source: 'manual',
      created_at: '2026-06-24T09:00:00Z',
      completed_at: '2026-06-24T09:30:00Z',
    },
  ],
};

const PROJECTS: ProjectsResponse = {
  items: [
    {
      id: LUMI_PROJECT_ID,
      name: 'Lumi',
      status: 'active',
      color: null,
      system_key: null,
      is_system: false,
      active_task_count: 1,
      completed_task_count: 1,
      estimated_minutes_total: 0,
      health_status: 'moving',
      health_reason: 'Active',
      next_task: TASKS.items[0],
      created_at: '2026-06-20T10:00:00Z',
    },
    {
      id: CONTENT_PROJECT_ID,
      name: 'Content',
      status: 'active',
      color: null,
      system_key: null,
      is_system: false,
      active_task_count: 1,
      completed_task_count: 0,
      estimated_minutes_total: 0,
      health_status: 'moving',
      health_reason: 'Active',
      next_task: TASKS.items[1],
      created_at: '2026-06-20T10:00:00Z',
    },
    {
      id: QA_PROJECT_ID,
      name: 'QA Project',
      status: 'active',
      color: null,
      system_key: null,
      is_system: false,
      active_task_count: 0,
      completed_task_count: 0,
      estimated_minutes_total: 0,
      health_status: 'quiet',
      health_reason: 'No tasks',
      next_task: null,
      created_at: '2026-06-20T10:00:00Z',
    },
  ],
};

const EMPTY_STATE: FocusStateResponse = {
  active_session: null,
  today: {
    focus_seconds: 0,
    completed_sessions: 0,
    streak_days: 0,
  },
  recent_sessions: [],
};

const SUMMARY: FocusSummaryResponse = {
  period: 'week',
  total_focus_seconds: 0,
  total_sessions: 0,
  streak_days: 0,
  average_focus_score: null,
  average_daily_focus_seconds: 0,
  average_daily_focus_delta_percent: null,
  total_focus_delta_percent: null,
  most_focused_daypart: null,
  daypart_breakdown: [],
  daily_activity: [],
  project_breakdown: [],
  next_steps: [],
};

function makeUser(locale = 'en'): User {
  return {
    id: '99999999-9999-4999-8999-999999999999',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'Asia/Yerevan',
    locale,
    settings: {},
    created_at: '2026-06-24T10:00:00Z',
    last_seen_at: null,
  };
}

function makeSettings(locale = 'en'): SettingsResponse {
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

function makeSession(overrides: Partial<FocusSession> = {}): FocusSession {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    status: 'completed',
    task: null,
    project_id: LUMI_PROJECT_ID,
    project_name: 'Lumi',
    local_date: '2026-06-24',
    intention: 'Написать черновик спецификации',
    planned_minutes: 45,
    started_at: '2026-06-24T10:00:00Z',
    target_end_at: '2026-06-24T10:45:00Z',
    ended_at: '2026-06-24T10:45:00Z',
    duration_seconds: 45 * 60,
    reflection: {
      accomplished_text: null,
      distraction_text: null,
      next_step_text: null,
      focus_score: null,
    },
    ...overrides,
  };
}

function makeSessions(count: number): FocusSession[] {
  return Array.from({ length: count }, (_, index) =>
    makeSession({
      id: `${String(index + 1).padStart(8, '0')}-7777-4777-8777-777777777777`,
      intention: `History session ${index + 1}`,
      started_at: new Date(Date.UTC(2026, 5, 27, 10, 0, 0) - index * 60 * 60_000).toISOString(),
      local_date: new Date(Date.UTC(2026, 5, 27, 10, 0, 0) - index * 60 * 60_000).toISOString().slice(0, 10),
      target_end_at: new Date(Date.UTC(2026, 5, 27, 10, 45, 0) - index * 60 * 60_000).toISOString(),
      ended_at: new Date(Date.UTC(2026, 5, 27, 10, 45, 0) - index * 60 * 60_000).toISOString(),
      duration_seconds: (20 + index) * 60,
    }),
  );
}

function renderFocusPage(locale = 'en') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettings(locale));
  vi.spyOn(api, 'listProjects').mockResolvedValue(PROJECTS);
  const sessionsSpy = vi.isMockFunction(api.listFocusSessions)
    ? vi.mocked(api.listFocusSessions)
    : vi.spyOn(api, 'listFocusSessions');
  if (!sessionsSpy.getMockImplementation()) {
    sessionsSpy.mockResolvedValue({ items: [] });
  }
  const sessionSpy = vi.isMockFunction(api.getFocusSession)
    ? vi.mocked(api.getFocusSession)
    : vi.spyOn(api, 'getFocusSession');
  if (!sessionSpy.getMockImplementation()) {
    sessionSpy.mockImplementation(async (id) => {
      const response = await api.listFocusSessions({ period: 'week', limit: 100, offset: 0 });
      return { session: response.items.find((item) => item.id === id) ?? makeSession({ id }) };
    });
  }
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <FocusPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe('FocusPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps the dial progress proportional to elapsed time', () => {
    const started = new Date('2026-06-24T10:00:00Z').getTime();
    const metrics = getDialMetrics({
      started,
      target: started + 25 * 60_000,
      now: started + 30_000,
    });

    expect(metrics.progress).toBeCloseTo(0.02, 3);
  });

  it('aggregates long custom ranges into truthful weekly chart buckets', () => {
    const days = Array.from({ length: 40 }, (_, index) => ({
      date: `2026-06-${String(index + 1).padStart(2, '0')}`,
      focus_seconds: 30 * 60,
      session_count: 1,
      average_focus_score: 4,
    }));

    const weeks = aggregateActivityForChart(days);

    expect(weeks).toHaveLength(6);
    expect(weeks[0]).toMatchObject({ focus_seconds: 7 * 30 * 60, session_count: 7, average_focus_score: 4 });
    expect(weeks[5]).toMatchObject({ focus_seconds: 5 * 30 * 60, session_count: 5 });
  });

  it('rejects nonexistent DST wall times and chooses the earlier instant for a fold', () => {
    const gap = localRangeToIso('2026-03-29', '02:30', '2026-03-29', '03:30', 'Europe/Berlin');
    expect(gap.valid).toBe(false);

    const fold = localRangeToIso('2026-10-25', '02:30', '2026-10-25', '03:30', 'Europe/Berlin');
    expect(fold.valid).toBe(true);
    expect(fold.started_at).toBe('2026-10-25T00:30:00.000Z');
    expect(fold.duration_minutes).toBe(120);
  });

  it('accepts manual ranges up to 240 minutes and rejects 241 minutes', () => {
    const accepted = localRangeToIso('2026-06-24', '10:00', '2026-06-24', '14:00', 'Asia/Yerevan');
    expect(accepted).toMatchObject({ valid: true, duration_minutes: 240 });

    const rejected = localRangeToIso('2026-06-24', '10:00', '2026-06-24', '14:01', 'Asia/Yerevan');
    expect(rejected).toMatchObject({ valid: false, duration_minutes: 241 });
  });

  it('shows an explicit retry state instead of treating a failed state request as no active timer', async () => {
    const user = userEvent.setup();
    const state = vi.spyOn(api, 'getFocusState')
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);

    renderFocusPage('en');

    expect(await screen.findByRole('alert')).toHaveTextContent('timer may still be running');
    expect(screen.queryByRole('button', { name: /start session/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByRole('button', { name: /start session/i })).toBeInTheDocument();
    expect(state).toHaveBeenCalledTimes(2);
  });

  it('starts a task-linked session and shows the breathing orb', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: {
        id: '22222222-2222-4222-8222-222222222222',
        status: 'active',
        task: TASKS.items[0],
        project_id: LUMI_PROJECT_ID,
        project_name: 'Lumi',
        local_date: '2026-06-24',
        intention: 'Написать черновик спецификации',
        planned_minutes: 45,
        started_at: new Date(Date.now() - 32 * 60_000).toISOString(),
        target_end_at: new Date(Date.now() + 13 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
        reflection: {
          accomplished_text: null,
          distraction_text: null,
          next_step_text: null,
          focus_score: null,
        },
      },
    });

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /start session/i }));
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'Написать черновик спецификации' } });
    await user.click(screen.getByRole('button', { name: /choose task/i }));
    await user.click(screen.getByText('Focus timer v1'));
    await screen.findByRole('button', { name: /start 45 min/i });
    fireEvent.click(screen.getByRole('button', { name: /start 45 min/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[0].id,
        project_id: LUMI_PROJECT_ID,
        project_name: 'Lumi',
        intention: 'Написать черновик спецификации',
        planned_minutes: 45,
      });
    });
    expect(await screen.findByText('Написать черновик спецификации')).toBeInTheDocument();
    expect(screen.getByLabelText('Session progress')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /прогресс/i })).not.toBeInTheDocument();
  });

  it('starts with a custom duration and searchable task picker', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: {
        id: '22222222-2222-4222-8222-222222222222',
        status: 'active',
        task: TASKS.items[1],
        project_id: CONTENT_PROJECT_ID,
        project_name: 'Content',
        local_date: '2026-06-24',
        intention: 'Пишу текст',
        planned_minutes: 37,
        started_at: new Date().toISOString(),
        target_end_at: new Date(Date.now() + 37 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
        reflection: {
          accomplished_text: null,
          distraction_text: null,
          next_step_text: null,
          focus_score: null,
        },
      },
    });

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /start session/i }));
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'Пишу текст' } });
    fireEvent.change(screen.getByLabelText('Custom duration'), { target: { value: '37' } });
    await user.click(screen.getByRole('button', { name: /choose task/i }));
    await user.type(screen.getByPlaceholderText('Search tasks'), 'пост');

    expect(screen.getByText('Написать пост про фокус')).toBeInTheDocument();
    expect(screen.queryByText('Закрытая задача')).not.toBeInTheDocument();

    await user.click(screen.getByText('Написать пост про фокус'));
    await screen.findByRole('button', { name: /start 37 min/i });
    fireEvent.click(screen.getByRole('button', { name: /start 37 min/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[1].id,
        project_id: CONTENT_PROJECT_ID,
        project_name: 'Content',
        intention: 'Пишу текст',
        planned_minutes: 37,
      });
    });
  });

  it('lets project override task project in the start flow', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      project_breakdown: [{ project_id: QA_PROJECT_ID, project_name: 'QA Project', focus_seconds: 39 * 60, session_count: 1 }],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: makeSession({
        status: 'active',
        task: TASKS.items[0],
        project_id: QA_PROJECT_ID,
        project_name: 'QA Project',
        started_at: new Date().toISOString(),
        target_end_at: new Date(Date.now() + 45 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
      }),
    });

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /start session/i }));
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'Override project' } });
    await user.click(screen.getByRole('button', { name: /choose task/i }));
    await user.click(screen.getByText('Focus timer v1'));
    await screen.findByRole('button', { name: /choose project/i });
    fireEvent.click(screen.getByRole('button', { name: /choose project/i }));
    const projectPicker = screen.getByRole('dialog', { name: /choose project/i });
    await user.click(within(projectPicker).getByRole('button', { name: 'QA Project' }));
    await screen.findByRole('button', { name: /start 45 min/i });
    fireEvent.click(screen.getByRole('button', { name: /start 45 min/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[0].id,
        project_id: QA_PROJECT_ID,
        project_name: 'QA Project',
        intention: 'Override project',
        planned_minutes: 45,
      });
    });
  });

  it('logs a completed focus block without starting an active timer', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const logFocus = vi.spyOn(api, 'logFocusSession').mockResolvedValue({
      session: {
        id: '55555555-5555-4555-8555-555555555555',
        status: 'completed',
        task: null,
        project_id: LUMI_PROJECT_ID,
        project_name: 'Lumi',
        local_date: '2026-06-24',
        intention: 'Ретро блок',
        planned_minutes: 37,
        started_at: '2026-06-24T10:00:00Z',
        target_end_at: '2026-06-24T10:37:00Z',
        ended_at: '2026-06-24T10:37:00Z',
        duration_seconds: 37 * 60,
        reflection: {
          accomplished_text: 'Сделал',
          distraction_text: null,
          next_step_text: null,
          focus_score: 4,
        },
      },
    });

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /log session/i }));
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'Ретро блок' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-06-24' } });
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '10:00' } });
    fireEvent.change(screen.getByLabelText('Custom duration'), { target: { value: '37' } });
    fireEvent.change(screen.getByLabelText('What did you do?'), { target: { value: 'Сделал' } });
    await user.click(screen.getByRole('button', { name: /save block/i }));

    await waitFor(() => {
      expect(logFocus).toHaveBeenCalledWith({
        task_id: null,
        project_id: null,
        project_name: null,
        intention: 'Ретро блок',
        logged_at: expect.any(String),
        duration_minutes: 37,
        accomplished_text: 'Сделал',
        distraction_text: null,
        next_step_text: null,
        focus_score: null,
      });
    });
  });

  it('resets the manual log range to a fresh block ending now on every open', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /log session/i }));
    let logDialog = await screen.findByRole('dialog', { name: /log session/i });
    fireEvent.change(within(logDialog).getByLabelText('End date'), { target: { value: '2020-01-01' } });
    logDialog = screen.getByRole('dialog', { name: /log session/i });
    fireEvent.click(within(logDialog).getByRole('button', { name: /^close$/i }));
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /log session/i })).not.toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /log session/i }));
    logDialog = await screen.findByRole('dialog', { name: /log session/i });
    expect(within(logDialog).getByLabelText('End date')).not.toHaveValue('2020-01-01');
  });

  it('renders active focus mode without inline analytics and opens details', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      active_session: makeSession({
        status: 'active',
        intention: 'Write product spec',
        project_id: LUMI_PROJECT_ID,
        project_name: 'Lumi',
        started_at: new Date(Date.now() - 60_000).toISOString(),
        target_end_at: new Date(Date.now() + 24 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
      }),
      today: { focus_seconds: 50 * 60, completed_sessions: 4, streak_days: 3 },
      recent_sessions: [makeSession({ intention: 'Past block', started_at: '2026-06-24T10:00:00Z' })],
    });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      period: 'week',
      total_focus_seconds: 50 * 60,
      total_sessions: 1,
      streak_days: 3,
      average_focus_score: 4,
      daily_activity: [{ date: '2026-06-24', focus_seconds: 50 * 60, session_count: 1 }],
      project_breakdown: [{ project_id: LUMI_PROJECT_ID, project_name: 'Lumi', focus_seconds: 50 * 60, session_count: 1 }],
      next_steps: [],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    expect(await screen.findByText('Focus mode is on')).toBeInTheDocument();
    expect(screen.getByText('Details & History')).toBeInTheDocument();
    expect(screen.getByText('sessions today')).toBeInTheDocument();
    expect(screen.getByText('day streak')).toBeInTheDocument();
    expect(screen.getByText('focus days')).toBeInTheDocument();
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument();
    expect(screen.queryByText('History')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /details & history/i }));

    expect(await screen.findByText('Session history')).toBeInTheDocument();
  });

  it('renders overtime alarm state with dominant stop and review action', async () => {
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      active_session: makeSession({
        status: 'active',
        intention: 'Overtime session',
        started_at: new Date(Date.now() - 30 * 60_000).toISOString(),
        target_end_at: new Date(Date.now() - 5 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
      }),
      today: { focus_seconds: 0, completed_sessions: 0, streak_days: 0 },
      recent_sessions: [],
    });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    expect(await screen.findByText('Timer ended')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stop timer & review/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /keep counting/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Session progress')).toHaveTextContent('+');
  });

  it('has no deceptive active edit action and confirms cancellation in the shared sheet stack', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      status: 'active',
      intention: 'Protected session',
      started_at: new Date(Date.now() - 60_000).toISOString(),
      target_end_at: new Date(Date.now() + 24 * 60_000).toISOString(),
      ended_at: null,
      duration_seconds: null,
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      active_session: session,
      today: { focus_seconds: 0, completed_sessions: 0, streak_days: 0 },
      recent_sessions: [],
    });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    const abandon = vi.spyOn(api, 'abandonFocusSession').mockResolvedValue({
      session: { ...session, status: 'abandoned', ended_at: new Date().toISOString(), duration_seconds: 60 },
    });

    renderFocusPage('en');

    expect(await screen.findByText('Protected session')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^edit session$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(await screen.findByRole('dialog', { name: /cancel this session/i })).toBeInTheDocument();
    expect(document.querySelectorAll('[role="dialog"][aria-modal="true"]')).toHaveLength(1);
    expect(abandon).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /discard session/i }));
    await waitFor(() => expect(abandon).toHaveBeenCalledWith(session.id));
  });

  it('uses the app locale and can start an untitled session', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: makeSession({
        status: 'active',
        intention: 'Session',
        started_at: new Date().toISOString(),
        target_end_at: new Date(Date.now() + 45 * 60_000).toISOString(),
        ended_at: null,
        duration_seconds: null,
      }),
    });

    renderFocusPage('en');

    expect(await screen.findByText('Ready for a session?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start session/i })).toBeInTheDocument();
    expect(screen.queryByText('Готов к сессии?')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /start session/i }));
    await user.click(screen.getByRole('button', { name: /start 45 min/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: null,
        project_id: null,
        project_name: null,
        intention: 'Session',
        planned_minutes: 45,
      });
    });
  });

  it('opens history details with clickable days, project split, and sessions', async () => {
    const user = userEvent.setup();
    const recentSession = makeSession({
      id: '77777777-7777-4777-8777-777777777777',
      project_id: QA_PROJECT_ID,
      project_name: 'QA Project',
      intention: 'QA custom session',
      duration_seconds: 39 * 60,
      reflection: {
        accomplished_text: 'Checked timer start and history',
        distraction_text: null,
        next_step_text: null,
        focus_score: 4,
      },
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      ...EMPTY_STATE,
      recent_sessions: [recentSession],
    });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      period: 'week',
      total_focus_seconds: 39 * 60,
      total_sessions: 1,
      streak_days: 1,
      average_focus_score: 4,
      daily_activity: [
        { date: '2026-06-23', focus_seconds: 0, session_count: 0 },
        { date: '2026-06-24', focus_seconds: 39 * 60, session_count: 1 },
        { date: '2026-06-25', focus_seconds: 0, session_count: 0 },
      ],
      project_breakdown: [{ project_id: QA_PROJECT_ID, project_name: 'QA Project', focus_seconds: 39 * 60, session_count: 1 }],
      next_steps: [],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [recentSession] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /view all/i }));

    expect(await screen.findByText('Session history')).toBeInTheDocument();
    expect(screen.getByText('Days')).toBeInTheDocument();
    expect(screen.getAllByText('QA Project').length).toBeGreaterThan(0);
    expect(screen.getAllByText('QA custom session').length).toBeGreaterThan(0);
    expect(screen.getByText('Checked timer start and history')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /2026-06-24: 39m/i }).length).toBeGreaterThan(0);
  });

  it('filters full history projects and rows by selected day and clears the day on repeat click', async () => {
    const user = userEvent.setup();
    const june24 = makeSession({
      id: 'aaaaaaaa-7777-4777-8777-777777777777',
      project_id: QA_PROJECT_ID,
      project_name: 'QA Project',
      local_date: '2026-06-24',
      intention: 'QA day session',
      started_at: '2026-06-24T10:00:00Z',
      target_end_at: '2026-06-24T10:39:00Z',
      ended_at: '2026-06-24T10:39:00Z',
      duration_seconds: 39 * 60,
    });
    const june25 = makeSession({
      id: 'bbbbbbbb-7777-4777-8777-777777777777',
      project_id: LUMI_PROJECT_ID,
      project_name: 'Lumi',
      local_date: '2026-06-25',
      intention: 'Lumi other day',
      started_at: '2026-06-25T12:00:00Z',
      target_end_at: '2026-06-25T12:50:00Z',
      ended_at: '2026-06-25T12:50:00Z',
      duration_seconds: 50 * 60,
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      ...EMPTY_STATE,
      recent_sessions: [june25, june24],
    });
    const fullSummary: FocusSummaryResponse = {
      ...SUMMARY,
      period: 'week',
      total_focus_seconds: 89 * 60,
      total_sessions: 2,
      daily_activity: [
        { date: '2026-06-24', focus_seconds: 39 * 60, session_count: 1 },
        { date: '2026-06-25', focus_seconds: 50 * 60, session_count: 1 },
      ],
      project_breakdown: [
        { project_id: LUMI_PROJECT_ID, project_name: 'Lumi', focus_seconds: 50 * 60, session_count: 1 },
        { project_id: QA_PROJECT_ID, project_name: 'QA Project', focus_seconds: 39 * 60, session_count: 1 },
      ],
    };
    const summary = vi.spyOn(api, 'getFocusSummary').mockImplementation(async (input) => {
      const query = typeof input === 'string' ? { period: input } : (input ?? { period: 'week' });
      if (query.period === 'custom' && query.from_date === '2026-06-24' && query.to_date === '2026-06-24') {
        return {
          ...fullSummary,
          period: 'custom',
          total_focus_seconds: 39 * 60,
          total_sessions: 1,
          daily_activity: [{ date: '2026-06-24', focus_seconds: 39 * 60, session_count: 1 }],
          project_breakdown: [{ project_id: QA_PROJECT_ID, project_name: 'QA Project', focus_seconds: 39 * 60, session_count: 1 }],
        };
      }
      return fullSummary;
    });
    const list = vi.spyOn(api, 'listFocusSessions').mockImplementation(async (input) => {
      const query = typeof input === 'string' ? { period: input } : (input ?? { period: 'week' });
      return {
        items: query.period === 'custom' && query.from_date === '2026-06-24' && query.to_date === '2026-06-24'
          ? [june24]
          : [june25, june24],
      };
    });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /view all/i }));
    await screen.findByRole('dialog', { name: /session history/i });

    const history = () => screen.getByRole('dialog', { name: /session history/i });
    const selectedDayButton = () => within(history()).getByRole('button', { name: /2026-06-24: 39m/i });
    fireEvent.click(selectedDayButton());

    expect(await within(history()).findByText('Projects on Jun 24')).toBeInTheDocument();
    await waitFor(() => {
      expect(list).toHaveBeenCalledWith(expect.objectContaining({
        period: 'custom',
        from_date: '2026-06-24',
        to_date: '2026-06-24',
        offset: 0,
      }));
      expect(summary).toHaveBeenCalledWith(expect.objectContaining({
        period: 'custom',
        from_date: '2026-06-24',
        to_date: '2026-06-24',
      }));
    });
    expect(within(history()).getByText('Sessions on Jun 24')).toBeInTheDocument();
    expect(within(history()).getByText('QA day session')).toBeInTheDocument();
    expect(within(history()).queryByText('Lumi other day')).not.toBeInTheDocument();
    expect(within(history()).getAllByText('QA Project').length).toBeGreaterThan(0);
    expect(within(history()).queryByText('Lumi', { selector: 'span' })).not.toBeInTheDocument();

    expect(selectedDayButton()).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(selectedDayButton());

    expect(within(history()).getByText('Projects this week')).toBeInTheDocument();
    expect(within(history()).getByText('Lumi other day')).toBeInTheDocument();
    expect(within(history()).getByText('QA day session')).toBeInTheDocument();
    expect(selectedDayButton()).toHaveAttribute('aria-pressed', 'false');
    expect(selectedDayButton().className).toContain('focus-visible:shadow');
    expect(selectedDayButton().className).not.toContain('focus:shadow');
  });

  it('uses server search, project filters, and deterministic infinite history offsets', async () => {
    const user = userEvent.setup();
    const session = makeSession({ intention: 'Paginated session', project_id: QA_PROJECT_ID, project_name: 'QA Project' });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    const summary = vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      total_focus_seconds: 9 * 3600,
      total_sessions: 70,
      project_breakdown: [{ project_id: QA_PROJECT_ID, project_name: 'QA Project', focus_seconds: 9 * 3600, session_count: 70 }],
    });
    const list = vi.spyOn(api, 'listFocusSessions').mockImplementation(async (input) => {
      const query = typeof input === 'string' ? { period: input } : (input ?? {});
      if (query.limit === 50 && query.offset === 0 && !query.q && !query.project_id) {
        return { items: [session], has_more: true, next_offset: 50 };
      }
      return {
        items: query.offset === 50 ? [{ ...session, id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', intention: 'Second page' }] : [session],
        has_more: false,
        next_offset: null,
      };
    });

    renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /view all/i }));
    const history = await screen.findByRole('dialog', { name: /session history/i });
    expect(within(history).getByText('9h 00m')).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole('dialog', { name: /session history/i })).getByRole('button', { name: /load more/i }));
    await waitFor(() => expect(list).toHaveBeenCalledWith(expect.objectContaining({ limit: 50, offset: 50 })));

    fireEvent.change(within(screen.getByRole('dialog', { name: /session history/i })).getByPlaceholderText('Search sessions'), { target: { value: 'needle' } });
    await waitFor(() => expect(list).toHaveBeenCalledWith(expect.objectContaining({ q: 'needle', offset: 0 })));
    await waitFor(() => expect(summary).toHaveBeenCalledWith(expect.objectContaining({ q: 'needle' })));

    fireEvent.change(within(screen.getByRole('dialog', { name: /session history/i })).getByRole('combobox', { name: /project/i }), { target: { value: QA_PROJECT_ID } });
    await waitFor(() => expect(list).toHaveBeenCalledWith(expect.objectContaining({ project_id: QA_PROJECT_ID, offset: 0 })));
    await waitFor(() => expect(summary).toHaveBeenCalledWith(expect.objectContaining({ q: 'needle', project_id: QA_PROJECT_ID })));
  });

  it('rejects reversed and overlong custom ranges before querying them', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });

    renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /view all/i }));
    await screen.findByRole('dialog', { name: /session history/i });
    fireEvent.click(within(screen.getByRole('dialog', { name: /session history/i })).getByRole('button', { name: /^custom$/i }));
    const fromInput = await screen.findByLabelText('From');
    fireEvent.change(fromInput, { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-12-31' } });
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('up to 180 days');
  });

  it('renders weekly KPI strip with baseline deltas and most focused daypart', async () => {
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      total_focus_seconds: 18 * 3600 + 40 * 60,
      total_sessions: 42,
      average_focus_score: 4.2,
      average_daily_focus_seconds: 2 * 3600 + 40 * 60,
      average_daily_focus_delta_percent: 18,
      total_focus_delta_percent: -6,
      most_focused_daypart: 'morning',
      daily_activity: [{ date: '2026-06-27', focus_seconds: 2 * 3600, session_count: 3 }],
      project_breakdown: [{ project_id: LUMI_PROJECT_ID, project_name: 'Lumi', focus_seconds: 6 * 3600, session_count: 10 }],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    expect(await screen.findByText('Avg/day')).toBeInTheDocument();
    expect(screen.getByText('Most focused')).toBeInTheDocument();
    expect(await screen.findByText('Morning')).toBeInTheDocument();
    expect(await screen.findByText('↑ 18%')).toBeInTheDocument();
    expect(await screen.findByText('↓ 6%')).toBeInTheDocument();
  });

  it('renders month analytics as 31 daily bars with scoped session copy and selected day summary', async () => {
    const user = userEvent.setup();
    const monthSummary: FocusSummaryResponse = {
      ...SUMMARY,
      period: 'month',
      total_focus_seconds: 112 * 3600 + 20 * 60,
      total_sessions: 146,
      average_focus_score: 4.1,
      average_daily_focus_seconds: 3 * 3600 + 37 * 60,
      daily_activity: Array.from({ length: 30 }, (_, index) => ({
        date: `2026-06-${String(index + 1).padStart(2, '0')}`,
        focus_seconds: index === 26 ? 7 * 3600 + 10 * 60 : (index % 6) * 1800,
        session_count: index === 26 ? 9 : index % 4,
      })),
      project_breakdown: [{ project_id: LUMI_PROJECT_ID, project_name: 'Lumi', focus_seconds: 7 * 3600, session_count: 12 }],
    };
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    const summary = vi.spyOn(api, 'getFocusSummary').mockImplementation((input = 'week') => {
      const period = typeof input === 'string' ? input : input.period;
      if (period === 'custom' && typeof input !== 'string' && input.from_date === '2026-06-27') {
        return Promise.resolve({
          ...SUMMARY,
          period: 'custom',
          total_focus_seconds: 7 * 3600 + 10 * 60,
          total_sessions: 9,
          project_breakdown: monthSummary.project_breakdown,
        });
      }
      return Promise.resolve(period === 'month' ? monthSummary : SUMMARY);
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    const queryClient = renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /month/i }));

    expect(await screen.findByText('146 sessions this month')).toBeInTheDocument();
    expect(screen.getByText('4.1 avg focus score')).toBeInTheDocument();
    expect(await screen.findAllByTestId('focus-day-bar')).toHaveLength(30);

    await user.click(screen.getByRole('button', { name: /2026-06-27: 7h 10m/i }));

    await waitFor(() => expect(summary).toHaveBeenCalledWith(expect.objectContaining({
      period: 'custom',
      from_date: '2026-06-27',
      to_date: '2026-06-27',
    })));

    expect(await screen.findByText('Jun 27')).toBeInTheDocument();
    expect(screen.getByText('7h 10m')).toBeInTheDocument();
    expect(screen.getByText('9 sessions')).toBeInTheDocument();

    act(() => {
      queryClient.setQueryData(['settings'], {
        ...makeSettings('en'),
        user: { ...makeUser('en'), timezone: 'Pacific/Chatham' },
      });
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /2026-06-27: 7h 10m/i })).toHaveAttribute('aria-pressed', 'false');
    });
  });

  it('caps main history preview at five sessions and opens full history', async () => {
    const user = userEvent.setup();
    const sessions = makeSessions(8);
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: sessions });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: sessions });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    expect(await screen.findByText('History session 1')).toBeInTheDocument();
    expect(screen.getByText('History session 5')).toBeInTheDocument();
    expect(screen.queryByText('History session 6')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /view all history/i }));

    const dialog = await screen.findByRole('dialog', { name: /session history/i });
    expect(dialog).toHaveClass('h-[88dvh]');
    expect(dialog).toHaveClass('max-h-[88dvh]');
    expect(screen.getByText('History session 8')).toBeInTheDocument();
  });

  it('opens session details instead of history when a history row is clicked', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Clicked session',
      project_id: LUMI_PROJECT_ID,
      project_name: 'Lumi',
      reflection: {
        accomplished_text: 'Filled later',
        distraction_text: null,
        next_step_text: 'Retest',
        focus_score: 5,
      },
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /clicked session/i }));

    expect(await screen.findByText('Session details')).toBeInTheDocument();
    expect(screen.getByText('Filled later')).toBeInTheDocument();
    expect(screen.queryByText('Session history')).not.toBeInTheDocument();
  });

  it('opens session details as a layer over full history and returns to the same history sheet', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Layered session',
      project_id: LUMI_PROJECT_ID,
      project_name: 'Lumi',
      reflection: {
        accomplished_text: 'Checked layer',
        distraction_text: null,
        next_step_text: null,
        focus_score: 4,
      },
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue({
      ...SUMMARY,
      daily_activity: [{ date: '2026-06-24', focus_seconds: 45 * 60, session_count: 1 }],
      project_breakdown: [{ project_id: LUMI_PROJECT_ID, project_name: 'Lumi', focus_seconds: 45 * 60, session_count: 1 }],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /view all/i }));
    const history = await screen.findByRole('dialog', { name: /session history/i });
    expect(within(history).getByText('Session history')).toBeInTheDocument();
    await user.click(within(history).getByRole('button', { name: /layered session/i }));

    expect(await screen.findByText('Session details')).toBeInTheDocument();
    expect(screen.getByText('Session history')).toBeInTheDocument();
    expect(screen.getAllByText('Checked layer').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: /^history$/i }));

    await waitFor(() => {
      expect(screen.queryByText('Session details')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Session history')).toBeInTheDocument();
    expect(screen.getAllByText('Layered session').length).toBeGreaterThan(0);
  });

  it('uses one edit session action and header trash action in session details', async () => {
    const user = userEvent.setup();
    const session = makeSession({ intention: 'Action hierarchy' });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /action hierarchy/i }));

    expect(await screen.findByRole('button', { name: /^edit session$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit review/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit time/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^delete session$/i })).toBeInTheDocument();
  });

  it('edits session time and review through one edit session sheet', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Editable session',
      started_at: '2026-06-24T10:00:00Z',
      target_end_at: '2026-06-24T10:45:00Z',
      ended_at: '2026-06-24T10:45:00Z',
      duration_seconds: 45 * 60,
      reflection: {
        accomplished_text: 'Old result',
        distraction_text: null,
        next_step_text: null,
        focus_score: 3,
      },
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const update = vi.spyOn(api, 'updateFocusSession').mockResolvedValue({
      session: {
        ...session,
        started_at: '2026-06-24T11:00:00Z',
        ended_at: '2026-06-24T12:15:00Z',
        duration_seconds: 75 * 60,
        reflection: {
          accomplished_text: 'New result',
          distraction_text: null,
          next_step_text: null,
          focus_score: 4,
        },
      },
    });

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /editable session/i }));
    await user.click(await screen.findByRole('button', { name: /^edit session$/i }));
    fireEvent.change(screen.getByLabelText('Start time'), { target: { value: '11:00' } });
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '12:15' } });
    fireEvent.change(screen.getByLabelText('What got done?'), { target: { value: 'New result' } });
    screen.getByRole('radio', { name: /focus: 3/i }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: /focus: 4/i })).toBeChecked();
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(session.id, expect.objectContaining({
        started_at: expect.any(String),
        ended_at: expect.any(String),
        accomplished_text: 'New result',
        focus_score: 4,
      }));
    });
  });

  it('edits a cross-midnight session and preserves an explicit unscored value', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Midnight handoff',
      started_at: '2026-06-24T19:50:00Z',
      target_end_at: '2026-06-24T20:10:00Z',
      ended_at: '2026-06-24T20:10:00Z',
      duration_seconds: 20 * 60,
      local_date: '2026-06-24',
      reflection: { accomplished_text: null, distraction_text: null, next_step_text: null, focus_score: 3 },
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    const update = vi.spyOn(api, 'updateFocusSession').mockResolvedValue({
      session: { ...session, reflection: { ...session.reflection, focus_score: null } },
    });

    renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /midnight handoff/i }));
    await user.click(await screen.findByRole('button', { name: /^edit session$/i }));
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-06-24' } });
    fireEvent.change(screen.getByLabelText('Start time'), { target: { value: '23:50' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-06-25' } });
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '00:10' } });
    await user.click(screen.getByRole('radio', { name: /not scored/i }));
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(update).toHaveBeenCalled());
    const payload = update.mock.calls[0][1];
    expect(new Date(payload.ended_at as string).getTime() - new Date(payload.started_at as string).getTime()).toBe(20 * 60_000);
    expect(payload.focus_score).toBeNull();
  });

  it('refetches session details by id after an edit instead of keeping a stale row snapshot', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Fresh details target',
      reflection: { accomplished_text: 'Old result', distraction_text: null, next_step_text: null, focus_score: null },
    });
    const refreshed = {
      ...session,
      reflection: { ...session.reflection, accomplished_text: 'Fresh result from server' },
    };
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    const getSession = vi.spyOn(api, 'getFocusSession')
      .mockResolvedValueOnce({ session })
      .mockResolvedValue({ session: refreshed });
    vi.spyOn(api, 'updateFocusSession').mockResolvedValue({ session: refreshed });

    renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /fresh details target/i }));
    await user.click(await screen.findByRole('button', { name: /^edit session$/i }));
    fireEvent.change(screen.getByLabelText('What got done?'), { target: { value: 'Fresh result from server' } });
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    expect(await screen.findByText('Fresh result from server')).toBeInTheDocument();
    expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('deletes a completed session after confirmation', async () => {
    const user = userEvent.setup();
    const session = makeSession({ intention: 'Delete target' });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({ ...EMPTY_STATE, recent_sessions: [session] });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [session] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const deleteFocusSession = vi
      .spyOn(api as typeof api & { deleteFocusSession: (id: string) => Promise<void> }, 'deleteFocusSession')
      .mockResolvedValue(undefined);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /delete target/i }));
    await user.click(await screen.findByRole('button', { name: /delete session/i }));

    expect(await screen.findByText('Delete session?')).toBeInTheDocument();
    expect(screen.getByText('This removes the time block from analytics and history.')).toBeInTheDocument();
    expect(document.querySelectorAll('[role="dialog"][aria-modal="true"]')).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => {
      expect(deleteFocusSession).toHaveBeenCalledWith(session.id);
    });
  });

  it('stops an overtime session before opening review so duration no longer grows', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      status: 'active',
      intention: 'Ringing session',
      started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      target_end_at: new Date(Date.now() - 60_000).toISOString(),
      ended_at: null,
      duration_seconds: null,
    });
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      active_session: session,
      today: { focus_seconds: 0, completed_sessions: 0, streak_days: 0 },
      recent_sessions: [],
    });
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const finish = vi.spyOn(api, 'finishFocusSession').mockResolvedValue({
      session: makeSession({
        ...session,
        status: 'completed',
        ended_at: new Date().toISOString(),
        duration_seconds: 5 * 60,
      }),
    });

    renderFocusPage('en');

    const stopButton = await screen.findByRole('button', { name: /stop timer & review/i });
    expect(stopButton).not.toBeDisabled();
    await user.click(stopButton);

    await waitFor(() => {
      expect(finish).toHaveBeenCalledWith(session.id, {});
    });
    expect(await screen.findByText('Session review')).toBeInTheDocument();
  });

  it('clears the cached active session after finish even when reconciliation refetch fails', async () => {
    const user = userEvent.setup();
    const activeSession = makeSession({
      status: 'active',
      intention: 'Finish through outage',
      started_at: new Date(Date.now() - 10 * 60_000).toISOString(),
      target_end_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      ended_at: null,
      duration_seconds: null,
    });
    vi.spyOn(api, 'getFocusState')
      .mockResolvedValueOnce({ ...EMPTY_STATE, active_session: activeSession })
      .mockRejectedValue(new Error('reconciliation unavailable'));
    vi.spyOn(api, 'getFocusSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'finishFocusSession').mockResolvedValue({
      session: {
        ...activeSession,
        status: 'completed',
        ended_at: new Date().toISOString(),
        duration_seconds: 10 * 60,
      },
    });

    const queryClient = renderFocusPage('en');
    await user.click(await screen.findByRole('button', { name: /finish session/i }));

    await waitFor(() => {
      expect((queryClient.getQueryData(['focus']) as FocusStateResponse | undefined)?.active_session).toBeNull();
    });
  });
});
