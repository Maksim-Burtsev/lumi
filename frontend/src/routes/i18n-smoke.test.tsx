import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type {
  CalendarEventsResponse,
  SettingsResponse,
  TasksResponse,
  User,
} from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import CalendarPage from './CalendarPage';
import TasksPage from './TasksPage';

function makeUser(locale = 'en'): User {
  return {
    id: '33333333-3333-4333-8333-333333333333',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'UTC',
    locale,
    settings: { reply_language_mode: 'auto', time_format: '24h' },
    created_at: '2026-06-12T00:00:00Z',
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

function renderWithProviders(ui: ReactElement, locale = 'en') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettings(locale));
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
          {ui}
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('Mini App English UI smoke', () => {
  it('localizes Tasks page static UI', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [] } satisfies TasksResponse);

    renderWithProviders(<TasksPage />);

    expect(await screen.findByPlaceholderText('Search tasks')).toBeInTheDocument();
    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(await screen.findByText('No tasks for today')).toBeInTheDocument();
    expect(screen.queryByText('Сегодня')).not.toBeInTheDocument();
  });

  it('localizes Calendar page static UI', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue({
      items: [],
      sync: { connected: false, last_sync_at: null, stale: false, refresh_queued: false },
    } satisfies CalendarEventsResponse);

    renderWithProviders(<CalendarPage />);

    expect(await screen.findByText('Sync')).toBeInTheDocument();
    expect(screen.getByText('Plan day')).toBeInTheDocument();
    expect(await screen.findByText('No meetings scheduled')).toBeInTheDocument();
    expect(await screen.findByText('08:00')).toBeInTheDocument();
    expect(screen.queryByText('Free day')).not.toBeInTheDocument();
    expect(screen.queryByText('Синхронизировать')).not.toBeInTheDocument();
  });

  it('keeps Calendar static UI in English even when stored user locale is Russian', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue({
      items: [],
      sync: { connected: false, last_sync_at: null, stale: false, refresh_queued: false },
    } satisfies CalendarEventsResponse);

    renderWithProviders(<CalendarPage />, 'ru');

    await waitFor(() => expect(screen.getByText('Sync')).toBeInTheDocument());
    expect(await screen.findByText('No meetings scheduled')).toBeInTheDocument();
    expect(await screen.findByText('08:00')).toBeInTheDocument();
    expect(screen.queryByText('Синхронизировать')).not.toBeInTheDocument();
    expect(screen.queryByText('Нет запланированных встреч')).not.toBeInTheDocument();
  });

});
