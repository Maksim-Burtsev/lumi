/**
 * Null-safe wrapper around the Telegram WebApp SDK.
 * Every function degrades gracefully when running in a plain browser
 * (window.Telegram absent) so the app never crashes outside Telegram.
 */

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
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null;
  return window.Telegram?.WebApp ?? null;
}

export function getInitData(): string {
  return getTelegramWebApp()?.initData ?? '';
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 };
}

function applyTheme(): void {
  const root = document.documentElement;
  const tg = getTelegramWebApp();

  const prefersDark =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = tg ? tg.colorScheme === 'dark' : prefersDark;
  root.classList.toggle('dark', isDark);

  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = isDark ? '#141310' : '#F6F4EF';

  const params = tg?.themeParams;
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

export function setupTelegramTheme(): void {
  const tg = getTelegramWebApp();
  try {
    tg?.ready();
  } catch {
    /* never crash on SDK quirks */
  }

  applyTheme();

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
