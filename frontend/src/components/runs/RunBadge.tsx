import type { LucideIcon } from 'lucide-react';
import {
  Bot,
  CalendarRange,
  ListChecks,
  Mail,
  MessageCircle,
  Newspaper,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { runStatusLabel } from '../../lib/labels';
import { useAppLocale } from '../../lib/useAppLocale';

const STATUS_DOT: Record<string, string> = {
  queued: 'bg-[var(--hint)]',
  running: 'bg-accent pulse-dot',
  completed: 'bg-success',
  failed: 'bg-danger',
};

export function RunStatusDot({ status }: { status: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status] ?? 'bg-[var(--hint)]'}`}
    />
  );
}

const STATUS_BADGE: Record<string, string> = {
  queued: 'bg-[var(--secondary-bg)] text-hint',
  running: 'bg-[var(--accent-soft)] text-accent-text',
  completed: 'bg-[var(--success-soft)] text-success',
  failed: 'bg-[var(--danger-soft)] text-danger',
};

export function RunStatusBadge({ status }: { status: string }) {
  const locale = useAppLocale();
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ${
        STATUS_BADGE[status] ?? 'bg-[var(--secondary-bg)] text-hint'
      }`}
    >
      <RunStatusDot status={status} />
      {runStatusLabel(status, locale)}
    </span>
  );
}

const TYPE_ICONS: Record<string, LucideIcon> = {
  email_triage: Mail,
  news_digest: Newspaper,
  daily_planning: CalendarRange,
  plan_day: CalendarRange,
  calendar_sync: RefreshCw,
  task_review: ListChecks,
  custom_prompt: Terminal,
  chat: MessageCircle,
};

export function runTypeIcon(type: string): LucideIcon {
  return TYPE_ICONS[type] ?? Bot;
}
