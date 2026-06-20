export interface TimezoneDisplayOption {
  value: string;
  label: string;
  primaryLabel: string;
  secondaryLabel: string;
  searchText: string;
  offsetMinutes: number;
  selectionPriority: number;
  chips: string[];
  searchEntries: TimezoneSearchEntry[];
}

export interface TimezoneSearchEntry {
  text: string;
  tokens: string[];
  kind: 'timezone' | 'label' | 'city' | 'country' | 'region' | 'abbreviation' | 'offset' | 'alias';
  rank: number;
  displayLabel?: string;
}

export interface TimezoneRenderedDisplay {
  primaryLabel: string;
  secondaryLabel: string;
  chips: string[];
}

const SUPPORTED_VALUES = Intl as unknown as {
  supportedValuesOf?: (input: 'timeZone') => string[];
};

interface TimezoneAliasSpec {
  value: string;
  display?: string;
  rank?: number;
}

type TimezoneAlias = string | TimezoneAliasSpec;

interface TimezoneMeta {
  name?: string;
  aliases?: TimezoneAlias[];
  cities?: TimezoneAlias[];
  countryAliases?: TimezoneAlias[];
  regionAliases?: TimezoneAlias[];
  abbreviations?: TimezoneAlias[];
  chips?: string[];
  usRank?: number;
  europeRank?: number;
}

const US_ALIASES = ['USA', 'US', 'United States', 'America'];
const EUROPE_ALIASES = ['Europe', 'European', 'EU'];
const US_QUERY_TOKENS = new Set(['usa', 'us', 'america', 'united', 'states']);
const EUROPE_QUERY_TOKENS = new Set(['europe', 'european', 'eu']);
const GENERIC_QUERY_TOKENS = new Set([...US_QUERY_TOKENS, ...EUROPE_QUERY_TOKENS]);
const CANONICAL_TIMEZONE_ALIASES: Record<string, string> = {
  'Asia/Katmandu': 'Asia/Kathmandu',
};

function canonicalizeTimezone(timezone: string): string {
  return CANONICAL_TIMEZONE_ALIASES[timezone] ?? timezone;
}

const TIMEZONE_META: Record<string, TimezoneMeta> = {
  'America/New_York': {
    name: 'Eastern Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Eastern'],
    abbreviations: ['ET', 'EST', 'EDT', { value: 'NYC', display: 'New York', rank: -8 }],
    cities: [
      'New York',
      { value: 'Boston', display: 'Boston / New York', rank: 1 },
      { value: 'Washington DC', display: 'Washington DC / New York', rank: 1 },
      { value: 'DC', display: 'Washington DC / New York', rank: 2 },
      { value: 'Miami', display: 'Miami / New York', rank: 2 },
      { value: 'Atlanta', display: 'Atlanta / New York', rank: 2 },
      { value: 'Philadelphia', display: 'Philadelphia / New York', rank: 2 },
    ],
    chips: ['USA', 'ET'],
    usRank: 0,
  },
  'America/Chicago': {
    name: 'Central Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Central', 'Texas', 'Midwest'],
    abbreviations: ['CT', 'CST', 'CDT'],
    cities: [
      'Chicago',
      { value: 'Austin', display: 'Austin / Chicago', rank: -4 },
      { value: 'Dallas', display: 'Dallas / Chicago', rank: -2 },
      { value: 'Houston', display: 'Houston / Chicago', rank: -2 },
      { value: 'New Orleans', display: 'New Orleans / Chicago', rank: 6 },
      { value: 'Minneapolis', display: 'Minneapolis / Chicago', rank: 2 },
      { value: 'Kansas City', display: 'Kansas City / Chicago', rank: 2 },
    ],
    chips: ['USA', 'CT'],
    usRank: 1,
  },
  'America/Denver': {
    name: 'Mountain Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Mountain', 'Colorado', 'Utah'],
    abbreviations: ['MT', 'MST', 'MDT'],
    cities: ['Denver', { value: 'Salt Lake City', display: 'Salt Lake City / Denver', rank: 1 }],
    chips: ['USA', 'MT'],
    usRank: 2,
  },
  'America/Los_Angeles': {
    name: 'Pacific Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Pacific', 'California', 'Bay Area', 'West Coast'],
    abbreviations: [
      'PT',
      'PST',
      'PDT',
      { value: 'LA', display: 'Los Angeles', rank: -6 },
      { value: 'SF', display: 'San Francisco / Los Angeles', rank: -8 },
      { value: 'SFO', display: 'San Francisco / Los Angeles', rank: -7 },
    ],
    cities: [
      'Los Angeles',
      { value: 'San Francisco', display: 'San Francisco / Los Angeles', rank: -10 },
      { value: 'San Fran', display: 'San Francisco / Los Angeles', rank: -9 },
      { value: 'San Diego', display: 'San Diego / Los Angeles', rank: 1 },
      { value: 'Seattle', display: 'Seattle / Los Angeles', rank: 2 },
      { value: 'Portland', display: 'Portland / Los Angeles', rank: 2 },
      { value: 'Las Vegas', display: 'Las Vegas / Los Angeles', rank: 3 },
    ],
    chips: ['USA', 'PT', 'California'],
    usRank: 3,
  },
  'America/Phoenix': {
    name: 'Arizona Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Arizona'],
    abbreviations: ['MST'],
    cities: ['Phoenix'],
    chips: ['USA', 'MST'],
    usRank: 4,
  },
  'America/Anchorage': {
    name: 'Alaska Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Alaska'],
    cities: ['Anchorage'],
    chips: ['USA', 'AKT'],
    usRank: 5,
  },
  'America/Adak': {
    name: 'Hawaii-Aleutian Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Aleutian'],
    cities: ['Adak'],
    chips: ['USA'],
    usRank: 6,
  },
  'Pacific/Honolulu': {
    name: 'Hawaii Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Hawaii'],
    abbreviations: ['HST'],
    cities: ['Honolulu'],
    chips: ['USA', 'HST'],
    usRank: 7,
  },
  'America/Puerto_Rico': {
    name: 'Atlantic Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Puerto Rico'],
    abbreviations: ['AST'],
    cities: [{ value: 'San Juan', display: 'San Juan / Puerto Rico', rank: 3 }],
    chips: ['USA', 'AST'],
    usRank: 8,
  },
  'America/St_Thomas': {
    name: 'Atlantic Time',
    countryAliases: US_ALIASES,
    regionAliases: ['US Virgin Islands', 'Virgin Islands'],
    abbreviations: ['AST'],
    cities: ['St Thomas'],
    chips: ['USA', 'AST'],
    usRank: 9,
  },
  'Pacific/Guam': {
    name: 'Chamorro Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Guam', 'Chamorro'],
    abbreviations: ['ChST'],
    cities: ['Guam'],
    chips: ['USA', 'ChST'],
    usRank: 10,
  },
  'Pacific/Saipan': {
    name: 'Chamorro Time',
    countryAliases: US_ALIASES,
    regionAliases: ['Northern Mariana Islands', 'Chamorro'],
    abbreviations: ['ChST'],
    cities: ['Saipan'],
    chips: ['USA', 'ChST'],
    usRank: 11,
  },
  'Pacific/Pago_Pago': {
    name: 'Samoa Time',
    countryAliases: US_ALIASES,
    regionAliases: ['American Samoa'],
    abbreviations: ['SST'],
    cities: ['Pago Pago'],
    chips: ['USA', 'SST'],
    usRank: 12,
  },
  'America/St_Johns': {
    name: 'Newfoundland Time',
    countryAliases: ['Canada'],
    regionAliases: ['Newfoundland'],
    abbreviations: ['NST', 'NDT'],
    cities: ['St Johns', 'St John’s'],
    chips: ['Canada', 'NST'],
  },
  'Europe/London': {
    name: 'UK Time',
    countryAliases: ['UK', 'Britain', 'United Kingdom', 'England'],
    regionAliases: EUROPE_ALIASES,
    cities: ['London'],
    chips: ['UK'],
    europeRank: 0,
  },
  'Europe/Dublin': {
    name: 'Irish Time',
    countryAliases: ['Ireland'],
    regionAliases: EUROPE_ALIASES,
    cities: ['Dublin'],
    chips: ['Ireland'],
    europeRank: 1,
  },
  'Europe/Lisbon': {
    name: 'Western European Time',
    countryAliases: ['Portugal'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['WET', 'WEST'],
    cities: ['Lisbon'],
    chips: ['Portugal'],
    europeRank: 2,
  },
  'Europe/Berlin': {
    name: 'Central European Time',
    countryAliases: ['Germany'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Berlin'],
    chips: ['Germany', 'CET'],
    europeRank: 3,
  },
  'Europe/Paris': {
    name: 'Central European Time',
    countryAliases: ['France'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Paris'],
    chips: ['France', 'CET'],
    europeRank: 4,
  },
  'Europe/Madrid': {
    name: 'Central European Time',
    countryAliases: ['Spain'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Madrid'],
    chips: ['Spain', 'CET'],
    europeRank: 5,
  },
  'Europe/Rome': {
    name: 'Central European Time',
    countryAliases: ['Italy'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Rome'],
    chips: ['Italy', 'CET'],
    europeRank: 6,
  },
  'Europe/Amsterdam': {
    name: 'Central European Time',
    countryAliases: ['Netherlands'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Amsterdam'],
    europeRank: 7,
  },
  'Europe/Brussels': {
    name: 'Central European Time',
    countryAliases: ['Belgium'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Brussels'],
    europeRank: 8,
  },
  'Europe/Zurich': {
    name: 'Central European Time',
    countryAliases: ['Switzerland'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Zurich'],
    europeRank: 9,
  },
  'Europe/Vienna': {
    name: 'Central European Time',
    countryAliases: ['Austria'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Vienna'],
    europeRank: 10,
  },
  'Europe/Prague': {
    name: 'Central European Time',
    countryAliases: ['Czechia', 'Czech Republic'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Prague'],
    europeRank: 11,
  },
  'Europe/Warsaw': {
    name: 'Central European Time',
    countryAliases: ['Poland'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Warsaw'],
    europeRank: 12,
  },
  'Europe/Stockholm': {
    name: 'Central European Time',
    countryAliases: ['Sweden'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['CET', 'CEST'],
    cities: ['Stockholm'],
    europeRank: 13,
  },
  'Europe/Athens': {
    name: 'Eastern European Time',
    countryAliases: ['Greece'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['EET', 'EEST'],
    cities: ['Athens'],
    europeRank: 20,
  },
  'Europe/Helsinki': {
    name: 'Eastern European Time',
    countryAliases: ['Finland'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['EET', 'EEST'],
    cities: ['Helsinki'],
    europeRank: 21,
  },
  'Europe/Kyiv': {
    name: 'Eastern European Time',
    countryAliases: ['Ukraine'],
    regionAliases: EUROPE_ALIASES,
    abbreviations: ['EET', 'EEST'],
    cities: ['Kyiv', 'Kiev'],
    europeRank: 22,
  },
  'Europe/Istanbul': {
    name: 'Turkey Time',
    countryAliases: ['Turkey', 'Türkiye'],
    regionAliases: EUROPE_ALIASES,
    cities: ['Istanbul'],
    europeRank: 30,
  },
  'Asia/Bangkok': { countryAliases: ['Thailand', 'Thai'], cities: ['Bangkok'], chips: ['Thailand'] },
  'Asia/Makassar': {
    countryAliases: ['Indonesia'],
    cities: [
      'Makassar',
      { value: 'Bali', display: 'Bali / Makassar', rank: -6 },
      { value: 'Denpasar', display: 'Bali / Makassar', rank: -5 },
    ],
    chips: ['Indonesia', 'Bali'],
  },
  'Asia/Kolkata': { countryAliases: ['India'], cities: ['Kolkata', 'Delhi', 'Mumbai', 'Bangalore'], chips: ['India'] },
  'Asia/Kathmandu': { countryAliases: ['Nepal'], cities: ['Kathmandu'], chips: ['Nepal'] },
  'Asia/Dubai': { countryAliases: ['UAE', 'United Arab Emirates'], cities: ['Dubai', 'Abu Dhabi'], chips: ['UAE'] },
  'Asia/Yerevan': { countryAliases: ['Armenia'], cities: ['Yerevan'], chips: ['Armenia'] },
  'Asia/Tokyo': { countryAliases: ['Japan'], cities: ['Tokyo'], chips: ['Japan'] },
  'Asia/Seoul': { countryAliases: ['Korea', 'South Korea'], cities: ['Seoul'], chips: ['Korea'] },
  'Asia/Shanghai': { countryAliases: ['China'], cities: ['Shanghai', 'Beijing'], chips: ['China'] },
  'Asia/Singapore': { countryAliases: ['Singapore'], cities: ['Singapore'], chips: ['Singapore'] },
  'Australia/Sydney': { countryAliases: ['Australia'], cities: ['Sydney'], chips: ['Australia'] },
  'Australia/Melbourne': { countryAliases: ['Australia'], cities: ['Melbourne'], chips: ['Australia'] },
  'Pacific/Auckland': { countryAliases: ['New Zealand'], cities: ['Auckland'], chips: ['New Zealand'] },
  'Pacific/Chatham': { countryAliases: ['New Zealand'], cities: ['Chatham'], chips: ['New Zealand'] },
  'America/Toronto': { countryAliases: ['Canada'], cities: ['Toronto'], chips: ['Canada'] },
  'America/Vancouver': { countryAliases: ['Canada'], cities: ['Vancouver'], chips: ['Canada'] },
};

export function getDeviceTimezone(): string | null {
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return timezone ? canonicalizeTimezone(timezone) : null;
  } catch {
    return null;
  }
}

export function getBrowserTimezones(): string[] {
  try {
    return [...new Set((SUPPORTED_VALUES.supportedValuesOf?.('timeZone') ?? []).map(canonicalizeTimezone))];
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
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[’']/g, '')
    .toLowerCase()
    .replace(/[_/.-]/g, ' ')
    .split(/[^a-z0-9:+]+/)
    .filter(Boolean);
}

function aliasValue(alias: TimezoneAlias): TimezoneAliasSpec {
  return typeof alias === 'string' ? { value: alias } : alias;
}

function makeSearchEntry(
  alias: TimezoneAlias,
  kind: TimezoneSearchEntry['kind'],
  fallbackRank: number,
): TimezoneSearchEntry | null {
  const item = aliasValue(alias);
  const tokens = tokenizeSearchText(item.value);
  if (!tokens.length) return null;
  return {
    text: item.value,
    tokens,
    kind,
    rank: item.rank ?? fallbackRank,
    displayLabel: item.display,
  };
}

function addSearchEntries(
  entries: TimezoneSearchEntry[],
  aliases: TimezoneAlias[] | undefined,
  kind: TimezoneSearchEntry['kind'],
  fallbackRank: number,
) {
  for (const alias of aliases ?? []) {
    const entry = makeSearchEntry(alias, kind, fallbackRank);
    if (entry) entries.push(entry);
  }
}

function buildSearchEntries(timezone: string, city: string, offset: string): TimezoneSearchEntry[] {
  const meta = TIMEZONE_META[timezone];
  const entries: TimezoneSearchEntry[] = [];

  addSearchEntries(entries, [timezone, timezone.replace(/_/g, ' ')], 'timezone', 60);
  addSearchEntries(entries, [offset], 'offset', 80);
  if (meta?.name) addSearchEntries(entries, [meta.name], 'label', 20);
  addSearchEntries(entries, meta?.cities, 'city', 0);
  addSearchEntries(entries, [city], 'city', 8);
  addSearchEntries(entries, meta?.countryAliases, 'country', 55);
  addSearchEntries(entries, meta?.regionAliases, 'region', 25);
  addSearchEntries(entries, meta?.abbreviations, 'abbreviation', 5);
  addSearchEntries(entries, meta?.aliases, 'alias', 30);

  const seen = new Set<string>();
  return entries.filter((entry) => {
    const key = `${entry.kind}:${entry.text}:${entry.displayLabel ?? ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function entryMatchesQueryToken(entry: TimezoneSearchEntry, queryToken: string): boolean {
  return entry.tokens.some((token) => {
    if (queryToken.length <= 2) return token === queryToken;
    return token === queryToken || token.startsWith(queryToken);
  });
}

function hasQueryToken(tokens: string[], set: Set<string>): boolean {
  return tokens.some((token) => set.has(token));
}

function queryRank(option: TimezoneDisplayOption, query: string): number {
  const tokens = tokenizeSearchText(query);
  const meta = TIMEZONE_META[option.value];
  if (hasQueryToken(tokens, US_QUERY_TOKENS)) return meta?.usRank ?? 10_000;
  if (hasQueryToken(tokens, EUROPE_QUERY_TOKENS)) return meta?.europeRank ?? 10_000;
  return 10_000;
}

function bestDisplayEntry(option: TimezoneDisplayOption, query: string): TimezoneSearchEntry | null {
  const queryTokens = tokenizeSearchText(query).filter((token) => !GENERIC_QUERY_TOKENS.has(token));
  if (!queryTokens.length) return null;

  const candidates = option.searchEntries
    .filter((entry) => entry.displayLabel || entry.kind === 'city')
    .map((entry) => {
      const matchedTokens = queryTokens.filter((token) => entryMatchesQueryToken(entry, token)).length;
      return { entry, matchedTokens };
    })
    .filter((candidate) => candidate.matchedTokens > 0)
    .sort((a, b) => (
      b.matchedTokens - a.matchedTokens
      || a.entry.rank - b.entry.rank
      || a.entry.text.localeCompare(b.entry.text)
    ));

  return candidates[0]?.entry ?? null;
}

function matchTimezoneOption(option: TimezoneDisplayOption, query: string): { matched: boolean; score: number } {
  const queryTokens = tokenizeSearchText(query);
  if (!queryTokens.length) return { matched: true, score: option.selectionPriority };

  const matchingEntriesByToken = queryTokens.map((token) => (
    option.searchEntries.filter((entry) => entryMatchesQueryToken(entry, token))
  ));
  if (matchingEntriesByToken.some((entries) => entries.length === 0)) {
    return { matched: false, score: Number.POSITIVE_INFINITY };
  }

  const allTokensInOneEntry = option.searchEntries.some((entry) => (
    queryTokens.every((token) => entryMatchesQueryToken(entry, token))
  ));
  const displayEntry = bestDisplayEntry(option, query);
  const bestRank = Math.min(...matchingEntriesByToken.flat().map((entry) => entry.rank));
  const exactAbbreviation = option.searchEntries.some((entry) => (
    entry.kind === 'abbreviation'
    && queryTokens.length === 1
    && entry.tokens.includes(queryTokens[0])
  ));

  let score = 1_000 + bestRank;
  if (allTokensInOneEntry) score -= 250;
  if (displayEntry) score -= 200 - displayEntry.rank * 2;
  if (exactAbbreviation) score -= 150;
  const rank = queryRank(option, query);
  if (rank !== 10_000) score += rank;

  return { matched: true, score };
}

function readableTimezoneId(timezone: string): string {
  return timezone.replace(/_/g, ' ');
}

function readableSecondaryLabel(option: TimezoneDisplayOption): string {
  return `${formatOffset(option.offsetMinutes)} · ${readableTimezoneId(option.value)}`;
}

export function getTimezoneDisplay(option: TimezoneDisplayOption, query: string): TimezoneRenderedDisplay {
  const entry = bestDisplayEntry(option, query);
  if (!entry) {
    return {
      primaryLabel: option.primaryLabel,
      secondaryLabel: readableSecondaryLabel(option),
      chips: option.chips,
    };
  }

  const city = entry.displayLabel ?? entry.text;
  return {
    primaryLabel: primaryLabel(option.value, city),
    secondaryLabel: readableSecondaryLabel(option),
    chips: option.chips,
  };
}

export function timezoneDismissKey(profileTimezone: string, deviceTimezone: string): string {
  return `lumi-tz-dismissed:${profileTimezone}:${deviceTimezone}`;
}

export function timezoneOptionMatches(option: TimezoneDisplayOption, query: string): boolean {
  return matchTimezoneOption(option, query).matched;
}

export function sortTimezoneOptions(
  a: TimezoneDisplayOption,
  b: TimezoneDisplayOption,
  query = '',
): number {
  const normalizedQuery = query.trim();
  if (normalizedQuery) {
    const queryTokens = tokenizeSearchText(normalizedQuery);
    const genericOnly = queryTokens.length > 0 && queryTokens.every((token) => GENERIC_QUERY_TOKENS.has(token));
    if (genericOnly) {
      return (
        queryRank(a, normalizedQuery) - queryRank(b, normalizedQuery)
        || a.offsetMinutes - b.offsetMinutes
        || cityFromTimezone(a.value).localeCompare(cityFromTimezone(b.value))
        || a.value.localeCompare(b.value)
      );
    }

    const aMatch = matchTimezoneOption(a, normalizedQuery);
    const bMatch = matchTimezoneOption(b, normalizedQuery);
    return (
      aMatch.score - bMatch.score
      || queryRank(a, normalizedQuery) - queryRank(b, normalizedQuery)
      || a.offsetMinutes - b.offsetMinutes
      || cityFromTimezone(a.value).localeCompare(cityFromTimezone(b.value))
      || a.value.localeCompare(b.value)
    );
  }

  return (
    a.selectionPriority - b.selectionPriority
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
  const source = params.apiTimezones?.length ? params.apiTimezones : params.browserTimezones ?? [];
  const zones = new Set(source.map(canonicalizeTimezone));
  zones.add('UTC');
  for (const tz of params.extraTimezones ?? []) {
    if (tz) zones.add(canonicalizeTimezone(tz));
  }
  const now = params.now ?? new Date();
  return [...zones].map((timezone) => {
    const offset = offsetName(timezone, now);
    const city = cityFromTimezone(timezone);
    const primary = primaryLabel(timezone, city);
    const secondary = `${offset} · ${timezone}`;
    const label = `${primary} · ${secondary}`;
    const meta = TIMEZONE_META[timezone];
    const searchEntries = buildSearchEntries(timezone, city, offset);
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
      searchText: searchEntries.map((entry) => entry.text).join(' ').toLowerCase(),
      offsetMinutes: offsetMinutes(offset),
      selectionPriority,
      chips: meta?.chips ?? [],
      searchEntries,
    };
  }).sort(sortTimezoneOptions);
}
