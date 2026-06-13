import { StrictMode, useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Sheet } from './Sheet';

function setWindowScrollY(value: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value });
}

function SheetHarness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Decision">
        <p>Sheet body</p>
      </Sheet>
    </>
  );
}

describe('Sheet scroll lock', () => {
  it('locks the body at the current scroll position and restores it on close', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    setWindowScrollY(420);
    window.scrollTo = scrollTo;

    render(<SheetHarness />);

    expect(screen.getByRole('dialog', { name: 'Decision' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-420px');
    expect(document.body.style.width).toBe('100%');

    await user.click(screen.getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.body.style.position).toBe('');
      expect(document.body.style.top).toBe('');
      expect(scrollTo).toHaveBeenCalledWith(0, 420);
    });
  });

  it('restores scroll once when mounted under StrictMode', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    setWindowScrollY(260);
    window.scrollTo = scrollTo;

    render(
      <StrictMode>
        <SheetHarness />
      </StrictMode>,
    );

    expect(screen.getByRole('dialog', { name: 'Decision' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Decision' })).not.toBeInTheDocument();
    });
    expect(scrollTo).toHaveBeenLastCalledWith(0, 260);
  });
});
