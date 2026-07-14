import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BottomNav } from './BottomNav';

describe('BottomNav product navigation', () => {
  it('renders exactly the four product areas with one active item', () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/sessions']}>
          <BottomNav />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const items = screen.getAllByRole('button');

    expect(items.map((item) => item.getAttribute('aria-label'))).toEqual([
      'Today',
      'Tasks',
      'Sessions',
      'Calendar',
    ]);
    expect(items.filter((item) => item.getAttribute('aria-current') === 'page')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Sessions' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('button', { name: 'Inbox' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Settings' })).not.toBeInTheDocument();
    expect(screen.getByRole('navigation')).not.toHaveClass('lg:hidden');
  });

  it('hides the mobile navigation at desktop width only for standalone web', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <BottomNav standalone />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole('navigation')).toHaveClass('lg:hidden');
  });
});
