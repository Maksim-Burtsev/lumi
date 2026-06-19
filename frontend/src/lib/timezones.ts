export interface TimezoneDisplayOption {
  value: string;
  label: string;
  searchText: string;
  offsetMinutes: number;
}

const SUPPORTED_VALUES = Intl as unknown as {
  supportedValuesOf?: (input: 'timeZone') => string[];
};

const TIMEZONE_ALIASES: Record<string, string[]> = {
  'America/New_York': ['USA', 'US', 'United States', 'America', 'NYC', 'New York', 'Eastern', 'EST', 'EDT'],
  'America/Chicago': ['USA', 'US', 'United States', 'America', 'Chicago', 'Texas', 'Central', 'CST', 'CDT'],
  'America/Denver': ['USA', 'US', 'United States', 'America', 'Denver', 'Colorado', 'Mountain', 'MST', 'MDT'],
  'America/Los_Angeles': [
    'USA',
    'US',
    'United States',
    'America',
    'California',
    'LA',
    'Los Angeles',
    'San Francisco',
    'SF',
  ],
  'America/Anchorage': ['USA', 'US', 'United States', 'America', 'Alaska', 'Anchorage'],
  'Pacific/Honolulu': ['USA', 'US', 'United States', 'America', 'Hawaii', 'Honolulu'],
  'America/Phoenix': ['USA', 'US', 'United States', 'America', 'Arizona', 'Phoenix', 'MST'],
  'Asia/Bangkok': ['Thailand', 'Thai', 'Bangkok'],
  'Asia/Makassar': ['Bali', 'Denpasar', 'Makassar'],
  'Asia/Kolkata': ['India', 'Delhi', 'Mumbai', 'Bangalore', 'Kolkata'],
  'Asia/Kathmandu': ['Nepal', 'Kathmandu'],
  'Asia/Dubai': ['UAE', 'Dubai', 'Abu Dhabi', 'United Arab Emirates'],
  'Asia/Yerevan': ['Armenia', 'Yerevan'],
  'Europe/London': ['UK', 'Britain', 'United Kingdom', 'London'],
  'Europe/Paris': ['France', 'Paris'],
  'Europe/Berlin': ['Germany', 'Berlin'],
  'Asia/Tokyo': ['Japan', 'Tokyo'],
  'Asia/Seoul': ['Korea', 'South Korea', 'Seoul'],
  'Asia/Shanghai': ['China', 'Beijing', 'Shanghai'],
  'Asia/Singapore': ['Singapore'],
  'Australia/Sydney': ['Australia', 'Sydney'],
  'Australia/Melbourne': ['Australia', 'Melbourne'],
  'Pacific/Auckland': ['New Zealand', 'Auckland'],
  'Pacific/Chatham': ['New Zealand', 'Chatham'],
  'America/Toronto': ['Canada', 'Toronto'],
  'America/Vancouver': ['Canada', 'Vancouver'],
};

export function getDeviceTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

export function getBrowserTimezones(): string[] {
  try {
    return SUPPORTED_VALUES.supportedValuesOf?.('timeZone') ?? [];
  } catch {
    return [];
  }
}

function cityFromTimezone(timezone: string): string {
  const last = timezone.split('/').pop() ?? timezone;
  return last.replace(/_/g, ' ');
}

function offsetName(timezone: string, now: Date): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'shortOffset',
      hour: '2-digit',
      minute: '2-digit',
    }).formatToParts(now);
    const value = parts.find((part) => part.type === 'timeZoneName')?.value ?? 'GMT';
    return value === 'GMT' ? 'UTC' : value.replace('GMT', 'UTC');
  } catch {
    return 'UTC';
  }
}

function offsetMinutes(offset: string): number {
  if (offset === 'UTC') return 0;
  const match = offset.match(/^UTC([+-])(\d{1,2})(?::(\d{2}))?$/);
  if (!match) return 0;
  const sign = match[1] === '-' ? -1 : 1;
  return sign * (Number(match[2]) * 60 + Number(match[3] ?? 0));
}

function tokenizeSearchText(value: string): string[] {
  return value
    .toLowerCase()
    .replace(/[_/-]/g, ' ')
    .split(/[^a-z0-9:+]+/)
    .filter(Boolean);
}

export function timezoneDismissKey(profileTimezone: string, deviceTimezone: string): string {
  return `lumi-tz-dismissed:${profileTimezone}:${deviceTimezone}`;
}

export function timezoneOptionMatches(option: TimezoneDisplayOption, query: string): boolean {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;
  if (normalizedQuery.length <= 3) {
    return tokenizeSearchText(option.searchText).some((token) => token === normalizedQuery);
  }
  return option.searchText.includes(normalizedQuery);
}

export function buildTimezoneOptions(params: {
  apiTimezones?: string[];
  browserTimezones?: string[];
  extraTimezones?: Array<string | null | undefined>;
  now?: Date;
}): TimezoneDisplayOption[] {
  const source = params.browserTimezones?.length ? params.browserTimezones : params.apiTimezones ?? [];
  const zones = new Set(source);
  zones.add('UTC');
  for (const tz of params.extraTimezones ?? []) {
    if (tz) zones.add(tz);
  }
  const now = params.now ?? new Date();
  return [...zones].map((timezone) => {
    const offset = offsetName(timezone, now);
    const city = cityFromTimezone(timezone);
    const label = `(${offset}) ${city} · ${timezone}`;
    const aliases = TIMEZONE_ALIASES[timezone] ?? [];
    return {
      value: timezone,
      label,
      searchText: `${timezone} ${city} ${offset} ${aliases.join(' ')}`.toLowerCase(),
      offsetMinutes: offsetMinutes(offset),
    };
  }).sort((a, b) => (
    a.offsetMinutes - b.offsetMinutes
    || cityFromTimezone(a.value).localeCompare(cityFromTimezone(b.value))
    || a.value.localeCompare(b.value)
  ));
}
