import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../../api/client';
import { WebLoginScreen } from './WebLoginScreen';

function renderLogin(path: string, queryClient = new QueryClient(), strict = false) {
  const content = (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <WebLoginScreen />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(strict ? <React.StrictMode>{content}</React.StrictMode> : content);
}

describe('WebLoginScreen', () => {
  it('shows the signed-out instructions when the URL has no nonce', () => {
    renderLogin('/web-login');
    expect(screen.getByText('Sign in through Telegram')).toBeInTheDocument();
    expect(screen.getByText(/Send \/web to Lumi/)).toBeInTheDocument();
  });

  it('strips the nonce before one StrictMode-safe exchange and clears prior identity state', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['tasks'], { private: 'old-user' });
    sessionStorage.setItem('lumi-realtime-last-id', '47');
    window.history.replaceState(null, '', '/#/web-login?nonce=strict-mode-nonce');
    const exchange = vi.spyOn(api, 'exchangeWebLogin').mockImplementation(async () => {
      expect(window.location.hash).toBe('#/web-login');
      return { authenticated: true };
    });

    renderLogin('/web-login?nonce=strict-mode-nonce', queryClient, true);

    expect(await screen.findByText('Signed in')).toBeInTheDocument();
    expect(exchange).toHaveBeenCalledOnce();
    expect(exchange).toHaveBeenCalledWith('strict-mode-nonce');
    expect(queryClient.getQueryData(['tasks'])).toBeUndefined();
    expect(sessionStorage.getItem('lumi-realtime-last-id')).toBeNull();
  });

  it('shows one safe error for an expired or replayed nonce', async () => {
    window.history.replaceState(null, '', '/#/web-login?nonce=expired-nonce');
    vi.spyOn(api, 'exchangeWebLogin').mockRejectedValue(
      new ApiError(401, 'invalid_or_expired_login', null),
    );

    renderLogin('/web-login?nonce=expired-nonce');

    await waitFor(() => expect(screen.getByText('This link expired or was already used')).toBeInTheDocument());
    expect(screen.getByText(/Each link works once/)).toBeInTheDocument();
  });

  it('checks a settled nonce with the server again instead of caching success', async () => {
    const exchange = vi.spyOn(api, 'exchangeWebLogin')
      .mockResolvedValueOnce({ authenticated: true })
      .mockRejectedValueOnce(new ApiError(401, 'invalid_or_expired_login', null));
    window.history.replaceState(null, '', '/#/web-login?nonce=replayed-nonce');

    const first = renderLogin('/web-login?nonce=replayed-nonce');
    expect(await screen.findByText('Signed in')).toBeInTheDocument();
    first.unmount();

    window.history.replaceState(null, '', '/#/web-login?nonce=replayed-nonce');
    renderLogin('/web-login?nonce=replayed-nonce');
    expect(await screen.findByText('This link expired or was already used')).toBeInTheDocument();
    expect(exchange).toHaveBeenCalledTimes(2);
  });

  it('clears the previous identity even if the route unmounts during exchange', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['tasks'], { private: 'old-user' });
    let finishExchange!: (value: { authenticated: true }) => void;
    vi.spyOn(api, 'exchangeWebLogin').mockReturnValue(new Promise((resolve) => {
      finishExchange = resolve;
    }));
    window.history.replaceState(null, '', '/#/web-login?nonce=route-change-nonce');

    const view = renderLogin('/web-login?nonce=route-change-nonce', queryClient);
    view.unmount();
    queryClient.setQueryData(['tasks'], { private: 'old-user-reloaded' });
    finishExchange({ authenticated: true });

    await waitFor(() => expect(queryClient.getQueryData(['tasks'])).toBeUndefined());
  });

  it('clears identity refetched after unmount when exchange transport fails', async () => {
    const queryClient = new QueryClient();
    let failExchange!: (reason: Error) => void;
    vi.spyOn(api, 'exchangeWebLogin').mockReturnValue(new Promise((_, reject) => {
      failExchange = reject;
    }));
    window.history.replaceState(null, '', '/#/web-login?nonce=failed-route-change');

    const view = renderLogin('/web-login?nonce=failed-route-change', queryClient);
    view.unmount();
    queryClient.setQueryData(['tasks'], { private: 'old-user-reloaded' });
    failExchange(new Error('body read failed'));

    await waitFor(() => expect(queryClient.getQueryData(['tasks'])).toBeUndefined());
  });
});
