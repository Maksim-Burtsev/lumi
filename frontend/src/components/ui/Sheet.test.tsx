import { StrictMode, useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
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

function NestedSheetHarness() {
  const [parentOpen, setParentOpen] = useState(true);
  const [childOpen, setChildOpen] = useState(false);
  return (
    <>
      <Sheet open={parentOpen} onClose={() => setParentOpen(false)} title="History">
        <button type="button" onClick={() => setChildOpen(true)}>
          Open details
        </button>
        <p>History body</p>
      </Sheet>
      <Sheet open={childOpen} onClose={() => setChildOpen(false)} title="Details">
        <p>Details body</p>
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

  it('keeps body locked while a nested sheet closes and restores only after the last sheet closes', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.fn();
    setWindowScrollY(320);
    window.scrollTo = scrollTo;

    render(<NestedSheetHarness />);

    expect(screen.getByRole('dialog', { name: 'History' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-320px');

    await user.click(screen.getByRole('button', { name: 'Open details' }));

    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-320px');

    await user.click(within(screen.getByRole('dialog', { name: 'Details' })).getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Details' })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('dialog', { name: 'History' })).toBeInTheDocument();
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-320px');
    expect(scrollTo).not.toHaveBeenCalled();

    await user.click(within(screen.getByRole('dialog', { name: 'History' })).getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'History' })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.body.style.position).toBe('');
      expect(scrollTo).toHaveBeenCalledTimes(1);
      expect(scrollTo).toHaveBeenCalledWith(0, 320);
    });
  });
});
