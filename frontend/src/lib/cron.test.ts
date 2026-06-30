import { describe, expect, it } from 'vitest';
import { cronPresets, humanizeCron } from './cron';

describe('localized cron labels', () => {
  it('humanizes common schedules in English', () => {
    expect(humanizeCron('* * * * *', 'en')).toBe('Every minute');
    expect(humanizeCron('*/30 * * * *', 'en')).toBe('Every 30 minutes');
    expect(humanizeCron('0 8 * * *', 'en')).toBe('Every day 08:00');
    expect(humanizeCron('30 8 * * 1-5', 'en')).toBe('Weekdays 08:30');
    expect(humanizeCron('15 9 * * 1', 'en')).toBe('Mondays 09:15');
  });

  it('falls back to English for unsupported Russian locale input', () => {
    expect(humanizeCron('* * * * *', 'ru')).toBe('Every minute');
    expect(humanizeCron('*/30 * * * *', 'ru')).toBe('Every 30 minutes');
    expect(humanizeCron('0 8 * * *', 'ru')).toBe('Every day 08:00');
    expect(humanizeCron('30 8 * * 1-5', 'ru')).toBe('Weekdays 08:30');
    expect(humanizeCron('15 9 * * 1', 'ru')).toBe('Mondays 09:15');
  });

  it('localizes preset labels without changing expressions', () => {
    expect(cronPresets('en')[0]).toEqual({ id: 'morning-8', label: 'Every morning 08:00', expression: '0 8 * * *' });
    expect(cronPresets('ru')[0]).toEqual({ id: 'morning-8', label: 'Every morning 08:00', expression: '0 8 * * *' });
  });
});
