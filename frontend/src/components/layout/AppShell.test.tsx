import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppShell } from './AppShell';

const { getInitDataMock } = vi.hoisted(() => ({ getInitDataMock: vi.fn(() => '') }));

vi.mock('../../lib/useAppLocale', () => ({
  useAppLocale: () => 'en',
}));

vi.mock('../focus/FocusTimerCoordinator', () => ({
  FocusTimerCoordinator: () => <div data-testid="focus-timer-coordinator" />,
}));

vi.mock('../../telegram/webapp', () => ({
  getInitData: getInitDataMock,
}));

vi.mock('./TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <header>{title}</header>,
}));

vi.mock('./BottomNav', () => ({
  BottomNav: ({ standalone }: { standalone: boolean }) => (
    <nav aria-label="Bottom navigation" data-standalone={String(standalone)} />
  ),
}));

vi.mock('./DesktopSidebar', () => ({
  DesktopSidebar: () => <aside aria-label="Desktop navigation" />,
}));

describe('AppShell', () => {
  it('keeps the focus coordinator mounted and preserves timezone prompt space', () => {
    getInitDataMock.mockReturnValue('');
    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <AppShell onLogout={vi.fn()}>
          <p>Route content</p>
        </AppShell>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('focus-timer-coordinator')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveClass('app-content');
    expect(screen.getByLabelText('Desktop navigation')).toBeInTheDocument();
    expect(screen.getByLabelText('Bottom navigation')).toHaveAttribute('data-standalone', 'true');
  });

  it('does not enable the desktop shell when Telegram initData is present', () => {
    getInitDataMock.mockReturnValue('signed-init-data');
    render(
      <MemoryRouter initialEntries={['/sessions']}>
        <AppShell onLogout={vi.fn()}>
          <p>Route content</p>
        </AppShell>
      </MemoryRouter>,
    );

    expect(screen.queryByLabelText('Desktop navigation')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Bottom navigation')).toHaveAttribute('data-standalone', 'false');
  });
});
