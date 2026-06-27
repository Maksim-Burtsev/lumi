import type { AppLocale } from './i18n';
import { normalizeAppLocale } from './i18n';

/** Small cron humanizer for common patterns; falls back to the raw expression. */

const DOW_PLURAL: Record<AppLocale, Record<number, string>> = {
  en: {
    0: 'Sundays',
    1: 'Mondays',
    2: 'Tuesdays',
    3: 'Wednesdays',
    4: 'Thursdays',
    5: 'Fridays',
    6: 'Saturdays',
    7: 'Sundays',
  },
  ru: {
    0: 'воскресеньям',
    1: 'понедельникам',
    2: 'вторникам',
    3: 'средам',
    4: 'четвергам',
    5: 'пятницам',
    6: 'субботам',
    7: 'воскресеньям',
  },
};

const DOW_SHORT: Record<AppLocale, Record<number, string>> = {
  en: {
    0: 'Sun',
    1: 'Mon',
    2: 'Tue',
    3: 'Wed',
    4: 'Thu',
    5: 'Fri',
    6: 'Sat',
    7: 'Sun',
  },
  ru: {
    0: 'Вс',
    1: 'Пн',
    2: 'Вт',
    3: 'Ср',
    4: 'Чт',
    5: 'Пт',
    6: 'Сб',
    7: 'Вс',
  },
};

function timeLabel(minute: number, hour: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function parseEveryN(field: string): number | null {
  const m = /^\*\/(\d+)$/.exec(field);
  return m ? parseInt(m[1], 10) : null;
}

function isNum(field: string): boolean {
  return /^\d+$/.test(field);
}

function ruMinuteWord(n: number): string {
  return n % 10 === 1 && n % 100 !== 11
    ? 'минуту'
    : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)
      ? 'минуты'
      : 'минут';
}

function ruHourWord(n: number): string {
  return n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'часа' : 'часов';
}

export function humanizeCron(expr: string, rawLocale?: AppLocale): string {
  const locale = normalizeAppLocale(rawLocale);
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [min, hour, dom, mon, dow] = parts;

  if (dom !== '*' || mon !== '*') return expr;

  if (min === '*' && hour === '*' && dow === '*') return locale === 'en' ? 'Every minute' : 'Каждую минуту';

  const everyMin = parseEveryN(min);
  if (everyMin !== null && hour === '*' && dow === '*') {
    if (everyMin === 1) return locale === 'en' ? 'Every minute' : 'Каждую минуту';
    return locale === 'en' ? `Every ${everyMin} minutes` : `Каждые ${everyMin} ${ruMinuteWord(everyMin)}`;
  }

  const everyHour = parseEveryN(hour);
  if (isNum(min) && everyHour !== null && dow === '*') {
    if (everyHour === 1) return locale === 'en' ? 'Every hour' : 'Каждый час';
    return locale === 'en' ? `Every ${everyHour} hours` : `Каждые ${everyHour} ${ruHourWord(everyHour)}`;
  }

  if (isNum(min) && hour === '*' && dow === '*') {
    const minute = String(parseInt(min, 10)).padStart(2, '0');
    return locale === 'en' ? `Every hour at :${minute}` : `Каждый час в :${minute}`;
  }

  if (!isNum(min) || !isNum(hour)) return expr;
  const t = timeLabel(parseInt(min, 10), parseInt(hour, 10));

  if (dow === '*') return locale === 'en' ? `Every day ${t}` : `Каждый день ${t}`;
  if (dow === '1-5') return locale === 'en' ? `Weekdays ${t}` : `Будни ${t}`;
  if (dow === '6,0' || dow === '0,6' || dow === '6,7' || dow === '6-7') {
    return locale === 'en' ? `Weekends ${t}` : `Выходные ${t}`;
  }

  if (isNum(dow)) {
    const d = parseInt(dow, 10);
    const name = DOW_PLURAL[locale][d];
    if (name) return locale === 'en' ? `${name} ${t}` : `По ${name} ${t}`;
  }

  if (/^[0-7](,[0-7])+$/.test(dow)) {
    const names = dow
      .split(',')
      .map((s) => DOW_SHORT[locale][parseInt(s, 10)])
      .filter((s): s is string => Boolean(s));
    if (names.length > 0) return `${names.join(', ')} · ${t}`;
  }

  return expr;
}

export interface CronPreset {
  id: string;
  label: string;
  expression: string | null;
}

const CRON_PRESETS_BY_LOCALE: Record<AppLocale, CronPreset[]> = {
  en: [
    { id: 'morning-8', label: 'Every morning 08:00', expression: '0 8 * * *' },
    { id: 'weekday-morning', label: 'Every morning 08:30, weekdays', expression: '30 8 * * 1-5' },
    { id: 'daily-9', label: 'Every day 09:00', expression: '0 9 * * *' },
    { id: 'every-30m', label: 'Every 30 minutes', expression: '*/30 * * * *' },
    { id: 'custom', label: 'Custom cron expression', expression: null },
  ],
  ru: [
    { id: 'morning-8', label: 'Каждое утро 08:00', expression: '0 8 * * *' },
    { id: 'weekday-morning', label: 'Каждое утро 08:30, будни', expression: '30 8 * * 1-5' },
    { id: 'daily-9', label: 'Каждый день 09:00', expression: '0 9 * * *' },
    { id: 'every-30m', label: 'Каждые 30 минут', expression: '*/30 * * * *' },
    { id: 'custom', label: 'Своя cron-строка', expression: null },
  ],
};

export function cronPresets(locale?: AppLocale): CronPreset[] {
  return CRON_PRESETS_BY_LOCALE[normalizeAppLocale(locale)];
}

export const CRON_PRESETS: CronPreset[] = CRON_PRESETS_BY_LOCALE.ru;
