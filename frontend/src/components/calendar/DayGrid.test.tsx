import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import type { CalendarEvent, SettingsResponse, User } from '../../api/types';
import { DayGrid } from './DayGrid';

function makeUser(): User {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'Asia/Yerevan',
    locale: 'ru',
    settings: { reply_language_mode: 'auto', time_format: '12h' },
    created_at: '2026-06-12T00:00:00Z',
    last_seen_at: null,
  };
}

function makeSettingsResponse(): SettingsResponse {
  return {
    user: makeUser(),
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

function renderGrid(event: CalendarEvent) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(['settings'], makeSettingsResponse());
  render(
    <QueryClientProvider client={queryClient}>
      <DayGrid
        events={[event]}
        dayStart={new Date('2026-06-16T20:00:00Z')}
        locale="ru"
        onEmptyTap={vi.fn()}
        onEventTap={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('DayGrid time format', () => {
  it('formats hour axis and event ranges with the selected 12-hour format', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());

    renderGrid({
      id: 'event-1',
      title: 'QA time format',
      description: null,
      start_at: '2026-06-17T10:30:00Z',
      end_at: '2026-06-17T11:15:00Z',
      all_day: false,
      busy: true,
      status: 'confirmed',
      source: 'internal',
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
      private_note: null,
      private_note_summary: null,
      private_note_summary_status: null,
      private_note_updated_at: null,
      private_note_summary_updated_at: null,
    });

    expect(await screen.findByText('8:00 AM')).toBeInTheDocument();
    expect(screen.queryByText('08:00')).not.toBeInTheDocument();
    expect(screen.getByText('2:30 PM–3:15 PM')).toBeInTheDocument();
  });
});
