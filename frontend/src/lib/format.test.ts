import { describe, expect, it } from 'vitest';
import { formatTime, formatTimeRange } from './format';

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
});
