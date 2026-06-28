import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { FocusSession, FocusStateResponse, FocusSummaryResponse, SettingsResponse, TasksResponse, User } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import FocusPage, { getDialMetrics } from './FocusPage';

const TASKS: TasksResponse = {
  items: [
    {
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Focus timer v1',
      description: null,
      status: 'active',
      priority: 'medium',
      project: 'Lumi',
      tags: [],
      due_at: null,
      reminder_at: null,
      snoozed_until: null,
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
      tags: [],
      due_at: null,
      reminder_at: null,
      snoozed_until: null,
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
      tags: [],
      due_at: null,
      reminder_at: null,
      snoozed_until: null,
      source: 'manual',
      created_at: '2026-06-24T09:00:00Z',
      completed_at: '2026-06-24T09:30:00Z',
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
    project: 'Lumi',
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
      target_end_at: new Date(Date.UTC(2026, 5, 27, 10, 45, 0) - index * 60 * 60_000).toISOString(),
      ended_at: new Date(Date.UTC(2026, 5, 27, 10, 45, 0) - index * 60 * 60_000).toISOString(),
      duration_seconds: (20 + index) * 60,
    }),
  );
}

function renderFocusPage(locale = 'en') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettings(locale));
  const sessionsSpy = vi.spyOn(api, 'listFocusSessions');
  if (!sessionsSpy.getMockImplementation()) {
    sessionsSpy.mockResolvedValue({ items: [] });
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
        project: 'Lumi',
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

    renderFocusPage('ru');

    await user.click(await screen.findByRole('button', { name: /начать сессию/i }));
    fireEvent.change(screen.getByLabelText('Намерение'), { target: { value: 'Написать черновик спецификации' } });
    await user.click(screen.getByRole('button', { name: /выбрать задачу/i }));
    await user.click(screen.getByText('Focus timer v1'));
    await user.click(screen.getByRole('button', { name: /старт 45 мин/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[0].id,
        project: 'Lumi',
        intention: 'Написать черновик спецификации',
        planned_minutes: 45,
      });
    });
    expect(await screen.findByText('Написать черновик спецификации')).toBeInTheDocument();
    expect(screen.getByLabelText('Прогресс сессии')).toBeInTheDocument();
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
        project: 'Content',
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

    renderFocusPage('ru');

    await user.click(await screen.findByRole('button', { name: /начать сессию/i }));
    fireEvent.change(screen.getByLabelText('Намерение'), { target: { value: 'Пишу текст' } });
    fireEvent.change(screen.getByLabelText('Своя длительность'), { target: { value: '37' } });
    await user.click(screen.getByRole('button', { name: /выбрать задачу/i }));
    await user.type(screen.getByPlaceholderText('Поиск задач'), 'пост');

    expect(screen.getByText('Написать пост про фокус')).toBeInTheDocument();
    expect(screen.queryByText('Закрытая задача')).not.toBeInTheDocument();

    await user.click(screen.getByText('Написать пост про фокус'));
    await user.click(screen.getByRole('button', { name: /старт 37 мин/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[1].id,
        project: 'Content',
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
      project_breakdown: [{ project: 'QA Project', focus_seconds: 39 * 60, session_count: 1 }],
    });
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: makeSession({
        status: 'active',
        task: TASKS.items[0],
        project: 'QA Project',
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
    await user.click(screen.getByRole('button', { name: /choose project/i }));
    const qaProjectOptions = screen.getAllByText('QA Project');
    await user.click(qaProjectOptions[qaProjectOptions.length - 1]);
    await user.click(screen.getByRole('button', { name: /start 45 min/i }));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith({
        task_id: TASKS.items[0].id,
        project: 'QA Project',
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
        project: 'Lumi',
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

    renderFocusPage('ru');

    await user.click(await screen.findByRole('button', { name: /залогировать/i }));
    fireEvent.change(screen.getByLabelText('Намерение'), { target: { value: 'Ретро блок' } });
    fireEvent.change(screen.getByLabelText('Дата'), { target: { value: '2026-06-24' } });
    fireEvent.change(screen.getByLabelText('Время'), { target: { value: '10:00' } });
    fireEvent.change(screen.getByLabelText('Своя длительность'), { target: { value: '37' } });
    fireEvent.change(screen.getByLabelText('Что сделал?'), { target: { value: 'Сделал' } });
    await user.click(screen.getByRole('button', { name: /сохранить блок/i }));

    await waitFor(() => {
      expect(logFocus).toHaveBeenCalledWith({
        task_id: null,
        project: null,
        intention: 'Ретро блок',
        logged_at: expect.any(String),
        duration_minutes: 37,
        accomplished_text: 'Сделал',
        distraction_text: null,
        next_step_text: null,
        focus_score: 4,
      });
    });
  });

  it('renders active focus mode without inline analytics and opens details', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getFocusState').mockResolvedValue({
      active_session: makeSession({
        status: 'active',
        intention: 'Write product spec',
        project: 'Lumi',
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
      project_breakdown: [{ project: 'Lumi', focus_seconds: 50 * 60, session_count: 1 }],
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
        project: null,
        intention: 'Session',
        planned_minutes: 45,
      });
    });
  });

  it('opens history details with clickable days, project split, and sessions', async () => {
    const user = userEvent.setup();
    const recentSession = makeSession({
      id: '77777777-7777-4777-8777-777777777777',
      project: 'QA Project',
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
      project_breakdown: [{ project: 'QA Project', focus_seconds: 39 * 60, session_count: 1 }],
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
      project_breakdown: [{ project: 'Lumi', focus_seconds: 6 * 3600, session_count: 10 }],
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
      project_breakdown: [{ project: 'Lumi', focus_seconds: 7 * 3600, session_count: 12 }],
    };
    vi.spyOn(api, 'getFocusState').mockResolvedValue(EMPTY_STATE);
    vi.spyOn(api, 'getFocusSummary').mockImplementation((period = 'week') =>
      Promise.resolve(period === 'month' ? monthSummary : SUMMARY),
    );
    vi.spyOn(api, 'listFocusSessions').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listTasks').mockResolvedValue(TASKS);

    renderFocusPage('en');

    await user.click(await screen.findByRole('button', { name: /month/i }));

    expect(await screen.findByText('146 sessions this month')).toBeInTheDocument();
    expect(screen.getByText('4.1 avg focus score')).toBeInTheDocument();
    expect(await screen.findAllByTestId('focus-day-bar')).toHaveLength(30);

    await user.click(screen.getByRole('button', { name: /2026-06-27: 7h 10m/i }));

    expect(await screen.findByText('Jun 27')).toBeInTheDocument();
    expect(screen.getByText('7h 10m')).toBeInTheDocument();
    expect(screen.getByText('9 sessions')).toBeInTheDocument();
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

    expect(await screen.findByText('Session history')).toBeInTheDocument();
    expect(screen.getByText('History session 8')).toBeInTheDocument();
  });

  it('opens session details instead of history when a history row is clicked', async () => {
    const user = userEvent.setup();
    const session = makeSession({
      intention: 'Clicked session',
      project: 'Lumi',
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
      expect(finish).toHaveBeenCalledWith(session.id, expect.objectContaining({ ended_at: expect.any(String) }));
    });
    expect(await screen.findByText('Session review')).toBeInTheDocument();
  });
});
