import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock,
  HelpCircle,
  Mail,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../api/client';
import {
  qk,
  useAgentRunAction,
  useCompleteTask,
  useConfirmBlock,
  useCreateTaskFromThread,
  useDecideConfirmation,
  useSnoozeTask,
  useToday,
} from '../api/hooks';
import type { AttentionItem, Suggestion, TimelineItem, TodaySummary } from '../api/types';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Sheet } from '../components/ui/Sheet';
import { Skeleton, SkeletonList, SkeletonTimeline } from '../components/ui/Skeleton';
import { StatPill } from '../components/ui/StatPill';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { Timeline } from '../components/timeline/Timeline';
import type { TimelineEntry } from '../components/timeline/Timeline';
import { countLabel, formatDateHeading, formatDueLabel, formatSpanMinutes, plural } from '../lib/format';
import { haptic } from '../telegram/webapp';

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

function attentionCtaLabel(item: AttentionItem): string {
  if (item.kind === 'confirmation') {
    if (item.ui_mode === 'review_then_confirm' || item.ui_mode === 'strong_confirm') return 'Проверить';
    return 'Решить';
  }
  if (item.kind === 'email') return 'Ответить';
  return 'Разобрать';
}

function riskLabel(item: AttentionItem): string {
  switch (item.risk_class) {
    case 'write_external':
      return 'Внешний календарь';
    case 'external_communication':
      return 'Внешняя отправка';
    case 'destructive':
      return 'Опасное действие';
    case 'write_internal_memory':
      return 'Память';
    case 'write_internal_scheduled':
      return 'Автоматизация';
    case 'write_internal':
      return 'Внутри Lumi';
    default:
      return 'Нужно подтверждение';
  }
}

function riskHint(item: AttentionItem): string {
  switch (item.risk_class) {
    case 'write_external':
      return 'Будет создана запись вне Lumi.';
    case 'external_communication':
      return 'Сначала будет черновик, отправка только после подтверждения.';
    case 'destructive':
      return 'Действие может удалить или отключить данные.';
    case 'write_internal_memory':
      return 'Lumi сохранит это как долгосрочную память.';
    case 'write_internal_scheduled':
      return 'Lumi включит регулярное действие.';
    case 'write_internal':
      return 'Изменение останется внутри Lumi.';
    default:
      return 'Проверь детали перед решением.';
  }
}

function payloadText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

function payloadDate(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return formatDueLabel(date.toISOString());
}

function confirmationDetailRows(item: AttentionItem): { label: string; value: string }[] {
  const payload = item.action_payload ?? {};
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null) => {
    if (value) rows.push({ label, value });
  };

  switch (item.action_type) {
    case 'create_google_calendar_event':
      push('Действие', 'Добавить в Google Calendar');
      push('Название', payloadText(payload.title));
      push('Начало', payloadDate(payload.start_at_local));
      push('Конец', payloadDate(payload.end_at_local));
      break;
    case 'store_memory':
      push('Запомнить', payloadText(payload.text));
      push('Тип', payloadText(payload.kind));
      break;
    case 'create_task':
      push('Задача', payloadText(payload.title));
      push('Срок', payloadDate(payload.due_at_local));
      push('Напоминание', payloadDate(payload.reminder_at_local));
      push('Проект', payloadText(payload.project));
      break;
    case 'create_automation':
      push('Автоматизация', payloadText(payload.title));
      push('Расписание', payloadText(payload.cron_expression));
      push('Часовой пояс', payloadText(payload.timezone));
      break;
    default:
      push('Действие', item.action_type ?? null);
  }

  return rows;
}

function AttentionIcon({ item }: { item: AttentionItem }) {
  const meta = ATTENTION_ICONS[item.kind];
  const Icon = meta.icon;
  return <Icon size={17} strokeWidth={1.9} className={`shrink-0 ${meta.className}`} />;
}

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
  const [selectedAttention, setSelectedAttention] = useState<AttentionItem | null>(null);
  const confirmBlock = useConfirmBlock();
  const decideConfirmation = useDecideConfirmation();
  const completeTask = useCompleteTask('today');
  const snoozeTask = useSnoozeTask('today');
  const createTaskFromThread = useCreateTaskFromThread();

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

  const closeAttention = () => setSelectedAttention(null);

  const handleAttentionNavigate = (route: string) => {
    closeAttention();
    navigate(route);
  };

  const handleConfirmationDecision = (accept: boolean) => {
    const id = selectedAttention?.ref_id;
    if (!id) return;
    decideConfirmation.mutate(
      { id, accept },
      {
        onSuccess: (result) => {
          haptic(accept ? 'success' : 'light');
          show(result.result_text, accept ? 'success' : 'info');
          closeAttention();
        },
        onError: () => {
          show('Не удалось сохранить решение', 'error');
          void todayQuery.refetch();
        },
      },
    );
  };

  const handleAttentionTaskComplete = () => {
    const id = selectedAttention?.ref_id;
    if (!id) return;
    completeTask.mutate(id, {
      onSuccess: () => {
        haptic('success');
        show('Задача выполнена', 'success');
        closeAttention();
      },
      onError: () => show('Не удалось выполнить задачу', 'error'),
    });
  };

  const handleAttentionTaskSnooze = () => {
    const id = selectedAttention?.ref_id;
    if (!id) return;
    snoozeTask.mutate(
      { id, input: { preset: 'tomorrow' } },
      {
        onSuccess: () => {
          show('Задача перенесена на завтра', 'success');
          closeAttention();
        },
        onError: () => show('Не удалось перенести задачу', 'error'),
      },
    );
  };

  const handleAttentionEmailTask = () => {
    const id = selectedAttention?.ref_id;
    if (!id) return;
    createTaskFromThread.mutate(id, {
      onSuccess: (result) => {
        show(`Задача создана: ${result.task.title}`, 'success');
        closeAttention();
      },
      onError: () => show('Не удалось создать задачу', 'error'),
    });
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
          <SectionHeader title="Ждет решения" />
          <Card className="card-strong divide-y divide-[var(--hairline)] overflow-hidden !p-0">
            {data.needs_attention.map((item) => {
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedAttention(item)}
                  className="flex min-h-[52px] w-full items-center gap-3 px-4 py-2.5 text-left"
                >
                  <AttentionIcon item={item} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-medium text-ink">{item.title}</span>
                    {item.subtitle && <span className="block truncate text-[12.5px] text-hint">{item.subtitle}</span>}
                  </span>
                  <span className="shrink-0 rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 text-[12px] font-medium text-[var(--secondary-text)]">
                    {attentionCtaLabel(item)}
                  </span>
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

      <Sheet open={selectedAttention !== null} onClose={closeAttention} title="Решение">
        {selectedAttention && (
          <div className="pb-2">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--secondary-bg)]">
                <AttentionIcon item={selectedAttention} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[16px] font-semibold leading-snug text-ink">{selectedAttention.title}</p>
                {selectedAttention.subtitle && (
                  <p className="mt-1 text-[13px] leading-relaxed text-hint">{selectedAttention.subtitle}</p>
                )}
              </div>
            </div>

            {selectedAttention.kind === 'confirmation' && (
              <>
                <div className="mt-4 rounded-2xl bg-[var(--accent-soft)] px-4 py-3">
                  <p className="text-[12px] font-semibold uppercase tracking-wide text-accent-text">
                    {riskLabel(selectedAttention)}
                  </p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink">{riskHint(selectedAttention)}</p>
                </div>

                {confirmationDetailRows(selectedAttention).length > 0 && (
                  <dl className="mt-4 divide-y divide-hairline rounded-2xl border border-hairline">
                    {confirmationDetailRows(selectedAttention).map((row) => (
                      <div key={row.label} className="grid grid-cols-[96px_1fr] gap-3 px-3.5 py-2.5">
                        <dt className="text-[12.5px] text-hint">{row.label}</dt>
                        <dd className="min-w-0 break-words text-[13px] font-medium text-ink">{row.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}

                <div className="mt-5 flex flex-col gap-2.5">
                  <Button
                    fullWidth
                    variant={selectedAttention.ui_mode === 'strong_confirm' ? 'danger' : 'primary'}
                    busy={decideConfirmation.isPending}
                    icon={<Check size={16} />}
                    onClick={() => handleConfirmationDecision(true)}
                  >
                    {selectedAttention.primary_label ?? 'Подтвердить'}
                  </Button>
                  <Button
                    fullWidth
                    variant="ghost"
                    busy={decideConfirmation.isPending}
                    onClick={() => handleConfirmationDecision(false)}
                  >
                    {selectedAttention.secondary_label ?? 'Отклонить'}
                  </Button>
                </div>
              </>
            )}

            {(selectedAttention.kind === 'overdue_task' || selectedAttention.kind === 'due_task') && (
              <div className="mt-5 flex flex-col gap-2.5">
                <Button fullWidth icon={<Check size={16} />} busy={completeTask.isPending} onClick={handleAttentionTaskComplete}>
                  Готово
                </Button>
                <Button
                  fullWidth
                  variant="secondary"
                  icon={<Clock size={16} />}
                  busy={snoozeTask.isPending}
                  onClick={handleAttentionTaskSnooze}
                >
                  Завтра
                </Button>
                <Button fullWidth variant="ghost" onClick={() => handleAttentionNavigate(ATTENTION_ROUTES[selectedAttention.kind])}>
                  Открыть задачи
                </Button>
              </div>
            )}

            {selectedAttention.kind === 'email' && (
              <div className="mt-5 flex flex-col gap-2.5">
                <Button fullWidth busy={createTaskFromThread.isPending} onClick={handleAttentionEmailTask}>
                  Создать задачу
                </Button>
                <Button fullWidth variant="ghost" onClick={() => handleAttentionNavigate(ATTENTION_ROUTES.email)}>
                  Открыть почту
                </Button>
              </div>
            )}
          </div>
        )}
      </Sheet>
    </Stagger>
  );
}
