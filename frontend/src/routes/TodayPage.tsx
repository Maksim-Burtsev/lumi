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
import type { AttentionItem, SlotSuggestion, Suggestion, TimelineItem, TodaySummary } from '../api/types';
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
import type { TimeDisplayOptions } from '../lib/format';
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';
import { haptic } from '../telegram/webapp';

const TODAY_COPY = {
  en: {
    quietDay: 'Quiet day — focus on important work',
    planReady: 'Plan ready',
    inboxTriaged: 'Inbox triaged',
    digestReady: 'Digest ready',
    googleNotConnected: 'Google is not connected — open Settings',
    saveDecisionError: 'Could not save the decision',
    blockAdded: 'Block added to calendar',
    blockConfirmError: 'Could not confirm the block',
    taskDone: 'Task completed',
    taskCompleteError: 'Could not complete the task',
    taskSnoozed: 'Task moved to tomorrow',
    taskSnoozeError: 'Could not move the task',
    taskCreatedPrefix: 'Task created',
    taskCreateError: 'Could not create a task',
    loadError: 'Could not load the day plan.',
    timelineTask: 'Task',
    focus: 'Focus',
    accept: 'Accept',
    free: 'Free',
    buildPlan: 'Build plan',
    triageInbox: 'Triage inbox',
    schedule: 'Schedule',
    emptyTitle: 'No meetings or blocks today',
    emptyHint: 'Tap “Build plan” and Lumi will review tasks and suggest focus blocks.',
    needsAttention: 'Needs decision',
    lumiSuggests: 'Lumi suggests',
    allClear: 'Nothing urgent — everything is under control',
    confirm: 'Confirm',
    dismiss: 'Dismiss',
    done: 'Done',
    tomorrow: 'Tomorrow',
    openTasks: 'Open tasks',
    createTask: 'Create task',
    openInbox: 'Open inbox',
    quickWinsReady: 'Quick wins ready',
    freeSlotReady: 'quick wins ready',
    openTaskList: 'Open task list',
  },
  ru: {
    quietDay: 'Спокойный день — можно заняться важным',
    planReady: 'План готов',
    inboxTriaged: 'Почта разобрана',
    digestReady: 'Дайджест готов',
    googleNotConnected: 'Google не подключен — загляни в Настройки',
    saveDecisionError: 'Не удалось сохранить решение',
    blockAdded: 'Блок добавлен в календарь',
    blockConfirmError: 'Не удалось подтвердить блок',
    taskDone: 'Задача выполнена',
    taskCompleteError: 'Не удалось выполнить задачу',
    taskSnoozed: 'Задача перенесена на завтра',
    taskSnoozeError: 'Не удалось перенести задачу',
    taskCreatedPrefix: 'Задача создана',
    taskCreateError: 'Не удалось создать задачу',
    loadError: 'Не удалось загрузить план дня.',
    timelineTask: 'Задача',
    focus: 'Фокус',
    accept: 'Принять',
    free: 'Свободно',
    buildPlan: 'Собрать план',
    triageInbox: 'Разобрать почту',
    schedule: 'Расписание',
    emptyTitle: 'Сегодня нет встреч и блоков',
    emptyHint: 'Нажми «Собрать план» — Lumi посмотрит задачи и предложит фокус-блоки.',
    needsAttention: 'Ждет решения',
    lumiSuggests: 'Lumi предлагает',
    allClear: 'Ничего срочного — всё под контролем',
    confirm: 'Подтвердить',
    dismiss: 'Отклонить',
    done: 'Готово',
    tomorrow: 'Завтра',
    openTasks: 'Открыть задачи',
    createTask: 'Создать задачу',
    openInbox: 'Открыть почту',
    quickWinsReady: 'Готовые быстрые задачи',
    freeSlotReady: 'готовых быстрых задач',
    openTaskList: 'Открыть список задач',
  },
} satisfies Record<AppLocale, Record<string, string>>;

function enCount(n: number, singular: string, many: string): string {
  return `${n} ${n === 1 ? singular : many}`;
}

function buildSummaryLine(summary: TodaySummary, locale: AppLocale): string {
  const parts: string[] = [];
  if (summary.meetings_today > 0) {
    parts.push(
      locale === 'en'
        ? enCount(summary.meetings_today, 'meeting', 'meetings')
        : countLabel(summary.meetings_today, ['встреча', 'встречи', 'встреч']),
    );
  }
  if (summary.tasks_active > 0) {
    parts.push(
      locale === 'en'
        ? enCount(summary.tasks_active, 'task', 'tasks')
        : countLabel(summary.tasks_active, ['задача', 'задачи', 'задач']),
    );
  }
  if (summary.emails_need_reply > 0) {
    parts.push(
      locale === 'en'
        ? `${summary.emails_need_reply} ${
            summary.emails_need_reply === 1 ? 'email needs a reply' : 'emails need replies'
          }`
        : `${summary.emails_need_reply} ${plural(summary.emails_need_reply, [
            'письмо ждёт ответа',
            'письма ждут ответа',
            'писем ждут ответа',
          ])}`,
    );
  }
  if (parts.length === 0) return TODAY_COPY[locale].quietDay;
  return parts.join(' · ');
}

function formatDateHeadingLocalized(date: Date, locale: AppLocale, timeDisplay: TimeDisplayOptions): string {
  return formatDateHeading(date, { ...timeDisplay, locale });
}

function formatDueLabelLocalized(ts: string, locale: AppLocale, timeDisplay: TimeDisplayOptions): string {
  return formatDueLabel(ts, { ...timeDisplay, locale });
}

function formatSpanMinutesLocalized(startTs: string, endTs: string, locale: AppLocale): string {
  if (locale === 'ru') return formatSpanMinutes(startTs, endTs);
  const minutes = Math.max(0, Math.round((new Date(endTs).getTime() - new Date(startTs).getTime()) / 60_000));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h} hr ${m} min`;
  if (h > 0) return `${h} ${h === 1 ? 'hr' : 'hrs'}`;
  return `${m} min`;
}

function slotTaskCountLabel(count: number, locale: AppLocale): string {
  if (locale === 'en') return `${count} ${count === 1 ? 'quick win' : 'quick wins'} ready`;
  const form = count % 10 === 1 && count % 100 !== 11
    ? 'готовая быстрая задача'
    : [2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)
      ? 'готовые быстрые задачи'
      : 'готовых быстрых задач';
  return `${count} ${form}`;
}

function slotTimelineTitle(slot: SlotSuggestion, locale: AppLocale): string {
  const span = formatSpanMinutesLocalized(slot.start_at, slot.end_at, locale);
  return `${span} ${locale === 'en' ? 'free' : 'свободно'} · ${slotTaskCountLabel(slot.tasks.length, locale)}`;
}

function overdueTasksLabel(count: number, locale: AppLocale): string {
  if (locale === 'en') return enCount(count, 'overdue task', 'overdue tasks');
  return countLabel(count, ['задача просрочена', 'задачи просрочены', 'задач просрочено']);
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

function attentionCtaLabel(item: AttentionItem, locale: AppLocale): string {
  if (item.kind === 'confirmation') {
    if (item.ui_mode === 'review_then_confirm' || item.ui_mode === 'strong_confirm') {
      return locale === 'en' ? 'Review' : 'Проверить';
    }
    return locale === 'en' ? 'Decide' : 'Решить';
  }
  if (item.kind === 'email') return locale === 'en' ? 'Reply' : 'Ответить';
  return locale === 'en' ? 'Sort' : 'Разобрать';
}

function riskLabel(item: AttentionItem, locale: AppLocale): string {
  switch (item.risk_class) {
    case 'write_external':
      return locale === 'en' ? 'External calendar' : 'Внешний календарь';
    case 'external_communication':
      return locale === 'en' ? 'External send' : 'Внешняя отправка';
    case 'destructive':
      return locale === 'en' ? 'Dangerous action' : 'Опасное действие';
    case 'write_internal_memory':
      return locale === 'en' ? 'Memory' : 'Память';
    case 'write_internal_scheduled':
      return locale === 'en' ? 'Automation' : 'Автоматизация';
    case 'write_internal':
      return locale === 'en' ? 'Inside Lumi' : 'Внутри Lumi';
    default:
      return locale === 'en' ? 'Confirmation required' : 'Нужно подтверждение';
  }
}

function riskHint(item: AttentionItem, locale: AppLocale): string {
  switch (item.risk_class) {
    case 'write_external':
      return locale === 'en' ? 'This will create an item outside Lumi.' : 'Будет создана запись вне Lumi.';
    case 'external_communication':
      return locale === 'en'
        ? 'Lumi will draft first and send only after confirmation.'
        : 'Сначала будет черновик, отправка только после подтверждения.';
    case 'destructive':
      return locale === 'en'
        ? 'This action can delete or disconnect data.'
        : 'Действие может удалить или отключить данные.';
    case 'write_internal_memory':
      return locale === 'en'
        ? 'Lumi will save this as long-term memory.'
        : 'Lumi сохранит это как долгосрочную память.';
    case 'write_internal_scheduled':
      return locale === 'en' ? 'Lumi will enable a recurring action.' : 'Lumi включит регулярное действие.';
    case 'write_internal':
      return locale === 'en' ? 'This change stays inside Lumi.' : 'Изменение останется внутри Lumi.';
    default:
      return locale === 'en' ? 'Review the details before deciding.' : 'Проверь детали перед решением.';
  }
}

function payloadText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

function payloadDate(value: unknown, locale: AppLocale, timeDisplay: TimeDisplayOptions): string | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return formatDueLabelLocalized(date.toISOString(), locale, timeDisplay);
}

function confirmationDetailRows(item: AttentionItem, locale: AppLocale, timeDisplay: TimeDisplayOptions): { label: string; value: string }[] {
  const payload = item.action_payload ?? {};
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null) => {
    if (value) rows.push({ label, value });
  };

  switch (item.action_type) {
    case 'create_google_calendar_event':
      push(locale === 'en' ? 'Action' : 'Действие', locale === 'en' ? 'Add to Google Calendar' : 'Добавить в Google Calendar');
      push(locale === 'en' ? 'Title' : 'Название', payloadText(payload.title));
      push(locale === 'en' ? 'Start' : 'Начало', payloadDate(payload.start_at_local, locale, timeDisplay));
      push(locale === 'en' ? 'End' : 'Конец', payloadDate(payload.end_at_local, locale, timeDisplay));
      break;
    case 'store_memory':
      push(locale === 'en' ? 'Remember' : 'Запомнить', payloadText(payload.text));
      push(locale === 'en' ? 'Type' : 'Тип', payloadText(payload.kind));
      break;
    case 'create_task':
      push(locale === 'en' ? 'Task' : 'Задача', payloadText(payload.title));
      push(locale === 'en' ? 'Due' : 'Срок', payloadDate(payload.due_at_local, locale, timeDisplay));
      push(locale === 'en' ? 'Reminder' : 'Напоминание', payloadDate(payload.reminder_at_local, locale, timeDisplay));
      push(locale === 'en' ? 'Project' : 'Проект', payloadText(payload.project));
      break;
    case 'create_automation':
      push(locale === 'en' ? 'Automation' : 'Автоматизация', payloadText(payload.title));
      push(locale === 'en' ? 'Schedule' : 'Расписание', payloadText(payload.cron_expression));
      push(locale === 'en' ? 'Time zone' : 'Часовой пояс', payloadText(payload.timezone));
      break;
    default:
      push(locale === 'en' ? 'Action' : 'Действие', item.action_type ?? null);
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
  const locale = useAppLocale();
  const timeDisplay = useTimeDisplay();
  const copy = TODAY_COPY[locale];
  const todayQuery = useToday();
  const navigate = useNavigate();
  const { show } = useToast();
  const [expandedAttentionId, setExpandedAttentionId] = useState<string | null>(null);
  const [decisionInFlightId, setDecisionInFlightId] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<SlotSuggestion | null>(null);
  const confirmBlock = useConfirmBlock();
  const decideConfirmation = useDecideConfirmation();
  const completeTask = useCompleteTask('today');
  const snoozeTask = useSnoozeTask('today');
  const createTaskFromThread = useCreateTaskFromThread();

  const planAction = useAgentRunAction({
    start: () => api.planDay(),
    invalidate: [qk.eventsAll, qk.freeSlotsAll, qk.tasksAll],
    successMessage: copy.planReady,
  });

  const triageAction = useAgentRunAction({
    start: () => api.runEmailTriage(),
    invalidate: [qk.inbox],
    successMessage: copy.inboxTriaged,
    onApiError: (error) => {
      if (error.status === 409 && error.error === 'google_not_connected') {
        show(copy.googleNotConnected, 'info');
        return true;
      }
      return false;
    },
  });

  const digestAction = useAgentRunAction({
    start: () => api.runNewsDigest(),
    invalidate: [qk.digests],
    successMessage: copy.digestReady,
  });

  const handleConfirmationDecision = (item: AttentionItem, accept: boolean) => {
    const id = item.ref_id;
    if (!id || decisionInFlightId) return;
    setDecisionInFlightId(id);
    decideConfirmation.mutate(
      { id, accept },
      {
        onSuccess: (result) => {
          haptic(accept ? 'success' : 'light');
          show(result.result_text, accept ? 'success' : 'info');
          setExpandedAttentionId((current) => (current === item.id ? null : current));
        },
        onError: () => {
          show(copy.saveDecisionError, 'error');
          void todayQuery.refetch();
        },
        onSettled: () => setDecisionInFlightId(null),
      },
    );
  };

  const handleConfirmBlock = (blockId: string) => {
    confirmBlock.mutate(blockId, {
      onSuccess: () => show(copy.blockAdded, 'success'),
      onError: () => show(copy.blockConfirmError, 'error'),
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

  const handleAttentionNavigate = (route: string) => {
    setExpandedAttentionId(null);
    navigate(route);
  };

  const handleAttentionTaskComplete = (item: AttentionItem) => {
    const id = item.ref_id;
    if (!id) return;
    completeTask.mutate(id, {
      onSuccess: () => {
        haptic('success');
        show(copy.taskDone, 'success');
        setExpandedAttentionId((current) => (current === item.id ? null : current));
      },
      onError: () => show(copy.taskCompleteError, 'error'),
    });
  };

  const handleAttentionTaskSnooze = (item: AttentionItem) => {
    const id = item.ref_id;
    if (!id) return;
    snoozeTask.mutate(
      { id, input: { preset: 'tomorrow' } },
      {
        onSuccess: () => {
          show(copy.taskSnoozed, 'success');
          setExpandedAttentionId((current) => (current === item.id ? null : current));
        },
        onError: () => show(copy.taskSnoozeError, 'error'),
      },
    );
  };

  const handleAttentionEmailTask = (item: AttentionItem) => {
    const id = item.ref_id;
    if (!id) return;
    createTaskFromThread.mutate(id, {
      onSuccess: (result) => {
        show(`${copy.taskCreatedPrefix}: ${result.task.title}`, 'success');
        setExpandedAttentionId((current) => (current === item.id ? null : current));
      },
      onError: () => show(copy.taskCreateError, 'error'),
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
    return <ErrorState message={copy.loadError} onRetry={() => void todayQuery.refetch()} />;
  }

  const data = todayQuery.data;
  const date = new Date(`${data.date}T00:00:00`);
  const nowMs = Date.now();
  const isTodayPayload = date.toDateString() === new Date().toDateString();

  const timelineItems: TimelineEntry[] = data.timeline
    .filter((item: TimelineItem) => item.status !== 'cancelled')
    .filter((item: TimelineItem) => !(
      isTodayPayload && item.kind === 'proposed' && new Date(item.end_at).getTime() <= nowMs
    ))
    .map((item) => ({
      id: item.id,
      kind: item.kind,
      title: item.title,
      start_at: item.start_at,
      end_at: item.end_at,
      subtitle:
        item.kind === 'task'
          ? copy.timelineTask
          : item.source === 'google'
            ? 'Google'
            : item.source === 'yandex'
              ? locale === 'en' ? 'Yandex' : 'Яндекс'
              : item.kind === 'focus'
                ? copy.focus
                : undefined,
      action:
        item.kind === 'proposed'
          ? {
              label: copy.accept,
              onClick: () => handleConfirmBlock(item.id),
              busy: confirmBlock.isPending,
            }
          : undefined,
    }));
  const slotEntries: TimelineEntry[] = (data.slot_suggestions ?? [])
    .filter((slot) => !isTodayPayload || new Date(slot.end_at).getTime() > nowMs)
    .map((slot) => ({
      id: `slot-${slot.id}`,
      kind: 'free' as const,
      title: slotTimelineTitle(slot, locale),
      start_at: slot.start_at,
      end_at: slot.end_at,
      subtitle: slot.reason ?? slot.tasks.slice(0, 2).map((task) => task.title).join(' · '),
      onPress: () => setSelectedSlot(slot),
    }));

  const rawEntries = [...timelineItems, ...slotEntries]
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());

  // Agenda rhythm: surface real gaps between items as ghost "free" rows,
  // so back-to-back meetings and 2-hour windows look different.
  const timelineEntries: TimelineEntry[] = [];
  rawEntries.forEach((entry, i) => {
    if (i > 0) {
      const prevEnd = new Date(rawEntries[i - 1].end_at).getTime();
      const start = new Date(entry.start_at).getTime();
      const end = new Date(entry.end_at).getTime();
      const gapMin = Math.round((start - prevEnd) / 60000);
      if (gapMin >= 30 && (!isTodayPayload || (start > nowMs && end > nowMs))) {
        timelineEntries.push({
          id: `gap-${i}`,
          kind: 'free',
          title: `${copy.free} · ${formatSpanMinutesLocalized(rawEntries[i - 1].end_at, entry.start_at, locale)}`,
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
            <p className="mt-1 text-[13px] text-hint">{formatDateHeadingLocalized(date, locale, timeDisplay)}</p>
            <p className="tnum mt-3 text-[15px] leading-relaxed text-ink">{buildSummaryLine(data.summary, locale)}</p>
            {data.summary.tasks_overdue > 0 && (
              <div className="mt-2.5">
                <StatPill
                  tone="danger"
                  label={overdueTasksLabel(data.summary.tasks_overdue, locale)}
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
                {copy.buildPlan}
              </Button>
              <Button
                variant="secondary"
                icon={<Mail size={16} />}
                busy={triageAction.isRunning}
                onClick={triageAction.trigger}
              >
                {copy.triageInbox}
              </Button>
            </div>
          </div>
        </Card>
      </Rise>

      {/* ----------------------------------------------------------- Timeline */}
      <Rise>
        <SectionHeader title={copy.schedule} />
        {timelineEntries.length > 0 ? (
          <Timeline entries={timelineEntries} />
        ) : (
          <EmptyState
            icon={CalendarDays}
            title={copy.emptyTitle}
            hint={copy.emptyHint}
          />
        )}
      </Rise>

      {/* ----------------------------------------------------------- Needs attention */}
      {data.needs_attention.length > 0 && (
        <div>
          <SectionHeader title={copy.needsAttention} />
          <Card className="card-strong divide-y divide-[var(--hairline)] overflow-hidden !p-0">
            {data.needs_attention.map((item) => {
              const expanded = expandedAttentionId === item.id;
              const detailRows = confirmationDetailRows(item, locale, timeDisplay);
              return (
                <div key={item.id}>
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setExpandedAttentionId((current) => (current === item.id ? null : item.id))}
                    className="flex min-h-[52px] w-full items-center gap-3 px-4 py-2.5 text-left"
                  >
                    <AttentionIcon item={item} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium text-ink">{item.title}</span>
                      {item.subtitle && <span className="block truncate text-[12.5px] text-hint">{item.subtitle}</span>}
                    </span>
                    <span className="shrink-0 rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 text-[12px] font-medium text-[var(--secondary-text)]">
                      {attentionCtaLabel(item, locale)}
                    </span>
                  </button>

                  {expanded && (
                    <div className="border-t border-hairline px-4 pb-4 pt-1">
                      {item.kind === 'confirmation' && (
                        <>
                          <div className="rounded-2xl bg-[var(--accent-soft)] px-4 py-3">
                            <p className="text-[12px] font-semibold uppercase tracking-wide text-accent-text">
                              {riskLabel(item, locale)}
                            </p>
                            <p className="mt-1 text-[13px] leading-relaxed text-ink">{riskHint(item, locale)}</p>
                          </div>

                          {detailRows.length > 0 && (
                            <dl className="mt-3 divide-y divide-hairline rounded-2xl border border-hairline">
                              {detailRows.map((row) => (
                                <div key={row.label} className="grid grid-cols-[96px_1fr] gap-3 px-3.5 py-2.5">
                                  <dt className="text-[12.5px] text-hint">{row.label}</dt>
                                  <dd className="min-w-0 break-words text-[13px] font-medium text-ink">{row.value}</dd>
                                </div>
                              ))}
                            </dl>
                          )}

                          <div className="mt-4 flex flex-col gap-2.5">
                            <Button
                              fullWidth
                              variant={item.ui_mode === 'strong_confirm' ? 'danger' : 'primary'}
                              busy={decideConfirmation.isPending && decisionInFlightId === item.ref_id}
                              icon={<Check size={16} />}
                              onClick={() => handleConfirmationDecision(item, true)}
                            >
                              {item.primary_label ?? copy.confirm}
                            </Button>
                            <Button
                              fullWidth
                              variant="ghost"
                              busy={decideConfirmation.isPending && decisionInFlightId === item.ref_id}
                              onClick={() => handleConfirmationDecision(item, false)}
                            >
                              {item.secondary_label ?? copy.dismiss}
                            </Button>
                          </div>
                        </>
                      )}

                      {(item.kind === 'overdue_task' || item.kind === 'due_task') && (
                        <div className="flex flex-col gap-2.5">
                          <Button
                            fullWidth
                            icon={<Check size={16} />}
                            busy={completeTask.isPending}
                            onClick={() => handleAttentionTaskComplete(item)}
                          >
                            {copy.done}
                          </Button>
                          <Button
                            fullWidth
                            variant="secondary"
                            icon={<Clock size={16} />}
                            busy={snoozeTask.isPending}
                            onClick={() => handleAttentionTaskSnooze(item)}
                          >
                            {copy.tomorrow}
                          </Button>
                          <Button fullWidth variant="ghost" onClick={() => handleAttentionNavigate(ATTENTION_ROUTES[item.kind])}>
                            {copy.openTasks}
                          </Button>
                        </div>
                      )}

                      {item.kind === 'email' && (
                        <div className="flex flex-col gap-2.5">
                          <Button
                            fullWidth
                            busy={createTaskFromThread.isPending}
                            onClick={() => handleAttentionEmailTask(item)}
                          >
                            {copy.createTask}
                          </Button>
                          <Button fullWidth variant="ghost" onClick={() => handleAttentionNavigate(ATTENTION_ROUTES.email)}>
                            {copy.openInbox}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </Card>
        </div>
      )}

      {/* ----------------------------------------------------------- Suggestions */}
      {data.suggestions.length > 0 && (
        <Rise>
          <SectionHeader title={copy.lumiSuggests} />
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
                    {copy.accept}
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
            {copy.allClear}
          </div>
        </Rise>
      )}

      {selectedSlot && (
        <Sheet open onClose={() => setSelectedSlot(null)} title={copy.quickWinsReady} closeLabel={copy.dismiss}>
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] px-3.5 py-3">
            <p className="tnum text-[14px] font-semibold text-ink">
              {formatSpanMinutesLocalized(selectedSlot.start_at, selectedSlot.end_at, locale)}
            </p>
            {selectedSlot.reason && <p className="mt-1 text-[12.5px] leading-relaxed text-hint">{selectedSlot.reason}</p>}
          </div>
          <div className="mt-3 space-y-2.5">
            {selectedSlot.tasks.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => {
                  setSelectedSlot(null);
                  navigate('/tasks');
                }}
                className="flex w-full items-center gap-3 rounded-2xl border border-hairline bg-[var(--surface)] px-3.5 py-3 text-left active:bg-[rgba(255,255,255,0.04)]"
              >
                <Sparkles size={15} className="shrink-0 text-accent-text" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-semibold text-ink">{task.title}</span>
                  <span className="block truncate text-[12.5px] text-hint">
                    {[task.project, task.estimated_minutes ? `${task.estimated_minutes} min` : null].filter(Boolean).join(' · ')}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <Button fullWidth variant="secondary" className="mt-4" onClick={() => {
            setSelectedSlot(null);
            navigate('/tasks');
          }}>
            {copy.openTaskList}
          </Button>
        </Sheet>
      )}
    </Stagger>
  );
}
