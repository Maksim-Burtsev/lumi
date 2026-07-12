import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppShell } from './AppShell';

vi.mock('../../lib/useAppLocale', () => ({
  useAppLocale: () => 'en',
}));

vi.mock('../focus/FocusTimerCoordinator', () => ({
  FocusTimerCoordinator: () => <div data-testid="focus-timer-coordinator" />,
}));

vi.mock('./TopBar', () => ({
  TopBar: ({ title }: { title: string }) => <header>{title}</header>,
}));

vi.mock('./BottomNav', () => ({
  BottomNav: () => <nav aria-label="Bottom navigation" />,
}));

describe('AppShell', () => {
  it('keeps the focus coordinator mounted and preserves timezone prompt space', () => {
    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <AppShell>
          <p>Route content</p>
        </AppShell>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('focus-timer-coordinator')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveStyle({
      paddingBottom: 'calc(env(safe-area-inset-bottom) + 88px + var(--timezone-prompt-reserve, 0px))',
    });
  });
});
