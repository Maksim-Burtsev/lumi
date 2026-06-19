import { describe, expect, it } from 'vitest';
import { buildTimezoneOptions, timezoneOptionMatches } from './timezones';

const TEST_ZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'America/St_Johns',
  'Africa/Lusaka',
  'Asia/Jerusalem',
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
    .map((option) => option.value);
}

describe('buildTimezoneOptions', () => {
  it('searches common country and place aliases', () => {
    expect(matchingValues('USA')).toEqual(expect.arrayContaining([
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Anchorage',
      'Pacific/Honolulu',
    ]));
    expect(matchingValues('USA')).not.toEqual(expect.arrayContaining(['Africa/Lusaka', 'Asia/Jerusalem']));
    expect(matchingValues('California')).toContain('America/Los_Angeles');
    expect(matchingValues('LA')).toContain('America/Los_Angeles');
    expect(matchingValues('LA')).not.toContain('Africa/Lusaka');
    expect(matchingValues('Thailand')).toContain('Asia/Bangkok');
    expect(matchingValues('Bali')).toContain('Asia/Makassar');
    expect(matchingValues('India')).toContain('Asia/Kolkata');
    expect(matchingValues('Nepal')).toContain('Asia/Kathmandu');
  });

  it('keeps readable city labels free of underscores', () => {
    const options = buildTimezoneOptions({
      apiTimezones: ['America/Los_Angeles', 'America/St_Johns'],
      browserTimezones: [],
      now: new Date('2026-06-19T12:00:00Z'),
    });

    const losAngeles = options.find((option) => option.value === 'America/Los_Angeles');
    const stJohns = options.find((option) => option.value === 'America/St_Johns');

    expect(losAngeles?.label).toContain('Los Angeles · America/Los_Angeles');
    expect(stJohns?.label).toContain('St Johns · America/St_Johns');
  });
});
