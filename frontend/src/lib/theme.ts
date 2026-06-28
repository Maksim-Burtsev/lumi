import type { ThemeMode } from '../api/types';

export type { ThemeMode };

export const THEME_MODE_STORAGE_KEY = 'lumi-theme-mode';

export function normalizeThemeMode(value: unknown): ThemeMode {
  if (value === 'light') return 'light';
  if (value === 'dark') return 'dark';
  return 'telegram';
}

export function readCachedThemeMode(): ThemeMode {
  try {
    return normalizeThemeMode(window.localStorage.getItem(THEME_MODE_STORAGE_KEY));
  } catch {
    return 'telegram';
  }
}

export function cacheThemeMode(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, mode);
  } catch {
    /* localStorage can be unavailable in embedded clients */
  }
}

export function resolveIsDarkTheme({
  mode,
  telegramColorScheme,
  prefersDark,
}: {
  mode: ThemeMode;
  telegramColorScheme: 'light' | 'dark' | null | undefined;
  prefersDark: boolean;
}): boolean {
  if (mode === 'light') return false;
  if (mode === 'dark') return true;
  if (telegramColorScheme === 'dark') return true;
  if (telegramColorScheme === 'light') return false;
  return prefersDark;
}
