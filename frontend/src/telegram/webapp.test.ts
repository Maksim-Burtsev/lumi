import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setupTelegramTheme } from './webapp';

declare global {
  interface Window {
    TelegramWebviewProxy?: {
      postEvent: (eventType: string, eventData: string) => void;
    };
  }
}

describe('Telegram readiness', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    delete window.TelegramWebviewProxy;
    Reflect.deleteProperty(window, 'external');
    vi.useRealTimers();
  });

  it('notifies Telegram when the bridge appears after startup', () => {
    vi.useFakeTimers();
    const postEvent = vi.fn();

    setupTelegramTheme();
    window.TelegramWebviewProxy = { postEvent };

    vi.advanceTimersByTime(50);

    expect(postEvent).toHaveBeenCalledWith('web_app_ready', JSON.stringify(''));
  });

  it('notifies Telegram when external.notify appears after startup', () => {
    vi.useFakeTimers();
    const notify = vi.fn();

    setupTelegramTheme();
    Object.defineProperty(window, 'external', {
      configurable: true,
      value: { notify },
    });

    vi.advanceTimersByTime(50);

    expect(notify).toHaveBeenCalledWith(
      JSON.stringify({ eventType: 'web_app_ready', eventData: '' }),
    );
  });

  it('falls back to external.notify when TelegramWebviewProxy throws', () => {
    vi.useFakeTimers();
    const notify = vi.fn();

    window.TelegramWebviewProxy = {
      postEvent: () => {
        throw new Error('bridge is not ready');
      },
    };
    Object.defineProperty(window, 'external', {
      configurable: true,
      value: { notify },
    });

    setupTelegramTheme();
    vi.advanceTimersByTime(50);

    expect(notify).toHaveBeenCalledWith(
      JSON.stringify({ eventType: 'web_app_ready', eventData: '' }),
    );
  });
});
