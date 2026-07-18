import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, UNAUTHORIZED_EVENT } from './client';

vi.mock('../telegram/webapp', () => ({
  getInitData: () => '',
}));

afterEach(() => {
  document.cookie = 'lumi_web_csrf=; Max-Age=0; path=/';
  vi.unstubAllGlobals();
});

describe('standalone web auth client', () => {
  it('exchanges a nonce with same-origin credentials and no token storage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ authenticated: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.exchangeWebLogin('one-time-nonce');

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/web/exchange', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      body: JSON.stringify({ nonce: 'one-time-nonce' }),
    }));
    expect(localStorage.getItem('lumi_web_session')).toBeNull();
  });

  it('does not publish global unauthorized state for a rejected exchange', async () => {
    const unauthorized = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, unauthorized);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'invalid_or_expired_login' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ));

    await expect(api.exchangeWebLogin('expired')).rejects.toMatchObject({
      status: 401,
      error: 'invalid_or_expired_login',
    });
    expect(unauthorized).not.toHaveBeenCalled();
    window.removeEventListener(UNAUTHORIZED_EVENT, unauthorized);
  });

  it('sends the readable CSRF cookie when logging out', async () => {
    document.cookie = 'lumi_web_csrf=csrf-value; path=/';
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ authenticated: false }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.logoutWebSession();

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('same-origin');
    expect(init.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-value' });
  });
});

describe('workday planning client', () => {
  it('posts the selected plan-day mode and optional idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ run_id: 'run-1', status: 'queued' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await api.planDay({ mode: 'replan', request_id: 'request-1' });

    expect(fetchMock).toHaveBeenCalledWith('/api/calendar/plan-day', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ mode: 'replan', request_id: 'request-1' }),
    }));
  });
});

describe('focus insights client', () => {
  it('uses the bounded list and explicit try/dismiss endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(
      JSON.stringify({ items: [], insight: {} }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await api.getFocusInsights(3);
    await api.tryFocusInsight('insight-1');
    await api.dismissFocusInsight('insight-1');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/focus/insights?limit=3', expect.objectContaining({
      method: 'GET',
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/focus/insights/insight-1/try', expect.objectContaining({
      method: 'POST',
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/focus/insights/insight-1/dismiss', expect.objectContaining({
      method: 'POST',
    }));
  });
});
