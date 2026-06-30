import { StrictMode, useState } from 'react';
import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { SettingsResponse } from '../../api/types';
import { Sheet } from './Sheet';

function setWindowScrollY(value: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value });
}

function SheetHarness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Decision">
        <p>Sheet body</p>
      </Sheet>
    </>
  );
}

function makeSettings(): SettingsResponse {
  return {
    user: {
      id: '33333333-3333-4333-8333-333333333333',
      telegram_user_id: 777000,
      username: 'tester',
      first_name: 'Test',
      last_name: 'User',
      timezone: 'UTC',
      locale: 'ru',
      settings: { reply_language_mode: 'auto', time_format: '24h' },
      created_at: '2026-06-12T00:00:00Z',
      last_seen_at: null,
    },
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

function renderWithSettings(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  queryClient.setQueryData(['settings'], makeSettings());
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('Sheet scroll lock', () => {
  it('locks the body at the current scroll position and restores it on close', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    setWindowScrollY(420);
    window.scrollTo = scrollTo;

    renderWithSettings(<SheetHarness />);

    expect(screen.getByRole('dialog', { name: 'Decision' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-420px');
    expect(document.body.style.width).toBe('100%');

    await user.click(screen.getByRole('button', { name: 'Close' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.body.style.position).toBe('');
      expect(document.body.style.top).toBe('');
      expect(scrollTo).toHaveBeenCalledWith(0, 420);
    });
  });

  it('restores scroll once when mounted under StrictMode', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    setWindowScrollY(260);
    window.scrollTo = scrollTo;

    renderWithSettings(
      <StrictMode>
        <SheetHarness />
      </StrictMode>,
    );

    expect(screen.getByRole('dialog', { name: 'Decision' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Close' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    });
    expect(scrollTo).toHaveBeenLastCalledWith(0, 260);
  });
});
