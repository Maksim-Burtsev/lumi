/** Small cron humanizer for common patterns; falls back to the raw expression. */

const DOW_PLURAL: Record<number, string> = {
  0: 'воскресеньям',
  1: 'понедельникам',
  2: 'вторникам',
  3: 'средам',
  4: 'четвергам',
  5: 'пятницам',
  6: 'субботам',
  7: 'воскресеньям',
};

const DOW_SHORT: Record<number, string> = {
  0: 'Вс',
  1: 'Пн',
  2: 'Вт',
  3: 'Ср',
  4: 'Чт',
  5: 'Пт',
  6: 'Сб',
  7: 'Вс',
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

export function humanizeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [min, hour, dom, mon, dow] = parts;

  // Anything with restricted day-of-month or month → raw
  if (dom !== '*' || mon !== '*') return expr;

  // * * * * *
  if (min === '*' && hour === '*' && dow === '*') return 'Каждую минуту';

  // */N * * * *
  const everyMin = parseEveryN(min);
  if (everyMin !== null && hour === '*' && dow === '*') {
    if (everyMin === 1) return 'Каждую минуту';
    const word = everyMin % 10 === 1 && everyMin % 100 !== 11 ? 'минуту' : everyMin % 10 >= 2 && everyMin % 10 <= 4 && (everyMin % 100 < 12 || everyMin % 100 > 14) ? 'минуты' : 'минут';
    return `Каждые ${everyMin} ${word}`;
  }

  // M */N * * *
  const everyHour = parseEveryN(hour);
  if (isNum(min) && everyHour !== null && dow === '*') {
    if (everyHour === 1) return 'Каждый час';
    const word = everyHour % 10 >= 2 && everyHour % 10 <= 4 && (everyHour % 100 < 12 || everyHour % 100 > 14) ? 'часа' : 'часов';
    return `Каждые ${everyHour} ${word}`;
  }

  // M * * * *
  if (isNum(min) && hour === '*' && dow === '*') {
    return `Каждый час в :${String(parseInt(min, 10)).padStart(2, '0')}`;
  }

  if (!isNum(min) || !isNum(hour)) return expr;
  const t = timeLabel(parseInt(min, 10), parseInt(hour, 10));

  if (dow === '*') return `Каждый день ${t}`;
  if (dow === '1-5') return `Будни ${t}`;
  if (dow === '6,0' || dow === '0,6' || dow === '6,7' || dow === '6-7') return `Выходные ${t}`;

  if (isNum(dow)) {
    const d = parseInt(dow, 10);
    const name = DOW_PLURAL[d];
    if (name) return `По ${name} ${t}`;
  }

  if (/^[0-7](,[0-7])+$/.test(dow)) {
    const names = dow
      .split(',')
      .map((s) => DOW_SHORT[parseInt(s, 10)])
      .filter((s): s is string => Boolean(s));
    if (names.length > 0) return `${names.join(', ')} · ${t}`;
  }

  return expr;
}

export interface CronPreset {
  id: string;
  label: string;
  expression: string | null; // null → custom input
}

export const CRON_PRESETS: CronPreset[] = [
  { id: 'morning-8', label: 'Каждое утро 08:00', expression: '0 8 * * *' },
  { id: 'weekday-morning', label: 'Каждое утро 08:30, будни', expression: '30 8 * * 1-5' },
  { id: 'daily-9', label: 'Каждый день 09:00', expression: '0 9 * * *' },
  { id: 'every-30m', label: 'Каждые 30 минут', expression: '*/30 * * * *' },
  { id: 'custom', label: 'Своя cron-строка', expression: null },
];
