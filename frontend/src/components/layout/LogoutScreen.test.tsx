import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import { hasPendingWebLogout, markPendingWebLogout } from '../../api/webAuth';
import { LogoutScreen } from './LogoutScreen';

vi.mock('./WebLoginScreen', () => ({
  WebLoginScreen: () => <div>Web login resumed</div>,
}));

function renderLogout(path = '/logout', strict = false) {
  const queryClient = new QueryClient();
  queryClient.setQueryData(['tasks'], { private: 'old-user' });
  const content = (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <LogoutScreen />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return {
    queryClient,
    ...render(strict ? <React.StrictMode>{content}</React.StrictMode> : content),
  };
}

describe('LogoutScreen', () => {
  it('runs one StrictMode-safe revoke and clears private client state', async () => {
    markPendingWebLogout();
    const logout = vi.spyOn(api, 'logoutWebSession').mockResolvedValue({ authenticated: false });

    const { queryClient } = renderLogout('/logout', true);

    expect(await screen.findByText('Signed out')).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
    expect(queryClient.getQueryData(['tasks'])).toBeUndefined();
    expect(hasPendingWebLogout()).toBe(false);
  });

  it('keeps private UI hidden and the recovery marker until retry succeeds', async () => {
    markPendingWebLogout();
    const logout = vi.spyOn(api, 'logoutWebSession')
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ authenticated: false });

    const { queryClient } = renderLogout();

    expect(await screen.findByText('Logout is not confirmed')).toBeInTheDocument();
    expect(queryClient.getQueryData(['tasks'])).toBeUndefined();
    expect(hasPendingWebLogout()).toBe(true);

    await userEvent.click(screen.getByRole('button', { name: 'Retry logout' }));
    expect(await screen.findByText('Signed out')).toBeInTheDocument();
    expect(logout).toHaveBeenCalledTimes(2);
    expect(hasPendingWebLogout()).toBe(false);
  });

  it('finishes a pending revoke before resuming a new magic link', async () => {
    markPendingWebLogout();
    vi.spyOn(api, 'logoutWebSession').mockResolvedValue({ authenticated: false });

    renderLogout('/web-login?nonce=fresh');

    expect(await screen.findByText('Web login resumed')).toBeInTheDocument();
  });
});
