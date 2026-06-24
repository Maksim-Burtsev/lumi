import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { FocusStateResponse, FocusSummaryResponse, TasksResponse } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import FocusPage from './FocusPage';

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
    await user.type(screen.getByLabelText('Намерение'), 'Написать черновик спецификации');
    await user.selectOptions(screen.getByLabelText('Задача'), TASKS.items[0].id);
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
});
