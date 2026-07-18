import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { CalendarEvent, SettingsResponse } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import CalendarPage from './CalendarPage';

function settings(): SettingsResponse {
  return {
    user: {
      id: '11111111-1111-4111-8111-111111111111',
      telegram_user_id: 777000,
      username: 'tester',
      first_name: 'Test',
      last_name: 'User',
      timezone: 'Asia/Yerevan',
      locale: 'en',
      settings: {},
      created_at: '2026-07-18T00:00:00Z',
      last_seen_at: null,
    },
    llm: { provider: 'mock', model: 'mock-1', configured: true },
    google: {
      status: 'disconnected',
      scopes: [],
      last_sync_at: null,
      last_error: null,
      gmail_available: false,
      calendar_available: false,
    },
    yandex: { status: 'disconnected', username: null, last_sync_at: null, last_error: null },
    flags: { store_email_bodies: false, store_llm_debug_payloads: false, dev_auth: true },
    app: { public_url: null, env: 'local' },
  };
}

function workBlock(): CalendarEvent {
  const start = new Date();
  start.setHours(10, 0, 0, 0);
  const end = new Date(start.getTime() + 25 * 60_000);
  return {
    id: '22222222-2222-4222-8222-222222222222',
    kind: 'work_block',
    source_task_id: '33333333-3333-4333-8333-333333333333',
    title: 'Ship calendar bridge',
    description: null,
    start_at: start.toISOString(),
    end_at: end.toISOString(),
    all_day: false,
    busy: true,
    status: 'confirmed',
    source: 'internal',
    created_by: 'planner',
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
  };
}

describe('CalendarPage WorkBlock integration', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts a linked focus cycle from a confirmed WorkBlock', async () => {
    const user = userEvent.setup();
    const event = workBlock();
    vi.spyOn(api, 'getSettings').mockResolvedValue(settings());
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue({ items: [event] });
    const start = vi.spyOn(api, 'startFocusSession').mockResolvedValue({
      session: {
        id: '44444444-4444-4444-8444-444444444444',
        status: 'active',
        planned_event_id: event.id,
        task: null,
        project_id: null,
        project_name: null,
        local_date: event.start_at.slice(0, 10),
        intention: event.title,
        planned_minutes: 25,
        started_at: new Date().toISOString(),
        target_end_at: new Date(Date.now() + 25 * 60_000).toISOString(),
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
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/calendar']}>
            <Routes>
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/sessions" element={<p>Sessions route</p>} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole('button', { name: /WorkBlock: Ship calendar bridge/i }));
    await user.click(await screen.findByRole('button', { name: /start focus/i }));

    await waitFor(() => expect(start).toHaveBeenCalledWith({
      planned_event_id: event.id,
      intention: event.title,
      planned_minutes: 25,
      break_minutes: 5,
    }));
    expect(await screen.findByText('Sessions route')).toBeInTheDocument();
  });
});
