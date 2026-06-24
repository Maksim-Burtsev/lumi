import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { FocusStateResponse, FocusSummaryResponse, TasksResponse } from '../api/types';
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
  daily_activity: [],
  project_breakdown: [],
  next_steps: [],
};

function renderFocusPage() {
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
  it('keeps the dial progress proportional to elapsed time', () => {
    const started = new Date('2026-06-24T10:00:00Z').getTime();
    const metrics = getDialMetrics({
      started,
      target: started + 25 * 60_000,
      now: started + 30_000,
    });

    expect(metrics.progress).toBeCloseTo(0.02, 3);
  });

  it('starts a task-linked session and shows the floating dial', async () => {
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

    renderFocusPage();

    await user.click(await screen.findByRole('button', { name: /начать фокус/i }));
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
    expect(screen.getByLabelText('Прогресс фокус-сессии')).toBeInTheDocument();
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

    renderFocusPage();

    await user.click(await screen.findByRole('button', { name: /начать фокус/i }));
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

    renderFocusPage();

    await user.click(await screen.findByRole('button', { name: /залогировать/i }));
    fireEvent.change(screen.getByLabelText('Намерение'), { target: { value: 'Ретро блок' } });
    fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2026-06-24T10:00' } });
    fireEvent.change(screen.getByLabelText('Длительность, минут'), { target: { value: '37' } });
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
});
