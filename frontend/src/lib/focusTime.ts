export interface FocusLocalRange {
  started_at: string;
  ended_at: string;
  valid: boolean;
  duration_minutes: number;
}

export function dateTimeInputParts(date: Date, timezone?: string | null): { date: string; time: string } {
  if (!timezone) {
    const offsetMs = date.getTimezoneOffset() * 60_000;
    const local = new Date(date.getTime() - offsetMs).toISOString();
    return { date: local.slice(0, 10), time: local.slice(11, 16) };
  }
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date);
    const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? '';
    return { date: `${part('year')}-${part('month')}-${part('day')}`, time: `${part('hour')}:${part('minute')}` };
  } catch {
    return dateTimeInputParts(date);
  }
}

export function localPartsToDate(date: string, time: string, timezone?: string | null): Date {
  if (!timezone) {
    const parsed = new Date(`${date}T${time || '00:00'}`);
    if (Number.isNaN(parsed.getTime())) return new Date(Number.NaN);
    const actual = dateTimeInputParts(parsed);
    return actual.date === date && actual.time === (time || '00:00')
      ? parsed
      : new Date(Number.NaN);
  }
  const desired = Date.parse(`${date}T${time || '00:00'}:00Z`);
  if (!Number.isFinite(desired)) return new Date(Number.NaN);

  const offsets = new Set<number>();
  for (const probeHours of [-36, -12, 0, 12, 36]) {
    const probe = desired + probeHours * 60 * 60_000;
    const actual = dateTimeInputParts(new Date(probe), timezone);
    const actualAsUtc = Date.parse(`${actual.date}T${actual.time}:00Z`);
    if (Number.isFinite(actualAsUtc)) offsets.add(actualAsUtc - probe);
  }

  const matches = [...offsets]
    .map((offset) => new Date(desired - offset))
    .filter((candidate) => {
      const actual = dateTimeInputParts(candidate, timezone);
      return actual.date === date && actual.time === (time || '00:00');
    })
    .sort((left, right) => left.getTime() - right.getTime());

  // During an autumn DST fold, use the earlier of the two matching instants.
  // A nonexistent spring-forward wall time has no round-trip match and is invalid.
  return matches[0] ?? new Date(Number.NaN);
}

export function localRangeToIso(
  startDate: string,
  startTime: string,
  endDate: string,
  endTime: string,
  timezone?: string | null,
): FocusLocalRange {
  const start = localPartsToDate(startDate, startTime, timezone);
  const end = localPartsToDate(endDate, endTime, timezone);
  const durationMinutes = Math.round((end.getTime() - start.getTime()) / 60_000);
  const validDates = !Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime());
  return {
    started_at: validDates ? start.toISOString() : '',
    ended_at: validDates ? end.toISOString() : '',
    valid: validDates && Number.isFinite(durationMinutes) && durationMinutes > 0 && durationMinutes <= 24 * 60,
    duration_minutes: durationMinutes,
  };
}
