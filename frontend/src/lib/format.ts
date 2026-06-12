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

const timeFmt = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', hour12: false });
const dayMonthFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const dayMonthTimeFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
const headingFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
const weekdayShortFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });

function capitalize(s: string): string {
  return s.length > 0 ? s[0].toUpperCase() + s.slice(1) : s;
}

/** "14:05" with tabular figures expected at render site */
export function formatTime(ts: string | Date): string {
  const d = typeof ts === 'string' ? new Date(ts) : ts;
  if (Number.isNaN(d.getTime())) return '—';
  return timeFmt.format(d);
}

export function formatTimeRange(start: string, end: string): string {
  return `${formatTime(start)}–${formatTime(end)}`;
}

/** "Вторник, 10 июня" */
export function formatDateHeading(d: Date): string {
  return capitalize(headingFmt.format(d));
}

export function isSameDay(a: Date, b: Date): boolean {
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

/** Day switcher label: "Сегодня, 10 июня" / "Завтра, 11 июня" / "Пт, 13 июня" */
export function formatDayLabel(d: Date): string {
  const today = startOfDay(new Date());
  if (isSameDay(d, today)) return `Сегодня, ${dayMonthLong(d)}`;
  if (isSameDay(d, addDays(today, 1))) return `Завтра, ${dayMonthLong(d)}`;
  if (isSameDay(d, addDays(today, -1))) return `Вчера, ${dayMonthLong(d)}`;
  return capitalize(weekdayShortFmt.format(d));
}

function dayMonthLong(d: Date): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(d);
}

/** Relative time: "только что", "2 мин назад", "вчера", "через 3 ч" … */
export function formatRelative(ts: string | null | undefined): string {
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
  if (hours < 24 && isSameDay(d, now)) return future ? `через ${countLabel(hours, ['час', 'часа', 'часов'])}` : `${hours} ч назад`;

  const today = startOfDay(now);
  if (isSameDay(d, addDays(today, -1))) return 'вчера';
  if (isSameDay(d, addDays(today, 1))) return `завтра в ${formatTime(d)}`;

  const days = Math.round(abs / 86_400_000);
  if (!future && days < 7) return `${countLabel(days, ['день', 'дня', 'дней'])} назад`;
  if (future && days < 7) return `через ${countLabel(days, ['день', 'дня', 'дней'])}`;

  return dayMonthFmt.format(d);
}

/** Due label for tasks: "Сегодня 14:00", "Завтра 09:00", "10 июн 09:00" */
export function formatDueLabel(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  const today = startOfDay(new Date());
  if (isSameDay(d, today)) return `Сегодня ${formatTime(d)}`;
  if (isSameDay(d, addDays(today, 1))) return `Завтра ${formatTime(d)}`;
  if (isSameDay(d, addDays(today, -1))) return `Вчера ${formatTime(d)}`;
  return dayMonthTimeFmt.format(d);
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
