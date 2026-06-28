import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { captureTelegramInitParams, getInitData, setupTelegramTheme } from './webapp';

declare global {
  interface Window {
    TelegramWebviewProxy?: {
      postEvent: (eventType: string, eventData: string) => void;
    };
  }
}

describe('Telegram readiness', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState(null, '', '/');
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
    window.sessionStorage.clear();
    window.history.replaceState(null, '', '/');
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

  it('keeps Telegram init data when the router replaces the launch hash', () => {
    vi.useFakeTimers();
    const postEvent = vi.fn();
    window.location.hash = '#tgWebAppData=query_id%3Dabc123&tgWebAppVersion=7.10';

    captureTelegramInitParams();
    window.location.hash = '#/';
    window.TelegramWebviewProxy = { postEvent };

    setupTelegramTheme();
    vi.advanceTimersByTime(50);

    expect(getInitData()).toBe('query_id=abc123');
    expect(postEvent).toHaveBeenCalledWith('web_app_ready', JSON.stringify(''));
  });
});
