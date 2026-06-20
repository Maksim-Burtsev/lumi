import { describe, expect, it } from 'vitest';
import {
  buildTimezoneOptions,
  getTimezoneDisplay,
  sortTimezoneOptions,
  timezoneOptionMatches,
} from './timezones';

const TEST_ZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'America/Anchorage',
  'Pacific/Honolulu',
  'America/Puerto_Rico',
  'Pacific/Guam',
  'America/St_Johns',
  'Africa/Lusaka',
  'Asia/Jerusalem',
  'Europe/London',
  'Europe/Dublin',
  'Europe/Berlin',
  'Europe/Paris',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Amsterdam',
  'Europe/Warsaw',
  'Europe/Athens',
  'Asia/Bangkok',
  'Asia/Makassar',
  'Asia/Kolkata',
  'Asia/Kathmandu',
];

function matchingValues(query: string): string[] {
  return buildTimezoneOptions({
    apiTimezones: TEST_ZONES,
    browserTimezones: [],
    now: new Date('2026-06-19T12:00:00Z'),
  })
    .filter((option) => timezoneOptionMatches(option, query))
    .sort((a, b) => sortTimezoneOptions(a, b, query))
    .map((option) => option.value);
}

describe('buildTimezoneOptions', () => {
  it('searches common country and place aliases', () => {
    const usa = matchingValues('USA');
    expect(usa).toEqual(expect.arrayContaining([
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Phoenix',
      'America/Anchorage',
      'Pacific/Honolulu',
      'America/Puerto_Rico',
      'Pacific/Guam',
    ]));
    expect(usa.slice(0, 7)).toEqual([
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Phoenix',
      'America/Anchorage',
      'Pacific/Honolulu',
    ]);
    expect(usa).not.toEqual(expect.arrayContaining(['Africa/Lusaka', 'Asia/Jerusalem']));
    expect(matchingValues('California')).toContain('America/Los_Angeles');
    expect(matchingValues('Pacific')).toContain('America/Los_Angeles');
    expect(matchingValues('PT')).toContain('America/Los_Angeles');
    expect(matchingValues('US San')[0]).toBe('America/Los_Angeles');
    expect(matchingValues('USA San')[0]).toBe('America/Los_Angeles');
    expect(matchingValues('San Fran')).toEqual(['America/Los_Angeles']);
    expect(matchingValues('San Francisco')).toEqual(['America/Los_Angeles']);
    expect(matchingValues('SF')).toEqual(['America/Los_Angeles']);
    expect(matchingValues('Bay Area')).toEqual(['America/Los_Angeles']);
    expect(matchingValues('Eastern')).toContain('America/New_York');
    expect(matchingValues('US New')[0]).toBe('America/New_York');
    expect(matchingValues('NYC')).toEqual(['America/New_York']);
    expect(matchingValues('US Austin')[0]).toBe('America/Chicago');
    expect(matchingValues('LA')).toContain('America/Los_Angeles');
    expect(matchingValues('LA')).not.toContain('Africa/Lusaka');
    expect(matchingValues('Germany')).toContain('Europe/Berlin');
    expect(matchingValues('France')).toContain('Europe/Paris');
    expect(matchingValues('UK')).toContain('Europe/London');
    expect(matchingValues('Europe').slice(0, 5)).toEqual([
      'Europe/London',
      'Europe/Dublin',
      'Europe/Berlin',
      'Europe/Paris',
      'Europe/Madrid',
    ]);
    expect(matchingValues('Thailand')).toContain('Asia/Bangkok');
    expect(matchingValues('Bali')).toContain('Asia/Makassar');
    expect(matchingValues('India')).toContain('Asia/Kolkata');
    expect(matchingValues('Nepal')).toContain('Asia/Kathmandu');
  });

  it('builds friendly primary labels and exact secondary labels', () => {
    const options = buildTimezoneOptions({
      apiTimezones: ['America/Los_Angeles', 'America/St_Johns', 'Europe/Berlin'],
      browserTimezones: [],
      now: new Date('2026-06-19T12:00:00Z'),
    });

    const losAngeles = options.find((option) => option.value === 'America/Los_Angeles');
    const stJohns = options.find((option) => option.value === 'America/St_Johns');
    const berlin = options.find((option) => option.value === 'Europe/Berlin');

    expect(losAngeles?.primaryLabel).toBe('Pacific Time · Los Angeles');
    expect(losAngeles?.secondaryLabel).toBe('UTC-07:00 · America/Los_Angeles');
    expect(stJohns?.primaryLabel).toBe('Newfoundland Time · St Johns');
    expect(stJohns?.secondaryLabel).toBe('UTC-02:30 · America/St_Johns');
    expect(berlin?.primaryLabel).toBe('Central European Time · Berlin');
    expect(berlin?.secondaryLabel).toBe('UTC+02:00 · Europe/Berlin');
  });

  it('adapts the displayed city to the matching place alias', () => {
    const options = buildTimezoneOptions({
      apiTimezones: ['America/Los_Angeles'],
      browserTimezones: [],
      now: new Date('2026-06-19T12:00:00Z'),
    });
    const losAngeles = options[0];

    expect(getTimezoneDisplay(losAngeles, '').primaryLabel).toBe('Pacific Time · Los Angeles');
    expect(getTimezoneDisplay(losAngeles, '').secondaryLabel).toBe('UTC-07:00 · America/Los Angeles');
    expect(getTimezoneDisplay(losAngeles, 'USA').primaryLabel).toBe('Pacific Time · Los Angeles');
    expect(getTimezoneDisplay(losAngeles, 'San Francisco').primaryLabel).toBe('Pacific Time · San Francisco / Los Angeles');
    expect(getTimezoneDisplay(losAngeles, 'San Francisco').secondaryLabel).toBe('UTC-07:00 · America/Los Angeles');
    expect(getTimezoneDisplay(losAngeles, 'US San').primaryLabel).toBe('Pacific Time · San Francisco / Los Angeles');
  });

  it('keeps current and detected timezones first before regular sorting', () => {
    const options = buildTimezoneOptions({
      apiTimezones: ['America/Los_Angeles', 'Europe/Berlin', 'Asia/Yerevan'],
      browserTimezones: [],
      currentTimezone: 'Europe/Berlin',
      deviceTimezone: 'America/Los_Angeles',
      now: new Date('2026-06-19T12:00:00Z'),
    });

    expect(options.slice(0, 2).map((option) => option.value)).toEqual([
      'Europe/Berlin',
      'America/Los_Angeles',
    ]);
  });

  it('ranks the query match above the current timezone while searching', () => {
    const options = buildTimezoneOptions({
      apiTimezones: ['Asia/Yerevan', 'America/Los_Angeles', 'America/New_York'],
      browserTimezones: [],
      currentTimezone: 'Asia/Yerevan',
      now: new Date('2026-06-19T12:00:00Z'),
    });

    const matches = options
      .filter((option) => timezoneOptionMatches(option, 'US San'))
      .sort((a, b) => sortTimezoneOptions(a, b, 'US San'))
      .map((option) => option.value);

    expect(matches[0]).toBe('America/Los_Angeles');
  });
});
