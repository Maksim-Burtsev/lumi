import type { KeyboardEvent, ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { StickyNote } from 'lucide-react';
import { Button } from '../ui/Button';
import { formatTime, formatTimeRange } from '../../lib/format';
import { useTimeDisplay } from '../../lib/useTimeDisplay';

export type TimelineEntryKind = 'event' | 'focus' | 'proposed' | 'free' | 'task';

export interface TimelineEntry {
  id: string;
  kind: TimelineEntryKind;
  title: string;
  start_at: string;
  end_at: string;
  subtitle?: string;
  /** «Принять» on proposed blocks. */
  action?: { label: string; onClick: () => void; busy?: boolean };
  /** Secondary, low-emphasis action («Отклонить»/«Убрать»). */
  secondaryAction?: { label: string; onClick: () => void; busy?: boolean };
  /** Tap on the whole row (e.g. free slot → create block). */
  onPress?: () => void;
  hasPersonalNote?: boolean;
}

const DOTS: Record<TimelineEntryKind, string> = {
  event: 'bg-[var(--hint)]',
  focus: 'bg-accent shadow-[0_0_6px_rgba(46,99,231,0.5)]',
  proposed: 'border-2 border-[var(--accent)] bg-transparent',
  free: 'border border-[var(--hint)] bg-transparent opacity-60',
  task: 'bg-[var(--success)]',
};

function entryCardClass(kind: TimelineEntryKind): string {
  switch (kind) {
    case 'event':
      return 'card card-strong px-4 py-3';
    case 'focus':
      return 'card card-strong border-l-[3px] border-l-[var(--accent)] px-4 py-3';
    case 'proposed':
      return 'rounded-card border border-dashed border-[var(--accent-border)] bg-[var(--accent-soft)] px-4 py-3';
    case 'free':
      return 'rounded-card border border-dashed border-hairline bg-transparent px-4 py-2.5';
    case 'task':
      return 'rounded-card border border-hairline bg-transparent px-4 py-2.5';
  }
}

function EntryRow({ entry }: { entry: TimelineEntry }) {
  const reduceMotion = useReducedMotion();
  const timeDisplay = useTimeDisplay();
  const press = () => entry.onPress?.();
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!entry.onPress) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    entry.onPress();
  };

  const inner: ReactNode = (
    <>
      <span className="tnum absolute -left-20 top-[13px] w-16 whitespace-nowrap text-right text-[12.5px] font-medium text-hint">
        {formatTime(entry.start_at, timeDisplay)}
      </span>
      <span
        aria-hidden
        className={`absolute left-[-15px] top-[18px] h-[7px] w-[7px] rounded-full ${DOTS[entry.kind]}`}
      />
      <div className={entryCardClass(entry.kind)}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5">
              <p
                className={`truncate text-[14.5px] ${
                  entry.kind === 'free' ? 'font-normal text-hint' : 'font-medium text-ink'
                }`}
              >
                {entry.title}
              </p>
              {entry.hasPersonalNote && (
                <span role="img" aria-label="Есть личная заметка" className="shrink-0 text-hint">
                  <StickyNote size={13} aria-hidden="true" />
                </span>
              )}
            </div>
            <p className="tnum mt-0.5 text-[12px] text-hint">
              {entry.kind === 'task'
                ? `к ${formatTime(entry.start_at, timeDisplay)}`
                : formatTimeRange(entry.start_at, entry.end_at, timeDisplay)}
              {entry.subtitle ? ` · ${entry.subtitle}` : ''}
            </p>
          </div>
          {entry.secondaryAction && (
            <span onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
              <Button
                size="sm"
                variant="ghost"
                busy={entry.secondaryAction.busy}
                onClick={entry.secondaryAction.onClick}
              >
                {entry.secondaryAction.label}
              </Button>
            </span>
          )}
          {entry.action && (
            <span onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
              <Button size="sm" variant="primary" busy={entry.action.busy} onClick={entry.action.onClick}>
                {entry.action.label}
              </Button>
            </span>
          )}
        </div>
      </div>
    </>
  );

  if (entry.onPress) {
    return (
      <motion.div
        role="button"
        tabIndex={0}
        onClick={press}
        onKeyDown={handleKeyDown}
        whileTap={reduceMotion ? undefined : { scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 420, damping: 26 }}
        className="relative block w-full cursor-pointer text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-border)]"
      >
        {inner}
      </motion.div>
    );
  }

  return <div className="relative">{inner}</div>;
}

/** Thin vertical rail with dot markers; times in tabular figures. */
export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <div className="relative flex flex-col gap-2.5 pl-20">
      <div aria-hidden className="absolute bottom-3 left-[68px] top-3 w-px bg-hairline" />
      {entries.map((entry) => (
        <EntryRow key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
