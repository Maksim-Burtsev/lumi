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
