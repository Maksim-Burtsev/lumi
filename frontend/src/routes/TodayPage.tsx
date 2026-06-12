import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock,
  HelpCircle,
  Mail,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../api/client';
import { qk, useAgentRunAction, useConfirmBlock, useToday } from '../api/hooks';
import type { AttentionItem, Suggestion, TimelineItem, TodaySummary } from '../api/types';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Skeleton, SkeletonList, SkeletonTimeline } from '../components/ui/Skeleton';
import { StatPill } from '../components/ui/StatPill';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { Timeline } from '../components/timeline/Timeline';
import type { TimelineEntry } from '../components/timeline/Timeline';
import { countLabel, formatDateHeading, formatSpanMinutes, plural } from '../lib/format';

function buildSummaryLine(summary: TodaySummary): string {
  const parts: string[] = [];
  if (summary.meetings_today > 0) parts.push(countLabel(summary.meetings_today, ['встреча', 'встречи', 'встреч']));
  if (summary.tasks_active > 0) parts.push(countLabel(summary.tasks_active, ['задача', 'задачи', 'задач']));
  if (summary.emails_need_reply > 0) {
    parts.push(
      `${summary.emails_need_reply} ${plural(summary.emails_need_reply, [
        'письмо ждёт ответа',
        'письма ждут ответа',
        'писем ждут ответа',
      ])}`,
    );
  }
  if (parts.length === 0) return 'Спокойный день — можно заняться важным';
  return parts.join(' · ');
}

const ATTENTION_ICONS: Record<AttentionItem['kind'], { icon: LucideIcon; className: string }> = {
  overdue_task: { icon: AlertCircle, className: 'text-danger' },
  due_task: { icon: Clock, className: 'text-accent-text' },
  email: { icon: Mail, className: 'text-accent-text' },
  confirmation: { icon: HelpCircle, className: 'text-hint' },
};

const ATTENTION_ROUTES: Record<AttentionItem['kind'], string> = {
  overdue_task: '/tasks',
  due_task: '/tasks',
  email: '/inbox',
  confirmation: '/calendar',
};

function TodaySkeleton() {
  return (
    <div>
      <div aria-hidden className="card p-5">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="mt-2.5 h-3.5 w-36" />
        <Skeleton className="mt-3.5 h-4 w-64" />
        <div className="mt-5 flex gap-2.5">
          <Skeleton className="h-11 w-36 !rounded-full" />
          <Skeleton className="h-11 w-40 !rounded-full" />
        </div>
      </div>
      <div className="mt-7">
        <Skeleton className="mb-3 h-4 w-28" />
        <SkeletonTimeline rows={3} />
      </div>
      <div className="mt-7">
        <Skeleton className="mb-3 h-4 w-36" />
        <SkeletonList count={2} lines={1} />
      </div>
    </div>
  );
}

export default function TodayPage() {
  const todayQuery = useToday();
  const navigate = useNavigate();
  const { show } = useToast();
  const confirmBlock = useConfirmBlock();

  const planAction = useAgentRunAction({
    start: () => api.planDay(),
    invalidate: [qk.eventsAll, qk.freeSlotsAll, qk.tasksAll],
    successMessage: 'План готов',
  });

  const triageAction = useAgentRunAction({
    start: () => api.runEmailTriage(),
    invalidate: [qk.inbox],
    successMessage: 'Почта разобрана',
    onApiError: (error) => {
      if (error.status === 409 && error.error === 'google_not_connected') {
        show('Google не подключен — загляни в Настройки', 'info');
        return true;
      }
      return false;
    },
  });

  const digestAction = useAgentRunAction({
    start: () => api.runNewsDigest(),
    invalidate: [qk.digests],
    successMessage: 'Дайджест готов',
  });

  const handleConfirmBlock = (blockId: string) => {
    confirmBlock.mutate(blockId, {
      onSuccess: () => show('Блок добавлен в календарь', 'success'),
      onError: () => show('Не удалось подтвердить блок', 'error'),
    });
  };

  const handleSuggestion = (suggestion: Suggestion) => {
    switch (suggestion.action.type) {
      case 'plan_day': {
        const date = suggestion.action.payload['date'];
        if (typeof date === 'string' && date) {
          planAction.trigger(() => api.planDay(date));
          break;
        }
        planAction.trigger();
        break;
      }
      case 'run_triage':
        triageAction.trigger();
        break;
      case 'run_digest':
        digestAction.trigger();
        break;
      case 'confirm_block': {
        const payload = suggestion.action.payload;
        const candidate = payload['block_id'] ?? payload['event_id'] ?? payload['id'];
        if (typeof candidate === 'string') handleConfirmBlock(candidate);
        break;
      }
    }
  };

  const suggestionBusy = (suggestion: Suggestion): boolean => {
    switch (suggestion.action.type) {
      case 'plan_day':
        return planAction.isRunning;
      case 'run_triage':
        return triageAction.isRunning;
      case 'run_digest':
        return digestAction.isRunning;
      case 'confirm_block':
        return confirmBlock.isPending;
    }
  };

  if (todayQuery.isPending) return <TodaySkeleton />;
  if (todayQuery.isError) {
    return <ErrorState message="Не удалось загрузить план дня." onRetry={() => void todayQuery.refetch()} />;
  }

  const data = todayQuery.data;
  const date = new Date(`${data.date}T00:00:00`);

  const rawEntries: TimelineEntry[] = data.timeline
    .filter((item: TimelineItem) => item.status !== 'cancelled')
    .map((item) => ({
      id: item.id,
      kind: item.kind,
      title: item.title,
      start_at: item.start_at,
      end_at: item.end_at,
      subtitle:
        item.kind === 'task'
          ? 'Задача'
          : item.source === 'google'
            ? 'Google'
            : item.source === 'yandex'
              ? 'Яндекс'
              : item.kind === 'focus'
                ? 'Фокус'
                : undefined,
      action:
        item.kind === 'proposed'
          ? {
              label: 'Принять',
              onClick: () => handleConfirmBlock(item.id),
              busy: confirmBlock.isPending,
            }
          : undefined,
    }));

  // Agenda rhythm: surface real gaps between items as ghost "free" rows,
  // so back-to-back meetings and 2-hour windows look different.
  const timelineEntries: TimelineEntry[] = [];
  rawEntries.forEach((entry, i) => {
    if (i > 0) {
      const prevEnd = new Date(rawEntries[i - 1].end_at).getTime();
      const start = new Date(entry.start_at).getTime();
      const gapMin = Math.round((start - prevEnd) / 60000);
      if (gapMin >= 45) {
        timelineEntries.push({
          id: `gap-${i}`,
          kind: 'free',
          title: `Свободно · ${formatSpanMinutes(rawEntries[i - 1].end_at, entry.start_at)}`,
          start_at: rawEntries[i - 1].end_at,
          end_at: entry.start_at,
        });
      }
    }
    timelineEntries.push(entry);
  });

  return (
    <Stagger>
      {/* ----------------------------------------------------------- Hero */}
      <Rise>
        <Card className="relative overflow-hidden p-5">
          <div aria-hidden className="dawn-glow" />
          <div className="relative">
            <h2 className="font-display text-[24px] font-normal leading-tight tracking-[-0.01em] text-ink">
              {data.greeting}
            </h2>
            <p className="mt-1 text-[13px] text-hint">{formatDateHeading(date)}</p>
            <p className="tnum mt-3 text-[15px] leading-relaxed text-ink">{buildSummaryLine(data.summary)}</p>
            {data.summary.tasks_overdue > 0 && (
              <div className="mt-2.5">
                <StatPill
                  tone="danger"
                  label={`${countLabel(data.summary.tasks_overdue, ['задача просрочена', 'задачи просрочены', 'задач просрочено'])}`}
                  onClick={() => navigate('/tasks')}
                />
              </div>
            )}
            <div className="mt-5 flex flex-wrap gap-2.5">
              <Button
                variant="primary"
                icon={<Sparkles size={16} />}
                busy={planAction.isRunning}
                onClick={planAction.trigger}
              >
                Собрать план
              </Button>
              <Button
                variant="secondary"
                icon={<Mail size={16} />}
                busy={triageAction.isRunning}
                onClick={triageAction.trigger}
              >
                Разобрать почту
              </Button>
            </div>
          </div>
        </Card>
      </Rise>

      {/* ----------------------------------------------------------- Timeline */}
      <Rise>
        <SectionHeader title="Расписание" />
        {timelineEntries.length > 0 ? (
          <Timeline entries={timelineEntries} />
        ) : (
          <EmptyState
            icon={CalendarDays}
            title="Сегодня нет встреч и блоков"
            hint="Нажми «Собрать план» — Lumi посмотрит задачи и предложит фокус-блоки."
          />
        )}
      </Rise>

      {/* ----------------------------------------------------------- Needs attention */}
      {data.needs_attention.length > 0 && (
        <Rise>
          <SectionHeader title="Требует внимания" />
          <Card className="card-strong divide-y divide-[var(--hairline)] overflow-hidden !p-0">
            {data.needs_attention.map((item) => {
              const meta = ATTENTION_ICONS[item.kind];
              const Icon = meta.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(ATTENTION_ROUTES[item.kind])}
                  className="flex min-h-[52px] w-full items-center gap-3 px-4 py-2.5 text-left"
                >
                  <Icon size={17} strokeWidth={1.9} className={`shrink-0 ${meta.className}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-medium text-ink">{item.title}</span>
                    {item.subtitle && <span className="block truncate text-[12.5px] text-hint">{item.subtitle}</span>}
                  </span>
                  <ArrowRight size={15} className="shrink-0 text-hint" />
                </button>
              );
            })}
          </Card>
        </Rise>
      )}

      {/* ----------------------------------------------------------- Suggestions */}
      {data.suggestions.length > 0 && (
        <Rise>
          <SectionHeader title="Lumi предлагает" />
          <div className="flex flex-col gap-3">
            {data.suggestions.map((suggestion) => (
              <div
                key={suggestion.id}
                className="rounded-card border border-[var(--accent-border)] bg-[var(--accent-soft)] px-4 py-3.5"
              >
                <div className="flex items-start gap-3">
                  <Sparkles size={17} className="mt-0.5 shrink-0 text-accent-text" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] font-medium leading-snug text-ink">{suggestion.title}</p>
                    {suggestion.description && (
                      <p className="mt-1 text-[12.5px] leading-relaxed text-hint">{suggestion.description}</p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="primary"
                    busy={suggestionBusy(suggestion)}
                    onClick={() => handleSuggestion(suggestion)}
                  >
                    Принять
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Rise>
      )}

      {/* All-clear footer when nothing demands attention */}
      {data.needs_attention.length === 0 && data.suggestions.length === 0 && (
        <Rise>
          <div className="mt-7 flex items-center justify-center gap-2 text-[13px] text-hint">
            <CheckCircle2 size={15} className="text-success" />
            Ничего срочного — всё под контролем
          </div>
        </Rise>
      )}
    </Stagger>
  );
}
