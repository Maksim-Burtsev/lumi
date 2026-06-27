import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Timeline } from './Timeline';

function renderTimeline(onPress = vi.fn(), onAction = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <Timeline
        entries={[
          {
            id: 'proposed-1',
            kind: 'proposed',
            title: 'Focus block',
            start_at: '2026-06-12T10:00:00+04:00',
            end_at: '2026-06-12T11:00:00+04:00',
            onPress,
            action: { label: 'Принять', onClick: onAction },
          },
        ]}
      />
    </QueryClientProvider>,
  );
}

describe('Timeline row actions', () => {
  it('triggers the row press handler when the row is clicked', async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    renderTimeline(onPress);

    await user.click(screen.getByRole('button', { name: /Focus block/ }));

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not trigger the row press handler when an inline action is clicked', async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    const onAction = vi.fn();
    renderTimeline(onPress, onAction);

    await user.click(screen.getByRole('button', { name: 'Принять' }));

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onPress).not.toHaveBeenCalled();
  });

  it('does not trigger the row press handler when an inline action is used from the keyboard', async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    const onAction = vi.fn();
    renderTimeline(onPress, onAction);

    screen.getByRole('button', { name: 'Принять' }).focus();
    await user.keyboard('{Enter}');

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onPress).not.toHaveBeenCalled();
  });
});
