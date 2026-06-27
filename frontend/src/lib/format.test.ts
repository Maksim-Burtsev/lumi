import { describe, expect, it } from 'vitest';
import {
  formatDateHeading,
  formatDuration,
  formatDueLabel,
  formatRelative,
  formatSpanMinutes,
  formatTime,
  formatTimeRange,
  resolveTimeFormat,
} from './format';

describe('time formatting preferences', () => {
  it('formats time in the profile timezone with the selected clock format', () => {
    const ts = '2026-06-17T10:30:00Z';

    expect(formatTime(ts, { locale: 'en', timeFormat: '24h', timezone: 'Asia/Yerevan' })).toBe('14:30');
    expect(formatTime(ts, { locale: 'en', timeFormat: '12h', timezone: 'Asia/Yerevan' })).toBe('2:30 PM');
  });

  it('formats ranges with the same timezone and clock format', () => {
    expect(formatTimeRange(
      '2026-06-17T10:30:00Z',
      '2026-06-17T11:45:00Z',
      { locale: 'en', timeFormat: '12h', timezone: 'Asia/Yerevan' },
    )).toBe('2:30 PM–3:45 PM');
  });

  it('resolves automatic clock format from the regional locale', () => {
    expect(resolveTimeFormat({ locale: 'en', timeFormat: 'auto', regionalLocale: 'en-US' })).toBe('12h');
    expect(resolveTimeFormat({ locale: 'en', timeFormat: 'auto', regionalLocale: 'en-GB' })).toBe('24h');
  });

  it('formats English dates with US and European regional ordering', () => {
    const friday = new Date('2026-06-19T12:00:00Z');

    expect(formatDateHeading(friday, { locale: 'en', regionalLocale: 'en-US' })).toBe('Friday, June 19');
    expect(formatDateHeading(friday, { locale: 'en', regionalLocale: 'en-GB' })).toBe('Friday 19 June');
  });

  it('formats English due labels with regional date ordering', () => {
    const ts = '2026-08-19T14:30:00Z';

    expect(formatDueLabel(ts, {
      locale: 'en',
      regionalLocale: 'en-US',
      timeFormat: '12h',
      timezone: 'UTC',
    })).toBe('Aug 19, 2:30 PM');
    expect(formatDueLabel(ts, {
      locale: 'en',
      regionalLocale: 'en-GB',
      timeFormat: '24h',
      timezone: 'UTC',
    })).toBe('19 Aug, 14:30');
  });

  it('formats relative time in English and Russian', () => {
    const now = new Date('2026-06-17T12:00:00Z');
    expect(formatRelative('2026-06-17T11:58:00Z', { locale: 'en', now })).toBe('2 min ago');
    expect(formatRelative('2026-06-17T11:58:00Z', { locale: 'ru', now })).toBe('2 мин назад');
    expect(formatRelative('2026-06-18T12:00:00Z', { locale: 'en', now, timeFormat: '24h', timezone: 'UTC' })).toBe('tomorrow at 12:00');
    expect(formatRelative('2026-06-18T12:00:00Z', { locale: 'ru', now, timeFormat: '24h', timezone: 'UTC' })).toBe('завтра в 12:00');
  });

  it('formats durations and spans in the selected locale', () => {
    expect(formatDuration(1234, 'en')).toBe('1.2 sec');
    expect(formatDuration(1234, 'ru')).toBe('1,2 с');
    expect(formatDuration(125_000, 'en')).toBe('2 min 05 sec');
    expect(formatDuration(125_000, 'ru')).toBe('2 мин 05 с');

    expect(formatSpanMinutes('2026-06-17T11:00:00Z', '2026-06-17T12:30:00Z', 'en')).toBe('1 h 30 min');
    expect(formatSpanMinutes('2026-06-17T11:00:00Z', '2026-06-17T12:30:00Z', 'ru')).toBe('1 ч 30 мин');
  });
});
