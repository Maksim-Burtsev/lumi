export type AppLocale = 'en' | 'ru';

export function normalizeAppLocale(value: unknown): AppLocale {
  return value === 'ru' ? 'ru' : 'en';
}

export function pickLocaleText<T>(locale: AppLocale, values: { en: T; ru: T }): T {
  return values[locale];
}
