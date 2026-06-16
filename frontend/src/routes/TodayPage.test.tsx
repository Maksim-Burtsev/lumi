import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { ConfirmationDecisionResponse, TodayResponse } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import TodayPage from './TodayPage';

const firstConfirmationId = '11111111-1111-4111-8111-111111111111';
const secondConfirmationId = '22222222-2222-4222-8222-222222222222';

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

function renderTodayPage() {
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
