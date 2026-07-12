import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { TopBar } from './TopBar';

vi.mock('../../api/hooks', () => ({
  useHealth: () => ({
    isPending: false,
    isError: false,
    data: { env: 'test', version: '0.1.0' },
  }),
}));

vi.mock('../../lib/useAppLocale', () => ({
  useAppLocale: () => 'en',
}));

describe('TopBar settings navigation', () => {
  it('exposes Settings as an accessible top-level link', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <TopBar title="Today" />
      </MemoryRouter>,
    );

    const settings = screen.getByRole('link', { name: 'Settings' });
    expect(settings).toHaveAttribute('href', '/settings');
    expect(settings).not.toHaveAttribute('aria-current');
  });

  it('marks Settings as current on the settings page', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <TopBar title="Settings" />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('aria-current', 'page');
  });
});
