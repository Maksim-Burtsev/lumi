import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type {
  AgentRunsResponse,
  AutomationsResponse,
  CalendarEventsResponse,
  InboxSummaryResponse,
  MemoriesResponse,
  NewsDigestsResponse,
  NewsTopicsResponse,
  SettingsResponse,
  TasksResponse,
  User,
} from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import AgentRunsPage from './AgentRunsPage';
import AutomationsPage from './AutomationsPage';
import CalendarPage from './CalendarPage';
import InboxPage from './InboxPage';
import MemoryPage from './MemoryPage';
import NewsPage from './NewsPage';
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

  it('localizes News page static UI', async () => {
    vi.spyOn(api, 'listNewsTopics').mockResolvedValue({ items: [] } satisfies NewsTopicsResponse);
    vi.spyOn(api, 'listNewsDigests').mockResolvedValue({ items: [] } satisfies NewsDigestsResponse);

    renderWithProviders(<NewsPage />);

    expect(await screen.findByText('Build digest')).toBeInTheDocument();
    expect(screen.getAllByText('Add topic')).not.toHaveLength(0);
    expect(await screen.findByText('No topics yet')).toBeInTheDocument();
    expect(screen.queryByText('Собрать дайджест')).not.toBeInTheDocument();
  });

  it('localizes Inbox page static UI', async () => {
    vi.spyOn(api, 'getInboxSummary').mockResolvedValue({
      connected: false,
      last_triage_at: null,
      counts: { needs_reply: 0, waiting_for_me: 0, decision_needed: 0, fyi: 0, newsletter: 0, invoice_document: 0, ignore: 0, unknown: 0 },
      threads: [],
    } satisfies InboxSummaryResponse);

    renderWithProviders(<InboxPage />);

    expect(await screen.findByText('Gmail is not connected')).toBeInTheDocument();
    expect(screen.getByText('Open settings')).toBeInTheDocument();
    expect(screen.queryByText('Gmail не подключен')).not.toBeInTheDocument();
  });

  it('localizes Memory page static UI', async () => {
    vi.spyOn(api, 'listMemories').mockResolvedValue({ items: [] } satisfies MemoriesResponse);

    renderWithProviders(<MemoryPage />);

    expect(await screen.findByText('All')).toBeInTheDocument();
    expect(await screen.findByText('Lumi has not remembered anything yet')).toBeInTheDocument();
    expect(screen.queryByText('Все')).not.toBeInTheDocument();
  });

  it('localizes Automations page static UI', async () => {
    vi.spyOn(api, 'listAutomations').mockResolvedValue({ items: [] } satisfies AutomationsResponse);

    renderWithProviders(<AutomationsPage />);

    expect(await screen.findByText('New automation')).toBeInTheDocument();
    expect(await screen.findByText('No automations yet')).toBeInTheDocument();
    expect(screen.queryByText('Новая автоматизация')).not.toBeInTheDocument();
  });

  it('localizes Agent runs page static UI', async () => {
    vi.spyOn(api, 'listAgentRuns').mockResolvedValue({ items: [] } satisfies AgentRunsResponse);

    renderWithProviders(<AgentRunsPage />);

    expect(await screen.findByText('No agent runs yet')).toBeInTheDocument();
    expect(screen.queryByText('Запусков пока не было')).not.toBeInTheDocument();
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

  it('localizes Calendar empty schedule marker in Russian', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue({
      items: [],
      sync: { connected: false, last_sync_at: null, stale: false, refresh_queued: false },
    } satisfies CalendarEventsResponse);

    renderWithProviders(<CalendarPage />, 'ru');

    await waitFor(() => expect(screen.getByText('Синхронизировать')).toBeInTheDocument());
    expect(screen.getByText('Нет запланированных встреч')).toBeInTheDocument();
    expect(screen.getByText('08:00')).toBeInTheDocument();
    expect(screen.queryByText('No meetings scheduled')).not.toBeInTheDocument();
  });

  it('opens English automation sheet', async () => {
    vi.spyOn(api, 'listAutomations').mockResolvedValue({ items: [] } satisfies AutomationsResponse);

    renderWithProviders(<AutomationsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'New automation' }));

    expect(await screen.findByRole('dialog', { name: 'New automation' })).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('When to run')).toBeInTheDocument();
    expect(screen.queryByText('Тип')).not.toBeInTheDocument();
  });
});
