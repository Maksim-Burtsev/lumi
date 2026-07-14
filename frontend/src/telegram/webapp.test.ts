import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  beginStandaloneWebAuth,
  captureTelegramInitParams,
  getInitData,
  setThemeMode,
  setupTelegramTheme,
} from './webapp';

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
    Object.defineProperty(window, 'parent', { configurable: true, value: window });
    Object.defineProperty(document, 'referrer', { configurable: true, value: '' });
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
    Object.defineProperty(window, 'parent', { configurable: true, value: window });
    Object.defineProperty(document, 'referrer', { configurable: true, value: '' });
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

  it('suppresses CSS transitions during a theme swap', () => {
    const callbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callbacks.push(callback);
      return callbacks.length;
    });

    setThemeMode('dark');

    expect(document.documentElement).toHaveClass('dark');
    expect(document.documentElement).toHaveClass('theme-swap');

    callbacks.shift()?.(0);
    expect(document.documentElement).toHaveClass('theme-swap');
    callbacks.shift()?.(16);
    expect(document.documentElement).not.toHaveClass('theme-swap');
  });

  it('does not resurrect stored init data in a plain standalone login', () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=stale-user',
      tgWebAppVersion: '7.10',
    }));
    window.location.hash = '#/web-login?nonce=standalone';

    captureTelegramInitParams();

    expect(getInitData()).toBe('');
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

  it('restores stored init data on a hard reload only while a Telegram bridge is present', async () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=hard-reload',
      tgWebAppVersion: '7.10',
    }));
    window.location.hash = '#/tasks';
    window.TelegramWebviewProxy = { postEvent: vi.fn() };
    vi.resetModules();

    const reloadedWebApp = await import('./webapp');

    expect(reloadedWebApp.getInitData()).toBe('query_id=hard-reload');
  });

  it('restores stored init data for the same Telegram Web parent after a hard reload', async () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=telegram-web-reload',
      tgWebAppVersion: '7.10',
    }));
    window.sessionStorage.setItem('__telegram__parentOrigin', 'https://web.telegram.org');
    window.location.hash = '#/tasks';
    Object.defineProperty(window, 'parent', { configurable: true, value: {} });
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: 'https://web.telegram.org/k/',
    });
    vi.resetModules();

    const reloadedWebApp = await import('./webapp');

    expect(reloadedWebApp.getInitData()).toBe('query_id=telegram-web-reload');
  });

  it('does not restore stored init data inside an unrelated iframe', async () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=stale-telegram-user',
      tgWebAppVersion: '7.10',
    }));
    window.sessionStorage.setItem('__telegram__parentOrigin', 'https://web.telegram.org');
    window.location.hash = '#/';
    Object.defineProperty(window, 'parent', { configurable: true, value: {} });
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: 'https://evil.example/embed',
    });
    vi.resetModules();

    const reloadedWebApp = await import('./webapp');

    expect(reloadedWebApp.getInitData()).toBe('');
  });

  it('does not let launch metadata unlock stored init data in an unrelated iframe', async () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=stale-telegram-user',
      tgWebAppVersion: '7.10',
    }));
    window.sessionStorage.setItem('__telegram__parentOrigin', 'https://web.telegram.org');
    window.location.hash = '#tgWebAppVersion=7.10';
    Object.defineProperty(window, 'parent', { configurable: true, value: {} });
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: 'https://evil.example/embed',
    });
    vi.resetModules();

    const reloadedWebApp = await import('./webapp');

    expect(reloadedWebApp.getInitData()).toBe('');
    void reloadedWebApp.loadTelegramSdk();
    expect(document.querySelector('script[data-telegram-webapp-sdk]')).toBeNull();
  });

  it('keeps init data disabled after standalone login redirects inside the SPA', () => {
    window.sessionStorage.setItem('__telegram__initParams', JSON.stringify({
      tgWebAppData: 'query_id=old-telegram-user',
    }));

    beginStandaloneWebAuth();
    window.location.hash = '#/';

    expect(getInitData()).toBe('');
    expect(window.sessionStorage.getItem('__telegram__initParams')).toBeNull();
  });
});
