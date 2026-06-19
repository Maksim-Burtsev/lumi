import type { AppLocale } from './i18n';

/** Russian formatting helpers: pluralization, times, relative dates. */

/** Proper Russian pluralization: plural(3, ['задача', 'задачи', 'задач']) → 'задачи' */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}

export function countLabel(n: number, forms: [string, string, string]): string {
  return `${n} ${plural(n, forms)}`;
}

const dayMonthFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const headingFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
const weekdayShortFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });

export type ResolvedTimeFormat = '24h' | '12h';
export type TimeFormat = 'auto' | ResolvedTimeFormat;

export interface TimeDisplayOptions {
  locale?: AppLocale;
  timeFormat?: TimeFormat;
  timezone?: string | null;
  regionalLocale?: string | null;
}

export function normalizeTimeFormat(value: unknown): TimeFormat {
  if (value === 'auto') return 'auto';
  if (value === '12h') return '12h';
  if (value === '24h') return '24h';
  return 'auto';
}

function browserLocale(): string | null {
  if (typeof navigator === 'undefined') return null;
  return navigator.languages?.[0] ?? navigator.language ?? null;
}

export function regionalLocaleTag(options: TimeDisplayOptions = {}): string {
  if (options.locale === 'ru') return 'ru-RU';
  const regional = options.regionalLocale ?? browserLocale();
  if (regional?.toLowerCase().startsWith('en-')) return regional;
  if (options.timezone?.startsWith('Europe/')) return 'en-GB';
  return 'en-US';
}

function localeTag(options: TimeDisplayOptions = {}): string {
  return !options.locale || options.locale === 'ru' ? 'ru-RU' : regionalLocaleTag(options);
}

function withTimezone(timezone: string | null | undefined): Pick<Intl.DateTimeFormatOptions, 'timeZone'> {
  return timezone ? { timeZone: timezone } : {};
}

function safeDateTimeFormat(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  try {
    return new Intl.DateTimeFormat(locale, options);
  } catch (error) {
    if (!(error instanceof RangeError) || !('timeZone' in options)) throw error;
    const { timeZone: _timeZone, ...fallback } = options;
    return new Intl.DateTimeFormat(locale, fallback);
  }
}

export function resolveTimeFormat(options: TimeDisplayOptions = {}): ResolvedTimeFormat {
  const timeFormat = normalizeTimeFormat(options.timeFormat);
  if (timeFormat !== 'auto') return timeFormat;
  try {
    const resolved = new Intl.DateTimeFormat(regionalLocaleTag(options), { hour: 'numeric' })
      .resolvedOptions() as Intl.ResolvedDateTimeFormatOptions & { hourCycle?: string; hour12?: boolean };
    const hourCycle = resolved.hourCycle;
    if (typeof resolved.hour12 === 'boolean') return resolved.hour12 ? '12h' : '24h';
    return hourCycle === 'h11' || hourCycle === 'h12' ? '12h' : '24h';
  } catch {
    return regionalLocaleTag(options) === 'en-US' ? '12h' : '24h';
  }
}

function timeFormatter(options: TimeDisplayOptions = {}): Intl.DateTimeFormat {
  const timeFormat = resolveTimeFormat(options);
  return safeDateTimeFormat(localeTag(options), {
    hour: timeFormat === '12h' ? 'numeric' : '2-digit',
    minute: '2-digit',
    hour12: timeFormat === '12h',
    ...withTimezone(options.timezone),
  });
}

function dayMonthTimeFormatter(options: TimeDisplayOptions = {}): Intl.DateTimeFormat {
  const timeFormat = resolveTimeFormat(options);
  return safeDateTimeFormat(localeTag(options), {
    day: 'numeric',
    hour: timeFormat === '12h' ? 'numeric' : '2-digit',
    minute: '2-digit',
    month: 'short',
    hour12: timeFormat === '12h',
    ...withTimezone(options.timezone),
  });
}

function dayKey(d: Date, timezone?: string | null): string {
  const parts = safeDateTimeFormat('en-CA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    ...withTimezone(timezone),
  }).formatToParts(d);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function capitalize(s: string): string {
  return s.length > 0 ? s[0].toUpperCase() + s.slice(1) : s;
}

/** "14:05" with tabular figures expected at render site */
export function formatTime(ts: string | Date, options: TimeDisplayOptions = {}): string {
  const d = typeof ts === 'string' ? new Date(ts) : ts;
  if (Number.isNaN(d.getTime())) return '—';
  return timeFormatter(options).format(d);
}

export function formatTimeRange(start: string, end: string, options: TimeDisplayOptions = {}): string {
  return `${formatTime(start, options)}–${formatTime(end, options)}`;
}

/** "Вторник, 10 июня" / "Friday, June 19" / "Friday, 19 June" */
export function formatDateHeading(d: Date, options: TimeDisplayOptions = {}): string {
  if (options.locale === 'en') {
    return safeDateTimeFormat(regionalLocaleTag(options), {
      day: 'numeric',
      month: 'long',
      weekday: 'long',
    }).format(d);
  }
  return capitalize(headingFmt.format(d));
}

export function isSameDay(a: Date, b: Date, timezone?: string | null): boolean {
  if (timezone) return dayKey(a, timezone) === dayKey(b, timezone);
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, days: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + days);
  return r;
}

/** "YYYY-MM-DD" in *local* time — for ?date= API params */
export function formatDateParam(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Day switcher label: "Сегодня, 10 июня" / "Today, June 10" / "Today, 10 June" */
export function formatDayLabel(d: Date, options: TimeDisplayOptions = {}): string {
  const today = startOfDay(new Date());
  if (options.locale === 'en') {
    if (isSameDay(d, today, options.timezone)) return `Today, ${dayMonthLong(d, options)}`;
    if (isSameDay(d, addDays(today, 1), options.timezone)) return `Tomorrow, ${dayMonthLong(d, options)}`;
    if (isSameDay(d, addDays(today, -1), options.timezone)) return `Yesterday, ${dayMonthLong(d, options)}`;
    return safeDateTimeFormat(regionalLocaleTag(options), {
      day: 'numeric',
      month: 'long',
      weekday: 'short',
    }).format(d);
  }
  if (isSameDay(d, today, options.timezone)) return `Сегодня, ${dayMonthLong(d, options)}`;
  if (isSameDay(d, addDays(today, 1), options.timezone)) return `Завтра, ${dayMonthLong(d, options)}`;
  if (isSameDay(d, addDays(today, -1), options.timezone)) return `Вчера, ${dayMonthLong(d, options)}`;
  return capitalize(weekdayShortFmt.format(d));
}

function dayMonthLong(d: Date, options: TimeDisplayOptions = {}): string {
  return safeDateTimeFormat(localeTag(options), { day: 'numeric', month: 'long' }).format(d);
}

/** Relative time: "только что", "2 мин назад", "вчера", "через 3 ч" … */
export function formatRelative(ts: string | null | undefined, options: TimeDisplayOptions = {}): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const future = diffMs < 0;
  const abs = Math.abs(diffMs);

  const min = Math.round(abs / 60_000);
  const hours = Math.round(abs / 3_600_000);

  if (abs < 45_000) return future ? 'через минуту' : 'только что';
  if (min < 60) return future ? `через ${min} мин` : `${min} мин назад`;
  if (hours < 24 && isSameDay(d, now, options.timezone)) return future ? `через ${countLabel(hours, ['час', 'часа', 'часов'])}` : `${hours} ч назад`;

  const today = startOfDay(now);
  if (isSameDay(d, addDays(today, -1), options.timezone)) return 'вчера';
  if (isSameDay(d, addDays(today, 1), options.timezone)) return `завтра в ${formatTime(d, options)}`;

  const days = Math.round(abs / 86_400_000);
  if (!future && days < 7) return `${countLabel(days, ['день', 'дня', 'дней'])} назад`;
  if (future && days < 7) return `через ${countLabel(days, ['день', 'дня', 'дней'])}`;

  return dayMonthFmt.format(d);
}

/** Due label for tasks: "Сегодня 14:00", "Завтра 09:00", "10 июн 09:00" */
export function formatDueLabel(ts: string, options: TimeDisplayOptions = {}): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  const today = startOfDay(new Date());
  if (options.locale === 'en') {
    if (isSameDay(d, today, options.timezone)) return `Today ${formatTime(d, options)}`;
    if (isSameDay(d, addDays(today, 1), options.timezone)) return `Tomorrow ${formatTime(d, options)}`;
    if (isSameDay(d, addDays(today, -1), options.timezone)) return `Yesterday ${formatTime(d, options)}`;
    return dayMonthTimeFormatter(options).format(d);
  }
  if (isSameDay(d, today, options.timezone)) return `Сегодня ${formatTime(d, options)}`;
  if (isSameDay(d, addDays(today, 1), options.timezone)) return `Завтра ${formatTime(d, options)}`;
  if (isSameDay(d, addDays(today, -1), options.timezone)) return `Вчера ${formatTime(d, options)}`;
  return dayMonthTimeFormatter(options).format(d);
}

/** "12,3 с" / "2 мин 05 с" — for run durations */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} мс`;
  const sec = ms / 1000;
  if (sec < 90) return `${sec.toFixed(1).replace('.', ',')} с`;
  const minutes = Math.floor(sec / 60);
  const rest = Math.round(sec % 60);
  return `${minutes} мин ${String(rest).padStart(2, '0')} с`;
}

/** "1 ч 30 мин" — for slot lengths */
export function formatSpanMinutes(startTs: string, endTs: string): string {
  const minutes = Math.max(0, Math.round((new Date(endTs).getTime() - new Date(startTs).getTime()) / 60_000));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h} ч ${m} мин`;
  if (h > 0) return `${h} ч`;
  return `${m} мин`;
}
