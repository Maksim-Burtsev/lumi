import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UnauthorizedScreen } from './UnauthorizedScreen';

describe('UnauthorizedScreen', () => {
  it('directs standalone users to request a one-time link from Telegram', () => {
    render(<UnauthorizedScreen onRetry={vi.fn()} />);

    expect(screen.getByText('Sign in through Telegram')).toBeInTheDocument();
    expect(screen.getByText(/Send \/web to Lumi/)).toBeInTheDocument();
    expect(screen.queryByText(/localStorage/i)).not.toBeInTheDocument();
  });
});
