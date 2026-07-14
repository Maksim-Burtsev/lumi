import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DesktopSidebar } from './DesktopSidebar';

vi.mock('../../api/hooks', () => ({
  useHealth: () => ({ isPending: false, isError: false, data: { env: 'test', version: '1' } }),
}));

vi.mock('../../lib/useAppLocale', () => ({
  useAppLocale: () => 'en',
}));

describe('DesktopSidebar', () => {
  it('renders the product areas, Settings, and one alias-aware active link', () => {
    render(
      <MemoryRouter initialEntries={['/focus']}>
        <DesktopSidebar loggingOut={false} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Today',
      'Tasks',
      'Sessions',
      'Calendar',
      'Settings',
    ]);
    expect(screen.getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Sessions' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Today' })).not.toHaveAttribute('aria-current');
  });

  it('runs standalone logout from the sidebar', async () => {
    const onLogout = vi.fn();
    render(
      <MemoryRouter initialEntries={['/']}>
        <DesktopSidebar loggingOut={false} onLogout={onLogout} />
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }));
    expect(onLogout).toHaveBeenCalledOnce();
  });

  it('hides web-session logout for local dev auth', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <DesktopSidebar loggingOut={false} onLogout={vi.fn()} showLogout={false} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('button', { name: 'Log out' })).not.toBeInTheDocument();
  });
});
