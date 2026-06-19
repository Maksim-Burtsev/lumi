export interface TimezoneDisplayOption {
  value: string;
  label: string;
  primaryLabel: string;
  secondaryLabel: string;
  searchText: string;
  offsetMinutes: number;
  selectionPriority: number;
}

const SUPPORTED_VALUES = Intl as unknown as {
  supportedValuesOf?: (input: 'timeZone') => string[];
};

interface TimezoneMeta {
  name?: string;
  aliases: string[];
  usRank?: number;
  europeRank?: number;
}

const US_ALIASES = ['USA', 'US', 'United States', 'America'];
const EUROPE_ALIASES = ['Europe', 'European', 'EU'];

const TIMEZONE_META: Record<string, TimezoneMeta> = {
  'America/New_York': {
    name: 'Eastern Time',
    aliases: [...US_ALIASES, 'New York', 'NYC', 'Eastern', 'ET', 'EST', 'EDT', 'Boston', 'Washington DC', 'DC', 'Miami', 'Atlanta', 'Philadelphia'],
    usRank: 0,
  },
  'America/Chicago': {
    name: 'Central Time',
    aliases: [...US_ALIASES, 'Chicago', 'Texas', 'Central', 'CT', 'CST', 'CDT', 'Dallas', 'Austin', 'Houston', 'New Orleans', 'Minneapolis', 'Kansas City'],
    usRank: 1,
  },
  'America/Denver': {
    name: 'Mountain Time',
    aliases: [...US_ALIASES, 'Denver', 'Colorado', 'Mountain', 'MT', 'MST', 'MDT', 'Salt Lake City'],
    usRank: 2,
  },
  'America/Los_Angeles': {
    name: 'Pacific Time',
    aliases: [...US_ALIASES, 'Pacific', 'PT', 'PST', 'PDT', 'California', 'LA', 'Los Angeles', 'San Francisco', 'SF', 'Seattle', 'Portland', 'San Diego', 'Las Vegas'],
    usRank: 3,
  },
  'America/Phoenix': {
    name: 'Arizona Time',
    aliases: [...US_ALIASES, 'Arizona', 'Phoenix', 'MST'],
    usRank: 4,
  },
  'America/Anchorage': {
    name: 'Alaska Time',
    aliases: [...US_ALIASES, 'Alaska', 'Anchorage'],
    usRank: 5,
  },
  'America/Adak': {
    name: 'Hawaii-Aleutian Time',
    aliases: [...US_ALIASES, 'Adak', 'Aleutian'],
    usRank: 6,
  },
  'Pacific/Honolulu': {
    name: 'Hawaii Time',
    aliases: [...US_ALIASES, 'Hawaii', 'Honolulu', 'HST'],
    usRank: 7,
  },
  'America/Puerto_Rico': {
    name: 'Atlantic Time',
    aliases: [...US_ALIASES, 'Puerto Rico', 'San Juan', 'AST'],
    usRank: 8,
  },
  'America/St_Thomas': {
    name: 'Atlantic Time',
    aliases: [...US_ALIASES, 'US Virgin Islands', 'Virgin Islands', 'St Thomas', 'AST'],
    usRank: 9,
  },
  'Pacific/Guam': {
    name: 'Chamorro Time',
    aliases: [...US_ALIASES, 'Guam', 'Chamorro', 'ChST'],
    usRank: 10,
  },
  'Pacific/Saipan': {
    name: 'Chamorro Time',
    aliases: [...US_ALIASES, 'Northern Mariana Islands', 'Saipan', 'Chamorro', 'ChST'],
    usRank: 11,
  },
  'Pacific/Pago_Pago': {
    name: 'Samoa Time',
    aliases: [...US_ALIASES, 'American Samoa', 'Pago Pago', 'SST'],
    usRank: 12,
  },
  'America/St_Johns': {
    name: 'Newfoundland Time',
    aliases: ['Canada', 'Newfoundland', 'St Johns', 'St John’s', 'NST', 'NDT'],
  },
  'Europe/London': {
    name: 'UK Time',
    aliases: [...EUROPE_ALIASES, 'UK', 'Britain', 'United Kingdom', 'England', 'London'],
    europeRank: 0,
  },
  'Europe/Dublin': {
    name: 'Irish Time',
    aliases: [...EUROPE_ALIASES, 'Ireland', 'Dublin'],
    europeRank: 1,
  },
  'Europe/Lisbon': {
    name: 'Western European Time',
    aliases: [...EUROPE_ALIASES, 'Portugal', 'Lisbon', 'WET', 'WEST'],
    europeRank: 2,
  },
  'Europe/Berlin': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Germany', 'Berlin', 'CET', 'CEST'],
    europeRank: 3,
  },
  'Europe/Paris': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'France', 'Paris', 'CET', 'CEST'],
    europeRank: 4,
  },
  'Europe/Madrid': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Spain', 'Madrid', 'CET', 'CEST'],
    europeRank: 5,
  },
  'Europe/Rome': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Italy', 'Rome', 'CET', 'CEST'],
    europeRank: 6,
  },
  'Europe/Amsterdam': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Netherlands', 'Amsterdam', 'CET', 'CEST'],
    europeRank: 7,
  },
  'Europe/Brussels': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Belgium', 'Brussels', 'CET', 'CEST'],
    europeRank: 8,
  },
  'Europe/Zurich': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Switzerland', 'Zurich', 'CET', 'CEST'],
    europeRank: 9,
  },
  'Europe/Vienna': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Austria', 'Vienna', 'CET', 'CEST'],
    europeRank: 10,
  },
  'Europe/Prague': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Czechia', 'Czech Republic', 'Prague', 'CET', 'CEST'],
    europeRank: 11,
  },
  'Europe/Warsaw': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Poland', 'Warsaw', 'CET', 'CEST'],
    europeRank: 12,
  },
  'Europe/Stockholm': {
    name: 'Central European Time',
    aliases: [...EUROPE_ALIASES, 'Sweden', 'Stockholm', 'CET', 'CEST'],
    europeRank: 13,
  },
  'Europe/Athens': {
    name: 'Eastern European Time',
    aliases: [...EUROPE_ALIASES, 'Greece', 'Athens', 'EET', 'EEST'],
    europeRank: 20,
  },
  'Europe/Helsinki': {
    name: 'Eastern European Time',
    aliases: [...EUROPE_ALIASES, 'Finland', 'Helsinki', 'EET', 'EEST'],
    europeRank: 21,
  },
  'Europe/Kyiv': {
    name: 'Eastern European Time',
    aliases: [...EUROPE_ALIASES, 'Ukraine', 'Kyiv', 'Kiev', 'EET', 'EEST'],
    europeRank: 22,
  },
  'Europe/Istanbul': {
    name: 'Turkey Time',
    aliases: [...EUROPE_ALIASES, 'Turkey', 'Türkiye', 'Istanbul'],
    europeRank: 30,
  },
  'Asia/Bangkok': { aliases: ['Thailand', 'Thai', 'Bangkok'] },
  'Asia/Makassar': { aliases: ['Bali', 'Denpasar', 'Makassar'] },
  'Asia/Kolkata': { aliases: ['India', 'Delhi', 'Mumbai', 'Bangalore', 'Kolkata'] },
  'Asia/Kathmandu': { aliases: ['Nepal', 'Kathmandu'] },
  'Asia/Dubai': { aliases: ['UAE', 'Dubai', 'Abu Dhabi', 'United Arab Emirates'] },
  'Asia/Yerevan': { aliases: ['Armenia', 'Yerevan'] },
  'Asia/Tokyo': { aliases: ['Japan', 'Tokyo'] },
  'Asia/Seoul': { aliases: ['Korea', 'South Korea', 'Seoul'] },
  'Asia/Shanghai': { aliases: ['China', 'Beijing', 'Shanghai'] },
  'Asia/Singapore': { aliases: ['Singapore'] },
  'Australia/Sydney': { aliases: ['Australia', 'Sydney'] },
  'Australia/Melbourne': { aliases: ['Australia', 'Melbourne'] },
  'Pacific/Auckland': { aliases: ['New Zealand', 'Auckland'] },
  'Pacific/Chatham': { aliases: ['New Zealand', 'Chatham'] },
  'America/Toronto': { aliases: ['Canada', 'Toronto'] },
  'America/Vancouver': { aliases: ['Canada', 'Vancouver'] },
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

function formatOffset(minutes: number): string {
  const sign = minutes < 0 ? '-' : '+';
  const abs = Math.abs(minutes);
  const hours = Math.floor(abs / 60);
  const mins = abs % 60;
  return `UTC${sign}${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
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
    if (value === 'GMT') return formatOffset(0);
    const match = value.match(/^GMT([+-])(\d{1,2})(?::(\d{2}))?$/);
    if (!match) return formatOffset(0);
    const sign = match[1] === '-' ? -1 : 1;
    return formatOffset(sign * (Number(match[2]) * 60 + Number(match[3] ?? 0)));
  } catch {
    return formatOffset(0);
  }
}

function offsetMinutes(offset: string): number {
  const match = offset.match(/^UTC([+-])(\d{1,2})(?::(\d{2}))?$/);
  if (!match) return 0;
  const sign = match[1] === '-' ? -1 : 1;
  return sign * (Number(match[2]) * 60 + Number(match[3] ?? 0));
}

function primaryLabel(timezone: string, city: string): string {
  const name = TIMEZONE_META[timezone]?.name;
  return name ? `${name} · ${city}` : city;
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

function queryRank(option: TimezoneDisplayOption, query: string): number {
  const tokens = tokenizeSearchText(query);
  const meta = TIMEZONE_META[option.value];
  if (tokens.some((token) => token === 'usa' || token === 'us' || token === 'america')) {
    return meta?.usRank ?? 10_000;
  }
  if (tokens.some((token) => token === 'europe' || token === 'european' || token === 'eu')) {
    return meta?.europeRank ?? 10_000;
  }
  return 10_000;
}

export function sortTimezoneOptions(
  a: TimezoneDisplayOption,
  b: TimezoneDisplayOption,
  query = '',
): number {
  const aQueryRank = queryRank(a, query);
  const bQueryRank = queryRank(b, query);
  return (
    a.selectionPriority - b.selectionPriority
    || aQueryRank - bQueryRank
    || a.offsetMinutes - b.offsetMinutes
    || cityFromTimezone(a.value).localeCompare(cityFromTimezone(b.value))
    || a.value.localeCompare(b.value)
  );
}

export function buildTimezoneOptions(params: {
  apiTimezones?: string[];
  browserTimezones?: string[];
  extraTimezones?: Array<string | null | undefined>;
  currentTimezone?: string | null;
  deviceTimezone?: string | null;
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
    const primary = primaryLabel(timezone, city);
    const secondary = `${offset} · ${timezone}`;
    const label = `${primary} · ${secondary}`;
    const aliases = TIMEZONE_META[timezone]?.aliases ?? [];
    const selectionPriority = timezone === params.currentTimezone
      ? 0
      : timezone === params.deviceTimezone
        ? 1
        : 2;
    return {
      value: timezone,
      label,
      primaryLabel: primary,
      secondaryLabel: secondary,
      searchText: `${timezone} ${city} ${offset} ${aliases.join(' ')}`.toLowerCase(),
      offsetMinutes: offsetMinutes(offset),
      selectionPriority,
    };
  }).sort(sortTimezoneOptions);
}
