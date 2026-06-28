import { describe, expect, it } from 'vitest';
import { normalizeThemeMode, resolveIsDarkTheme } from './theme';

describe('theme mode', () => {
  it('normalizes unknown values to Telegram mode', () => {
    expect(normalizeThemeMode('telegram')).toBe('telegram');
    expect(normalizeThemeMode('light')).toBe('light');
    expect(normalizeThemeMode('dark')).toBe('dark');
    expect(normalizeThemeMode('system')).toBe('telegram');
    expect(normalizeThemeMode(undefined)).toBe('telegram');
  });

  it('forces light or dark when the user overrides Telegram theme', () => {
    expect(resolveIsDarkTheme({ mode: 'light', telegramColorScheme: 'dark', prefersDark: true })).toBe(false);
    expect(resolveIsDarkTheme({ mode: 'dark', telegramColorScheme: 'light', prefersDark: false })).toBe(true);
  });

  it('uses Telegram color scheme in Telegram mode, then falls back to OS preference', () => {
    expect(resolveIsDarkTheme({ mode: 'telegram', telegramColorScheme: 'dark', prefersDark: false })).toBe(true);
    expect(resolveIsDarkTheme({ mode: 'telegram', telegramColorScheme: 'light', prefersDark: true })).toBe(false);
    expect(resolveIsDarkTheme({ mode: 'telegram', telegramColorScheme: null, prefersDark: true })).toBe(true);
  });
});
