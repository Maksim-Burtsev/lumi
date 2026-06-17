import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { MeResponse, SettingsResponse, User } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import SettingsPage from './SettingsPage';

const TIMEZONES_RESPONSE = {
  items: [
    { id: 'Asia/Yerevan' },
    { id: 'America/St_Johns' },
    { id: 'Asia/Kathmandu' },
    { id: 'Pacific/Chatham' },
    { id: 'UTC' },
  ],
};

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

function renderSettingsPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    </QueryClientProvider>,
  );

  return queryClient;
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe('SettingsPage language settings', () => {
  it('lets the user change app language and bot reply mode', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => ({
      user: makeUser({
        locale: input.locale ?? 'en',
        settings: {
          reply_language_mode: input.reply_language_mode ?? 'auto',
          locale_source: input.locale ? 'manual' : 'telegram',
        },
      }),
    }));

    renderSettingsPage();

    expect(await screen.findByText('App language')).toBeInTheDocument();
    await user.selectOptions(screen.getByDisplayValue('English'), 'ru');

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ locale: 'ru' });
    });

    await user.selectOptions(screen.getByDisplayValue('Auto: match each message'), 'app_locale');

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ reply_language_mode: 'app_locale' });
    });
  });

  it('lets the user search and select a rare timezone', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => ({
      user: makeUser({ timezone: input.timezone ?? 'Asia/Yerevan' }),
    }));

    renderSettingsPage();

    await user.click(await screen.findByRole('button', { name: /change time zone/i }));
    await user.type(screen.getByPlaceholderText('Search city or time zone'), 'Chatham');
    await user.click(await screen.findByRole('button', { name: /Pacific\/Chatham/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ timezone: 'Pacific/Chatham' });
    });
  });
});
