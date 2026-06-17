import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import type { MeResponse, SettingsResponse, User } from '../../api/types';
import { ToastProvider } from '../ui/Toast';
import { TimezoneMismatchPrompt } from './TimezoneMismatchPrompt';

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'Asia/Yerevan',
    locale: 'en',
    settings: { reply_language_mode: 'auto' },
    created_at: '2026-06-12T00:00:00Z',
    last_seen_at: null,
    ...overrides,
  };
}

function makeSettingsResponse(user: User = makeUser()): SettingsResponse {
  return {
    user,
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

function renderPrompt() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TimezoneMismatchPrompt />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  vi.spyOn(Intl, 'DateTimeFormat').mockImplementation((() => ({
    resolvedOptions: () => ({ timeZone: 'Pacific/Chatham' }),
  })) as unknown as typeof Intl.DateTimeFormat);
});

describe('TimezoneMismatchPrompt', () => {
  it('shows a mismatch prompt without silently patching the profile', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    const patchSpy = vi.spyOn(api, 'patchSettings').mockResolvedValue({ user: makeUser() });

    renderPrompt();

    expect(await screen.findByText(/Detected time zone/i)).toBeInTheDocument();
    expect(screen.getByText(/Pacific\/Chatham/i)).toBeInTheDocument();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it('applies detected timezone only after the user confirms', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => ({
      user: makeUser({ timezone: input.timezone ?? 'Asia/Yerevan' }),
    }));

    renderPrompt();

    await user.click(await screen.findByRole('button', { name: /use detected/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ timezone: 'Pacific/Chatham' });
    });
  });

  it('suppresses the same mismatch after the user keeps current timezone', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'patchSettings').mockResolvedValue({ user: makeUser() });

    renderPrompt();
    await user.click(await screen.findByRole('button', { name: /keep current/i }));

    await waitFor(() => {
      expect(screen.queryByText(/Detected time zone/i)).not.toBeInTheDocument();
    });
    expect(localStorage.getItem('lumi-tz-dismissed:Asia/Yerevan:Pacific/Chatham')).toBe('1');
  });
});
