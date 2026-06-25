import { describe, expect, it } from 'vitest';
import {
  formatDateHeading,
  formatDueLabel,
  formatRelative,
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

  it('formats relative time in English when locale is English', () => {
    const now = new Date();
    const threeMinutesAgo = new Date(now.getTime() - 3 * 60_000).toISOString();

    expect(formatRelative(threeMinutesAgo, { locale: 'en' })).toBe('3 min ago');
  });
});
