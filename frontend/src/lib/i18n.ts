export type AppLocale = 'en' | 'ru';

export type Localized<T> = Record<AppLocale, T>;

export function normalizeAppLocale(value: unknown): AppLocale {
  return value === 'ru' ? 'ru' : 'en';
}

export function pickLocaleText<T>(locale: AppLocale, values: { en: T; ru: T }): T {
  return values[locale];
}

export function localized<T>(values: Localized<T>, locale: unknown): T {
  return values[normalizeAppLocale(locale)];
}
