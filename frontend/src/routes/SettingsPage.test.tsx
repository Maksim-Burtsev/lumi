import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { MeResponse, SettingsResponse, ThemeMode, User } from '../api/types';
import { ToastProvider } from '../components/ui/Toast';
import SettingsPage from './SettingsPage';

const TIMEZONES_RESPONSE = {
  items: [
    { id: 'Asia/Yerevan' },
    { id: 'America/St_Johns' },
    { id: 'America/New_York' },
    { id: 'America/Chicago' },
    { id: 'America/Denver' },
    { id: 'America/Los_Angeles' },
    { id: 'America/Phoenix' },
    { id: 'America/Anchorage' },
    { id: 'Pacific/Honolulu' },
    { id: 'America/Puerto_Rico' },
    { id: 'Pacific/Guam' },
    { id: 'Europe/London' },
    { id: 'Europe/Berlin' },
    { id: 'Europe/Paris' },
    { id: 'Asia/Bangkok' },
    { id: 'Asia/Makassar' },
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
    settings: { reply_language_mode: 'auto', time_format: 'auto', theme_mode: 'telegram' },
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
          time_format: '24h',
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

  it('lets the user search timezones by country and common place names', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);

    renderSettingsPage();

    await user.click(await screen.findByRole('button', { name: /change time zone/i }));
    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'USA' } });
    expect(await screen.findByRole('button', { name: /Pacific Time/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /America\/New York/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Africa\/Lusaka/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Asia\/Jerusalem/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'US San' } });
    expect(await screen.findByRole('button', { name: /San Francisco.*America\/Los Angeles/i })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'Germany' } });
    expect(await screen.findByRole('button', { name: /Central European Time.*Europe\/Berlin/i })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'Thailand' } });
    expect(await screen.findByRole('button', { name: /Asia\/Bangkok/i })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'Bali' } });
    expect(await screen.findByRole('button', { name: /Asia\/Makassar/i })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Search city or time zone'), { target: { value: 'zzzz impossible' } });
    expect(await screen.findByText(/Try a city, country, or abbreviation/i)).toBeInTheDocument();
  });

  it('renders regional settings as a list and resolves legacy auto time format', async () => {
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);

    renderSettingsPage();

    expect(await screen.findByText('Regional settings')).toBeInTheDocument();
    const timeFormatSelect = screen.getByLabelText('Time format');
    expect(timeFormatSelect).toHaveDisplayValue('12-hour');
    expect(within(timeFormatSelect).queryByRole('option', { name: 'Automatic' })).not.toBeInTheDocument();
    expect(within(timeFormatSelect).getByRole('option', { name: '12-hour' })).toBeInTheDocument();
    expect(within(timeFormatSelect).getByRole('option', { name: '24-hour' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change time zone/i })).toBeInTheDocument();
  });

  it('lets the user switch to a 24-hour time format', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => ({
      user: makeUser({
        settings: {
          reply_language_mode: 'auto',
          time_format: input.time_format ?? 'auto',
        },
      }),
    }));

    renderSettingsPage();

    expect(await screen.findByText('Time format')).toBeInTheDocument();
    const timeFormatSelect = screen.getByLabelText('Time format');
    expect(timeFormatSelect).toHaveDisplayValue('12-hour');
    await user.selectOptions(timeFormatSelect, '24h');

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ time_format: '24h' });
    });
  });

  it('lets the user force the dark theme from appearance settings', async () => {
    const user = userEvent.setup();
    let savedThemeMode: ThemeMode = 'telegram';
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockImplementation(async () => makeSettingsResponse(makeUser({
      settings: {
        reply_language_mode: 'auto',
        time_format: 'auto',
        theme_mode: savedThemeMode,
      },
    })));
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => {
      savedThemeMode = input.theme_mode ?? savedThemeMode;
      return {
        user: makeUser({
          settings: {
            reply_language_mode: 'auto',
            time_format: 'auto',
            theme_mode: savedThemeMode,
          },
        }),
      };
    });

    renderSettingsPage();

    expect(await screen.findByText('Appearance')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Theme' })).not.toBeInTheDocument();
    expect(screen.queryByRole('listbox', { name: 'Theme' })).not.toBeInTheDocument();
    const themeSelect = screen.getByRole('combobox', { name: 'Theme' });
    expect(themeSelect).toHaveDisplayValue('Telegram');
    await user.selectOptions(themeSelect, 'dark');

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith({ theme_mode: 'dark' });
    });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(screen.getByRole('combobox', { name: 'Theme' })).toHaveDisplayValue('Dark');
    expect(screen.queryByText('Theme saved')).not.toBeInTheDocument();
  });

  it('keeps the selected theme visible while saving', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    let resolvePatch: (response: MeResponse) => void = () => {};
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(
      () => new Promise<MeResponse>((resolve) => {
        resolvePatch = resolve;
      }),
    );

    renderSettingsPage();

    expect(await screen.findByText('Appearance')).toBeInTheDocument();
    const themeSelect = screen.getByRole('combobox', { name: 'Theme' });
    expect(themeSelect).toHaveDisplayValue('Telegram');
    await user.selectOptions(themeSelect, 'dark');

    expect(themeSelect).toHaveDisplayValue('Dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(patchSpy).toHaveBeenCalledWith({ theme_mode: 'dark' });

    resolvePatch({
      user: makeUser({
        settings: {
          reply_language_mode: 'auto',
          time_format: 'auto',
          theme_mode: 'dark',
        },
      }),
    });
    await waitFor(() => expect(themeSelect).toHaveDisplayValue('Dark'));
    expect(screen.queryByText('Theme saved')).not.toBeInTheDocument();
  });

  it('keeps the latest selected theme when saves resolve out of order', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse());
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    const resolvers: Array<(response: MeResponse) => void> = [];
    const patchSpy = vi.spyOn(api, 'patchSettings').mockImplementation(
      () => new Promise<MeResponse>((resolve) => {
        resolvers.push(resolve);
      }),
    );

    renderSettingsPage();

    expect(await screen.findByText('Appearance')).toBeInTheDocument();
    const themeSelect = screen.getByRole('combobox', { name: 'Theme' });
    await user.selectOptions(themeSelect, 'dark');
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith({ theme_mode: 'dark' }));
    expect(themeSelect).toHaveDisplayValue('Dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    await user.selectOptions(themeSelect, 'light');
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith({ theme_mode: 'light' }));
    expect(themeSelect).toHaveDisplayValue('Light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    resolvers[0]({
      user: makeUser({
        settings: {
          reply_language_mode: 'auto',
          time_format: 'auto',
          theme_mode: 'dark',
        },
      }),
    });
    await waitFor(() => expect(themeSelect).toHaveDisplayValue('Light'));
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    resolvers[1]({
      user: makeUser({
        settings: {
          reply_language_mode: 'auto',
          time_format: 'auto',
          theme_mode: 'light',
        },
      }),
    });
    await waitFor(() => expect(themeSelect).toHaveDisplayValue('Light'));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(screen.queryByText('Theme saved')).not.toBeInTheDocument();
  });

  it('shows work rhythm controls with five-minute short windows', async () => {
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse(makeUser({
      locale: 'ru',
      settings: {
        reply_language_mode: 'auto',
        time_format: '24h',
        planning: {
          work_days: [0, 1, 2, 3, 4],
          work_hours: { start: '09:00', end: '19:00' },
          quiet_hours: { start: '21:00', end: '09:00' },
          proactive_level: 'balanced',
          micro_slots_enabled: true,
          micro_slots: { min_minutes: 5 },
          auto_enrich_tasks: true,
          suggestion_notifications: 'important',
        },
      },
    })));
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);

    renderSettingsPage();

    expect(await screen.findByText('Рабочий ритм')).toBeInTheDocument();
    expect(screen.getByText('Рабочие дни')).toBeInTheDocument();
    expect(screen.getByText('Рабочие часы')).toBeInTheDocument();
    expect(screen.getByText('Тихие часы')).toBeInTheDocument();
    expect(screen.getByText('Проактивность Lumi')).toBeInTheDocument();
    expect(screen.getByText('Показывать задачи для свободных окон от 5 минут')).toBeInTheDocument();
  });

  it('shows a distinct description for each Lumi proactivity mode', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'Lumi', env: 'local', version: '0.1.0' });
    vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettingsResponse(makeUser({
      locale: 'en',
      settings: {
        reply_language_mode: 'auto',
        time_format: '24h',
        planning: {
          work_days: [0, 1, 2, 3, 4],
          work_hours: { start: '09:00', end: '19:00' },
          quiet_hours: { start: '21:00', end: '09:00' },
          proactive_level: 'balanced',
          micro_slots_enabled: true,
          micro_slots: { min_minutes: 5 },
          auto_enrich_tasks: true,
          suggestion_notifications: 'important',
        },
      },
    })));
    vi.spyOn(api, 'getTimezones').mockResolvedValue(TIMEZONES_RESPONSE);
    vi.spyOn(api, 'patchSettings').mockImplementation(async (input): Promise<MeResponse> => ({
      user: makeUser({
        locale: 'en',
        settings: {
          reply_language_mode: 'auto',
          time_format: '24h',
          planning: {
            ...((makeUser().settings.planning as Record<string, unknown>) ?? {}),
            proactive_level: input.settings?.planning && typeof input.settings.planning === 'object'
              ? (input.settings.planning as { proactive_level?: string }).proactive_level
              : 'balanced',
          },
        },
      }),
    }));

    renderSettingsPage();

    expect(await screen.findByText('Regular checks while you are active.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Calm' }));
    expect(await screen.findByText('Fewer checks and fewer nudges.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Active' }));
    expect(await screen.findByText('Faster refresh after calendar or task changes.')).toBeInTheDocument();
  });
});
