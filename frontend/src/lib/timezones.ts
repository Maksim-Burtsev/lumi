export interface TimezoneDisplayOption {
  value: string;
  label: string;
  searchText: string;
  offsetMinutes: number;
}

const SUPPORTED_VALUES = Intl as unknown as {
  supportedValuesOf?: (input: 'timeZone') => string[];
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

export function timezoneDismissKey(profileTimezone: string, deviceTimezone: string): string {
  return `lumi-tz-dismissed:${profileTimezone}:${deviceTimezone}`;
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
    return {
      value: timezone,
      label,
      searchText: `${timezone} ${city} ${offset}`.toLowerCase(),
      offsetMinutes: offsetMinutes(offset),
    };
  }).sort((a, b) => (
    a.offsetMinutes - b.offsetMinutes
    || cityFromTimezone(a.value).localeCompare(cityFromTimezone(b.value))
    || a.value.localeCompare(b.value)
  ));
}
