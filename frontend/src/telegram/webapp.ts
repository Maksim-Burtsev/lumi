/**
 * Null-safe wrapper around the Telegram WebApp SDK.
 * Every function degrades gracefully when running in a plain browser
 * (window.Telegram absent) so the app never crashes outside Telegram.
 */

import { cacheThemeMode, normalizeThemeMode, readCachedThemeMode, resolveIsDarkTheme } from '../lib/theme';
import type { ThemeMode } from '../lib/theme';

export interface TelegramThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
}

export interface TelegramHapticFeedback {
  impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
  notificationOccurred: (type: 'error' | 'success' | 'warning') => void;
  selectionChanged: () => void;
}

export interface TelegramWebApp {
  initData: string;
  colorScheme: 'light' | 'dark';
  themeParams: TelegramThemeParams;
  ready: () => void;
  expand: () => void;
  onEvent?: (event: string, handler: () => void) => void;
  offEvent?: (event: string, handler: () => void) => void;
  HapticFeedback?: TelegramHapticFeedback;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
    TelegramWebviewProxy?: {
      postEvent: (eventType: string, eventData: string) => void;
    };
  }
}

type TelegramInitParams = Record<string, string>;

const INIT_PARAMS_STORAGE_KEY = '__telegram__initParams';
const THEME_PARAMS_STORAGE_KEY = '__telegram__themeParams';
const THEME_SWAP_CLASS = 'theme-swap';

let telegramSdkLoad: Promise<void> | null = null;
let cachedInitParams: TelegramInitParams = {};
let themeSwapFrame: number | null = null;

export function getTelegramWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null;
  return window.Telegram?.WebApp ?? null;
}

function readStoredInitParams(): TelegramInitParams {
  try {
    const raw = window.sessionStorage.getItem(INIT_PARAMS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return {};
    const params: TelegramInitParams = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === 'string') params[key] = value;
    }
    return params;
  } catch {
    return {};
  }
}

function readHashInitParams(): TelegramInitParams {
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return {};

  const params = new URLSearchParams(hash);
  const result: TelegramInitParams = {};
  params.forEach((value, key) => {
    if (key.startsWith('tgWebApp')) result[key] = value;
  });
  return result;
}

function getTelegramInitParams(): TelegramInitParams {
  if (typeof window === 'undefined') return {};

  const params = { ...cachedInitParams, ...readStoredInitParams(), ...readHashInitParams() };
  if (Object.keys(params).length > 0) {
    cachedInitParams = params;
    try {
      window.sessionStorage.setItem(INIT_PARAMS_STORAGE_KEY, JSON.stringify(params));
    } catch {
      /* sessionStorage can be unavailable in embedded clients */
    }
  }
  return params;
}

export function captureTelegramInitParams(): void {
  void getTelegramInitParams();
}

function hasTelegramBridge(): boolean {
  if (typeof window === 'undefined') return false;
  const external = window.external as { notify?: (payload: string) => void } | undefined;
  return Boolean(
    window.TelegramWebviewProxy ||
      (external && typeof external.notify === 'function') ||
      window.parent !== window,
  );
}

function hasTelegramLaunchParams(): boolean {
  return Object.keys(getTelegramInitParams()).length > 0;
}

function postTelegramEvent(eventType: string, eventData: unknown = ''): boolean {
  if (typeof window === 'undefined') return false;

  try {
    if (window.TelegramWebviewProxy) {
      window.TelegramWebviewProxy.postEvent(eventType, JSON.stringify(eventData));
      return true;
    }
  } catch {
    /* try the next bridge */
  }

  try {
    const external = window.external as { notify?: (payload: string) => void } | undefined;
    if (external && typeof external.notify === 'function') {
      external.notify(JSON.stringify({ eventType, eventData }));
      return true;
    }
  } catch {
    /* try the next bridge */
  }

  try {
    if (window.parent !== window) {
      window.parent.postMessage(JSON.stringify({ eventType, eventData }), '*');
      return true;
    }
  } catch {
    return false;
  }

  return false;
}

function notifyReady(): void {
  const tg = getTelegramWebApp();
  if (tg) {
    try {
      tg.ready();
      return;
    } catch {
      /* fall back to lower-level bridges */
    }
  }

  try {
    if (hasTelegramLaunchParams() || hasTelegramBridge()) postTelegramEvent('web_app_ready');
  } catch {
    /* never crash on SDK quirks */
  }
}

function scheduleReadyFallbacks(): void {
  if (typeof window === 'undefined') return;
  window.setTimeout(notifyReady, 0);
  window.setTimeout(notifyReady, 50);
  window.setTimeout(notifyReady, 250);
  window.setTimeout(notifyReady, 1000);
  window.setTimeout(notifyReady, 2000);
  window.setTimeout(notifyReady, 5000);
}

export function getInitData(): string {
  return getTelegramWebApp()?.initData ?? getTelegramInitParams().tgWebAppData ?? '';
}

function getFallbackThemeParams(): TelegramThemeParams | undefined {
  if (typeof window === 'undefined') return undefined;

  const raw = getTelegramInitParams().tgWebAppThemeParams;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as TelegramThemeParams;
      window.sessionStorage.setItem(THEME_PARAMS_STORAGE_KEY, JSON.stringify(parsed));
      return parsed;
    } catch {
      /* bad theme payload */
    }
  }

  try {
    const stored = window.sessionStorage.getItem(THEME_PARAMS_STORAGE_KEY);
    return stored ? (JSON.parse(stored) as TelegramThemeParams) : undefined;
  } catch {
    return undefined;
  }
}

export function loadTelegramSdk(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  if (getTelegramWebApp()) return Promise.resolve();
  if (!hasTelegramLaunchParams() && !hasTelegramBridge()) return Promise.resolve();
  if (telegramSdkLoad) return telegramSdkLoad;

  telegramSdkLoad = new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-telegram-webapp-sdk]');
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => resolve(), { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-web-app.js';
    script.async = true;
    script.dataset.telegramWebappSdk = 'true';
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.appendChild(script);
  });

  return telegramSdkLoad;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 };
}

function prefersDarkTheme(): boolean {
  if (typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-color-scheme: dark)')?.matches ?? false;
}

function suppressThemeSwapTransitions(root: HTMLElement): void {
  if (typeof window === 'undefined') return;
  if (themeSwapFrame !== null && typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(themeSwapFrame);
  }

  root.classList.add(THEME_SWAP_CLASS);
  const clear = () => {
    themeSwapFrame = null;
    root.classList.remove(THEME_SWAP_CLASS);
  };

  if (typeof window.requestAnimationFrame === 'function') {
    themeSwapFrame = window.requestAnimationFrame(() => {
      themeSwapFrame = window.requestAnimationFrame(clear);
    });
    return;
  }

  window.setTimeout(clear, 0);
}

function applyTheme(mode?: ThemeMode): void {
  const root = document.documentElement;
  const tg = getTelegramWebApp();

  const themeMode = normalizeThemeMode(mode ?? readCachedThemeMode());
  const isDark = resolveIsDarkTheme({
    mode: themeMode,
    telegramColorScheme: tg?.colorScheme ?? null,
    prefersDark: prefersDarkTheme(),
  });
  if (root.classList.contains('dark') !== isDark) {
    suppressThemeSwapTransitions(root);
  }
  root.classList.toggle('dark', isDark);

  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = isDark ? '#141310' : '#F6F4EF';

  const params = tg?.themeParams ?? getFallbackThemeParams();
  if (params?.button_color) {
    root.style.setProperty('--tg-button', params.button_color);
    // Telegram button color becomes a *tint* for secondary CTAs;
    // the amber identity stays dominant.
    const rgb = hexToRgb(params.button_color);
    if (rgb) {
      root.style.setProperty('--secondary-bg', `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.12)`);
      root.style.setProperty('--secondary-text', isDark ? '#F2EFE8' : params.button_color);
    }
  }

  try {
    tg?.setBackgroundColor?.(isDark ? '#141310' : '#F6F4EF');
    tg?.setHeaderColor?.(isDark ? '#141310' : '#F6F4EF');
  } catch {
    /* older clients */
  }
}

export function setThemeMode(mode: ThemeMode): void {
  cacheThemeMode(mode);
  applyTheme(mode);
}

export function setupTelegramTheme(mode?: ThemeMode): void {
  const tg = getTelegramWebApp();
  scheduleReadyFallbacks();

  applyTheme(mode);

  try {
    tg?.onEvent?.('themeChanged', applyTheme);
  } catch {
    /* noop */
  }

  if (!tg && typeof window.matchMedia === 'function') {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const listener = () => applyTheme();
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', listener);
  }
}

export type HapticType = 'light' | 'medium' | 'heavy' | 'success' | 'error';

export function haptic(type: HapticType): void {
  const h = getTelegramWebApp()?.HapticFeedback;
  if (!h) return;
  try {
    if (type === 'success' || type === 'error') h.notificationOccurred(type);
    else h.impactOccurred(type);
  } catch {
    /* noop */
  }
}

/** Open a URL in the external browser (Telegram-aware, null-safe). */
export function openExternalLink(url: string): void {
  const tg = getTelegramWebApp();
  if (tg?.openLink) {
    tg.openLink(url);
  } else {
    window.open(url, '_blank', 'noopener');
  }
}
