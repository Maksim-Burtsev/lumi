import { useMemo, useRef } from 'react';
import { StickyNote } from 'lucide-react';
import type { CalendarEvent } from '../../api/types';
import { formatTime } from '../../lib/format';
import type { AppLocale } from '../../lib/i18n';
import { useTimeDisplay } from '../../lib/useTimeDisplay';

/**
 * Mac-style proportional day grid: hour lines, events positioned by start
 * time with height proportional to duration; overlapping events share width.
 */

const PX_PER_MINUTE = 1.3;
const MIN_EVENT_PX = 20;

export interface DayGridProps {
  events: CalendarEvent[];
  dayStart: Date;
  locale: AppLocale;
  /** Tap on an event opens its detail sheet. */
  onEventTap: (event: CalendarEvent) => void;
  /** Tap on empty space → create a block at that time (rounded to 30 min). */
  onEmptyTap: (time: Date) => void;
  nowLine?: boolean;
}

interface Positioned {
  event: CalendarEvent;
  top: number;
  height: number;
  column: number;
  columns: number;
}

function minutesFromMidnight(iso: string, dayStart: Date): number {
  const d = new Date(iso);
  return (d.getTime() - dayStart.getTime()) / 60000;
}

/** Greedy column assignment inside overlap clusters. */
function layoutEvents(events: CalendarEvent[], dayStart: Date): Positioned[] {
  const sorted = [...events].sort(
    (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
  );
  const out: Positioned[] = [];
  let cluster: { event: CalendarEvent; start: number; end: number; column: number }[] = [];
  let clusterEnd = -1;

  const flush = () => {
    if (!cluster.length) return;
    const columns = Math.max(...cluster.map((c) => c.column)) + 1;
    for (const item of cluster) {
      const top = item.start * PX_PER_MINUTE;
      const height = Math.max((item.end - item.start) * PX_PER_MINUTE, MIN_EVENT_PX);
      out.push({ event: item.event, top, height, column: item.column, columns });
    }
    cluster = [];
    clusterEnd = -1;
  };

  for (const event of sorted) {
    const start = Math.max(0, minutesFromMidnight(event.start_at, dayStart));
    const rawEnd = Math.min(24 * 60, minutesFromMidnight(event.end_at, dayStart));
    // Columns split ONLY on real time overlap — back-to-back 15-minute
    // meetings stay stacked; short events render compact instead (below).
    const end = Math.max(start + 1, rawEnd);
    if (cluster.length && start >= clusterEnd) flush();
    // first free column within the cluster
    const used = new Set(
      cluster.filter((c) => c.end > start).map((c) => c.column),
    );
    let column = 0;
    while (used.has(column)) column += 1;
    cluster.push({ event, start, end, column });
    clusterEnd = Math.max(clusterEnd, end);
  }
  flush();
  return out;
}

function eventClasses(event: CalendarEvent): string {
  if (event.status === 'proposed') {
    return 'border border-dashed border-[var(--accent-border)] bg-[var(--accent-soft)]';
  }
  if (event.source === 'internal') {
    return 'border-l-[3px] border-l-[var(--accent)] bg-[var(--accent-soft)]';
  }
  // external (google / yandex) — solid, muted
  return 'bg-[var(--secondary-bg)] border-l-[3px] border-l-[var(--hint)]';
}

const SOURCE_LABELS: Record<AppLocale, Record<string, string>> = {
  en: { google: 'Google', yandex: 'Yandex' },
  ru: { google: 'Google', yandex: 'Яндекс' },
};

export function DayGrid({ events, dayStart, locale, onEventTap, onEmptyTap, nowLine }: DayGridProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const timeDisplay = useTimeDisplay();
  const allDayLabel = locale === 'en' ? 'all day' : 'весь день';
  const createBlockLabel = locale === 'en' ? 'Create block' : 'Создать блок';
  const proposedLabel = locale === 'en' ? 'proposal' : 'предложение';

  const DAY_MIN = 24 * 60;
  const visible = events.filter((e) => e.status !== 'cancelled');
  // Events covering (almost) the whole visible day — vacations, duty shifts,
  // multi-day spans — belong in the all-day row, not as giant columns.
  const spansDay = (e: CalendarEvent) => {
    const start = Math.max(0, minutesFromMidnight(e.start_at, dayStart));
    const end = Math.min(DAY_MIN, minutesFromMidnight(e.end_at, dayStart));
    return end - start >= 18 * 60;
  };
  const timed = visible.filter((e) => !e.all_day && !spansDay(e));
  const allDay = visible.filter((e) => e.all_day || spansDay(e));

  const { startHour, endHour } = useMemo(() => {
    let start = 8;
    let end = 22;
    for (const e of timed) {
      const s = Math.floor(minutesFromMidnight(e.start_at, dayStart) / 60);
      const f = Math.ceil(minutesFromMidnight(e.end_at, dayStart) / 60);
      if (!Number.isNaN(s)) start = Math.min(start, Math.max(0, s));
      if (!Number.isNaN(f)) end = Math.max(end, Math.min(24, f));
    }
    return { startHour: start, endHour: end };
  }, [timed, dayStart]);

  const positioned = useMemo(() => layoutEvents(timed, dayStart), [timed, dayStart]);
  const offsetPx = startHour * 60 * PX_PER_MINUTE;
  const heightPx = (endHour - startHour) * 60 * PX_PER_MINUTE;
  const hours = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i);
  const hourLabel = (hour: number) => formatTime(
    new Date(dayStart.getTime() + hour * 60 * 60000),
    timeDisplay,
  );

  const nowMinutes = minutesFromMidnight(new Date().toISOString(), dayStart);
  const showNow = nowLine && nowMinutes >= startHour * 60 && nowMinutes <= endHour * 60;

  const handleGridClick = (clientY: number) => {
    const rect = gridRef.current?.getBoundingClientRect();
    if (!rect) return;
    const minutes = (clientY - rect.top) / PX_PER_MINUTE + startHour * 60;
    const rounded = Math.round(minutes / 30) * 30;
    const time = new Date(dayStart.getTime() + rounded * 60000);
    onEmptyTap(time);
  };

  return (
    <div>
      {allDay.length > 0 && (
        <div className="mb-3 space-y-1.5">
          {allDay.map((e) => (
            <button
              key={e.id}
              onClick={() => onEventTap(e)}
              className="flex w-full items-center gap-2 rounded-xl bg-[var(--secondary-bg)] px-3.5 py-2 text-left text-[13px] font-medium text-ink"
            >
              <span className="min-w-0 flex-1 truncate">{e.title}</span>
              {e.private_note && <StickyNote size={13} className="shrink-0 text-hint" aria-hidden="true" />}
              <span className="shrink-0 text-[11.5px] font-normal text-hint">{allDayLabel}</span>
            </button>
          ))}
        </div>
      )}

      <div className="relative ml-16" style={{ height: heightPx }} ref={gridRef}>
        {/* hour lines + labels */}
        {hours.map((hour) => (
          <div
            key={hour}
            className="absolute left-0 right-0 border-t border-[var(--hairline)]"
            style={{ top: (hour - startHour) * 60 * PX_PER_MINUTE }}
          >
            <span className="tnum absolute -left-16 -top-2 w-14 whitespace-nowrap text-right text-[11px] text-hint">
              {hourLabel(hour)}
            </span>
          </div>
        ))}

        {/* click-to-create layer */}
        <button
          aria-label={createBlockLabel}
          className="absolute inset-0 cursor-pointer"
          onClick={(e) => handleGridClick(e.clientY)}
        />

        {/* now line */}
        {showNow && (
          <div
            className="pointer-events-none absolute left-0 right-0 z-20"
            style={{ top: nowMinutes * PX_PER_MINUTE - offsetPx }}
          >
            <div className="h-[2px] bg-[var(--danger)] opacity-80" />
            <div className="absolute -left-1 -top-[3px] h-2 w-2 rounded-full bg-[var(--danger)]" />
          </div>
        )}

        {/* events */}
        {positioned.map(({ event, top, height, column, columns }) => {
          const width = 100 / columns;
          return (
            <button
              key={event.id}
              onClick={(e) => {
                e.stopPropagation();
                onEventTap(event);
              }}
              className={`absolute z-10 overflow-hidden rounded-lg text-left transition-transform active:scale-[0.99] ${
                height < 32 ? 'px-2 py-[2px]' : 'px-2.5 py-1.5'
              } ${eventClasses(event)}`}
              style={{
                top: top - offsetPx,
                height,
                left: `calc(${column * width}% + ${column > 0 ? 3 : 0}px)`,
                width: `calc(${width}% - ${columns > 1 ? 3 : 0}px)`,
              }}
            >
              <p
                className={`truncate pr-4 font-medium leading-tight text-ink ${
                  height < 32 ? 'text-[11px]' : 'text-[12.5px]'
                }`}
              >
                {height < 32 ? `${formatTime(event.start_at, timeDisplay)} ${event.title}` : event.title}
              </p>
              {event.private_note && (
                <StickyNote
                  size={height < 32 ? 11 : 12}
                  className="absolute right-1.5 top-1.5 text-hint"
                  aria-hidden="true"
                />
              )}
              {height >= 42 && (
                <p className="tnum mt-0.5 truncate text-[11px] leading-tight text-hint">
                  {formatTime(event.start_at, timeDisplay)}–{formatTime(event.end_at, timeDisplay)}
                  {event.source !== 'internal'
                    ? ` · ${SOURCE_LABELS[locale][event.source] ?? event.source}`
                    : event.status === 'proposed'
                      ? ` · ${proposedLabel}`
                      : ''}
                </p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
