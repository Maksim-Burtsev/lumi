import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock,
  HelpCircle,
  ListTodo,
  Play,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../api/client';
import {
  qk,
  useAgentRunAction,
  useCompleteTask,
  useConfirmBlock,
  useDeleteCalendarPrivateNote,
  useDecideConfirmation,
  useSnoozeTask,
  useStartFocusSession,
  useToday,
  useUpdateCalendarPrivateNote,
} from '../api/hooks';
import type {
  AttentionItem,
  SlotSuggestion,
  Suggestion,
  Task,
  TimelineItem,
  TodayCapacity,
  TodaySummary,
} from '../api/types';
import { PRIVATE_NOTE_MAX_CHARS, PrivateNoteSection } from '../components/calendar/PrivateNoteSection';
import { prepareFocusAlarm } from '../components/focus/FocusTimerCoordinator';
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
import {
  countLabel,
  formatDateHeading,
  formatDueLabel,
  formatSpanMinutes,
  formatTime,
  formatTimeRange,
} from '../lib/format';
import type { TimeDisplayOptions } from '../lib/format';
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';
import { haptic } from '../telegram/webapp';

const TODAY_COPY = {
  en: {
    quietDay: 'Quiet day — focus on important work',
    tomorrowReady: 'Tomorrow is planned',
    dayReplanned: 'The rest of the day is replanned',
    saveDecisionError: 'Could not save the decision',
    blockAdded: 'Block added to calendar',
    blockConfirmError: 'Could not confirm the block',
    taskDone: 'Task completed',
    taskCompleteError: 'Could not complete the task',
    taskSnoozed: 'Task moved to tomorrow',
    taskSnoozeError: 'Could not move the task',
    loading: 'Loading workday',
    loadError: 'Could not load the day plan.',
    timelineTask: 'Task',
    workBlock: 'WorkBlock',
    actualFocus: 'Actual focus',
    proposal: 'Lumi proposal',
    validUntil: 'valid until',
    accept: 'Accept',
    free: 'Free',
    workday: 'Workday',
    capacity: 'Capacity',
    capacityFree: 'free',
    meetings: 'Meetings',
    planned: 'WorkBlocks',
    focused: 'Focused',
    overCapacity: 'The day is over capacity',
    nextBlock: 'Next block',
    noNextBlock: 'No upcoming WorkBlock',
    noNextHint: 'Use Calendar to reserve a focused interval.',
    start: 'Start',
    focusStarted: 'Focus started',
    focusStartError: 'Could not start focus',
    planTomorrow: 'Plan tomorrow',
    replanRemaining: 'Replan remaining',
    schedule: 'Timeline',
    emptyTitle: 'No meetings or blocks today',
    emptyHint: 'Your workday is open. Reserve a WorkBlock in Calendar when you need one.',
    plannedTasks: 'Planned tasks',
    noPlannedTasks: 'No tasks planned for today',
    addFromTasks: 'Choose work from Tasks or keep the day clear.',
    needsAttention: 'Needs decision',
    lumiSuggests: 'Lumi suggests',
    allClear: 'Nothing urgent — everything is under control',
    confirm: 'Confirm',
    dismiss: 'Dismiss',
    done: 'Done',
    tomorrow: 'Tomorrow',
    openTasks: 'Open tasks',
    quickWinsReady: 'Quick wins ready',
    freeSlotReady: 'quick wins ready',
    openTaskList: 'Open task list',
  },
  ru: {
    quietDay: 'Спокойный день — можно заняться важным',
    tomorrowReady: 'Завтра спланировано',
    dayReplanned: 'Остаток дня перепланирован',
    saveDecisionError: 'Не удалось сохранить решение',
    blockAdded: 'Блок добавлен в календарь',
    blockConfirmError: 'Не удалось подтвердить блок',
    taskDone: 'Задача выполнена',
    taskCompleteError: 'Не удалось выполнить задачу',
    taskSnoozed: 'Задача перенесена на завтра',
    taskSnoozeError: 'Не удалось перенести задачу',
    loading: 'Загружаем рабочий день',
    loadError: 'Не удалось загрузить план дня.',
    timelineTask: 'Задача',
    workBlock: 'WorkBlock',
    actualFocus: 'Факт фокуса',
    proposal: 'Предложение Lumi',
    validUntil: 'до',
    accept: 'Принять',
    free: 'Свободно',
    workday: 'Рабочий день',
    capacity: 'Загрузка',
    capacityFree: 'свободно',
    meetings: 'Встречи',
    planned: 'WorkBlocks',
    focused: 'Сделано',
    overCapacity: 'День перегружен',
    nextBlock: 'Следующий блок',
    noNextBlock: 'Впереди нет WorkBlock',
    noNextHint: 'Зарезервируй фокусный интервал в Календаре.',
    start: 'Начать',
    focusStarted: 'Фокус запущен',
    focusStartError: 'Не удалось запустить фокус',
    planTomorrow: 'Спланировать завтра',
    replanRemaining: 'Перепланировать остаток',
    schedule: 'Таймлайн',
    emptyTitle: 'Сегодня нет встреч и блоков',
    emptyHint: 'Рабочий день свободен. При необходимости добавь WorkBlock в Календаре.',
    plannedTasks: 'Задачи на сегодня',
    noPlannedTasks: 'На сегодня нет запланированных задач',
    addFromTasks: 'Выбери работу в Задачах или оставь день свободным.',
    needsAttention: 'Ждет решения',
    lumiSuggests: 'Lumi предлагает',
    allClear: 'Ничего срочного — всё под контролем',
    confirm: 'Подтвердить',
    dismiss: 'Отклонить',
    done: 'Готово',
    tomorrow: 'Завтра',
    openTasks: 'Открыть задачи',
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
  return formatSpanMinutes(startTs, endTs, locale);
}

function formatMinutes(minutes: number, locale: AppLocale): string {
  const safeMinutes = Math.max(0, Math.round(minutes));
  const hours = Math.floor(safeMinutes / 60);
  const remainder = safeMinutes % 60;
  if (hours === 0) return `${remainder} ${locale === 'en' ? 'min' : 'мин'}`;
  if (remainder === 0) return `${hours} ${locale === 'en' ? 'h' : 'ч'}`;
  return `${hours} ${locale === 'en' ? 'h' : 'ч'} ${remainder} ${locale === 'en' ? 'min' : 'мин'}`;
}

function workBlockMinutes(item: TimelineItem): number {
  const minutes = Math.round((new Date(item.end_at).getTime() - new Date(item.start_at).getTime()) / 60_000);
  return Math.max(1, Math.min(240, Number.isFinite(minutes) ? minutes : 25));
}

function workBlockBreakMinutes(minutes: number): number {
  if (minutes === 25) return 5;
  if (minutes === 50) return 10;
  if (minutes === 90) return 15;
  return 0;
}

function timelineSubtitle(
  item: TimelineItem,
  locale: AppLocale,
  timeDisplay: TimeDisplayOptions,
  copy: (typeof TODAY_COPY)[AppLocale],
): string | undefined {
  if (item.kind === 'task') return copy.timelineTask;
  if (item.kind === 'focus_session') return copy.actualFocus;
  if (item.kind === 'work_block') return copy.workBlock;
  if (item.kind === 'proposed') {
    return item.expires_at
      ? `${copy.proposal} · ${copy.validUntil} ${formatTime(item.expires_at, timeDisplay)}`
      : copy.proposal;
  }
  if (item.source === 'google') return 'Google';
  if (item.source === 'yandex') return locale === 'en' ? 'Yandex' : 'Яндекс';
  return undefined;
}

function taskMeta(task: Task, locale: AppLocale, timeDisplay: TimeDisplayOptions): string {
  return [
    task.project,
    task.estimated_minutes ? formatMinutes(task.estimated_minutes, locale) : null,
    task.due_at ? formatDueLabelLocalized(task.due_at, locale, timeDisplay) : null,
  ].filter(Boolean).join(' · ');
}

function slotTaskCountLabel(count: number, locale: AppLocale): string {
  if (locale === 'en') return `${count} ${count === 1 ? 'quick win' : 'quick wins'} ready`;
  const form = count % 10 === 1 && count % 100 !== 11
    ? 'задача готова'
    : [2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)
      ? 'задачи готовы'
      : 'задач готово';
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

type ProductAttentionItem = AttentionItem & { kind: Exclude<AttentionItem['kind'], 'email'> };

function isProductAttentionItem(item: AttentionItem): item is ProductAttentionItem {
  return item.kind !== 'email';
}

const ATTENTION_ICONS: Record<ProductAttentionItem['kind'], { icon: LucideIcon; className: string }> = {
  overdue_task: { icon: AlertCircle, className: 'text-danger' },
  due_task: { icon: Clock, className: 'text-accent-text' },
  confirmation: { icon: HelpCircle, className: 'text-hint' },
};

function attentionCtaLabel(item: ProductAttentionItem, locale: AppLocale): string {
  if (item.kind === 'confirmation') {
    if (item.ui_mode === 'review_then_confirm' || item.ui_mode === 'strong_confirm') {
      return locale === 'en' ? 'Review' : 'Проверить';
    }
    return locale === 'en' ? 'Decide' : 'Решить';
  }
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

function AttentionIcon({ item }: { item: ProductAttentionItem }) {
  const meta = ATTENTION_ICONS[item.kind];
  const Icon = meta.icon;
  return <Icon size={17} strokeWidth={1.9} className={`shrink-0 ${meta.className}`} />;
}

function CapacityOverview({
  capacity,
  locale,
  copy,
}: {
  capacity: TodayCapacity;
  locale: AppLocale;
  copy: (typeof TODAY_COPY)[AppLocale];
}) {
  const utilization = Math.max(0, Math.round(capacity.utilization_percent));
  const barWidth = Math.min(100, utilization);
  return (
    <div className="mt-4 border-t border-hairline pt-4" aria-label={copy.capacity}>
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-hint">{copy.capacity}</p>
          <p className="tnum mt-1 text-[18px] font-medium text-ink">
            {formatMinutes(capacity.free_minutes, locale)} {copy.capacityFree}
          </p>
        </div>
        <span className={`tnum text-[13px] font-medium ${capacity.over_capacity ? 'text-danger' : 'text-hint'}`}>
          {utilization}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={copy.capacity}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, utilization)}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--secondary-bg)]"
      >
        <div
          className={`h-full rounded-full ${capacity.over_capacity ? 'bg-[var(--danger)]' : 'bg-accent'}`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <dl className="tnum mt-3 grid grid-cols-3 gap-2 text-[11.5px] text-hint">
        <div>
          <dt>{copy.meetings}</dt>
          <dd className="mt-0.5 font-medium text-ink">{formatMinutes(capacity.meeting_minutes, locale)}</dd>
        </div>
        <div>
          <dt>{copy.planned}</dt>
          <dd className="mt-0.5 font-medium text-ink">{formatMinutes(capacity.planned_minutes, locale)}</dd>
        </div>
        <div>
          <dt>{copy.focused}</dt>
          <dd className="mt-0.5 font-medium text-ink">{formatMinutes(capacity.focus_minutes, locale)}</dd>
        </div>
      </dl>
      {capacity.over_capacity && <p className="mt-3 text-[12.5px] font-medium text-danger">{copy.overCapacity}</p>}
    </div>
  );
}

function TodaySkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label}>
      <div aria-hidden className="card p-5">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="mt-2.5 h-3.5 w-36" />
        <Skeleton className="mt-3.5 h-4 w-64" />
        <div className="mt-5 flex gap-2.5">
          <Skeleton className="h-11 w-36 !rounded-full" />
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
  const noteCopy = locale === 'en'
    ? {
        maxError: `Personal note is limited to ${PRIVATE_NOTE_MAX_CHARS} characters`,
        deleted: 'Note deleted',
        deleteFailed: 'Could not delete note',
        saved: 'Note saved',
        saveFailed: 'Could not save note',
      }
    : {
        maxError: `Личная заметка — до ${PRIVATE_NOTE_MAX_CHARS} символов`,
        deleted: 'Заметка удалена',
        deleteFailed: 'Не удалось удалить заметку',
        saved: 'Заметка сохранена',
        saveFailed: 'Не удалось сохранить заметку',
      };
  const todayQuery = useToday();
  const navigate = useNavigate();
  const { show } = useToast();
  const [expandedAttentionId, setExpandedAttentionId] = useState<string | null>(null);
  const [decisionInFlightId, setDecisionInFlightId] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<SlotSuggestion | null>(null);
  const confirmBlock = useConfirmBlock();
  const decideConfirmation = useDecideConfirmation();
  const startFocus = useStartFocusSession();
  const completeTask = useCompleteTask('today');
  const snoozeTask = useSnoozeTask('today');
  const updatePrivateNote = useUpdateCalendarPrivateNote();
  const deletePrivateNote = useDeleteCalendarPrivateNote();
  const [selectedTimelineEvent, setSelectedTimelineEvent] = useState<TimelineItem | null>(null);
  const [noteEditing, setNoteEditing] = useState(false);
  const [noteExpanded, setNoteExpanded] = useState(false);
  const [noteDraft, setNoteDraft] = useState('');
  const [noteError, setNoteError] = useState<string | null>(null);

  useEffect(() => {
    setNoteEditing(false);
    setNoteExpanded(false);
    setNoteDraft(selectedTimelineEvent?.private_note ?? '');
    setNoteError(null);
  }, [selectedTimelineEvent?.id, selectedTimelineEvent?.private_note]);

  const planTomorrowAction = useAgentRunAction({
    start: () => api.planDay({ mode: 'tomorrow' }),
    invalidate: [qk.eventsAll, qk.freeSlotsAll, qk.tasksAll],
    successMessage: copy.tomorrowReady,
  });
  const replanAction = useAgentRunAction({
    start: () => api.planDay({ mode: 'replan' }),
    invalidate: [qk.eventsAll, qk.freeSlotsAll, qk.tasksAll],
    successMessage: copy.dayReplanned,
  });

  const handleStartNextBlock = (block: TimelineItem) => {
    if (startFocus.isPending || block.kind !== 'work_block' || block.status !== 'confirmed') return;
    const plannedMinutes = workBlockMinutes(block);
    prepareFocusAlarm();
    startFocus.mutate(
      {
        planned_event_id: block.id,
        intention: block.title,
        planned_minutes: plannedMinutes,
        break_minutes: workBlockBreakMinutes(plannedMinutes),
      },
      {
        onSuccess: () => {
          haptic('success');
          show(copy.focusStarted, 'success');
          navigate('/sessions');
        },
        onError: () => show(copy.focusStartError, 'error'),
      },
    );
  };

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

  const patchSelectedEventNote = (event: {
    id: string;
    private_note?: string | null;
    private_note_summary?: string | null;
    private_note_summary_status?: TimelineItem['private_note_summary_status'];
    private_note_updated_at?: string | null;
    private_note_summary_updated_at?: string | null;
  }) => {
    setSelectedTimelineEvent((current) => {
      if (!current || current.id !== event.id) return current;
      return {
        ...current,
        private_note: event.private_note ?? null,
        private_note_summary: event.private_note_summary ?? null,
        private_note_summary_status: event.private_note_summary_status ?? null,
        private_note_updated_at: event.private_note_updated_at ?? null,
        private_note_summary_updated_at: event.private_note_summary_updated_at ?? null,
      };
    });
  };

  const closeEventSheet = () => {
    setSelectedTimelineEvent(null);
    setNoteEditing(false);
    setNoteExpanded(false);
    setNoteError(null);
  };

  const savePrivateNote = () => {
    if (!selectedTimelineEvent) return;
    if (noteDraft.length > PRIVATE_NOTE_MAX_CHARS) {
      setNoteError(noteCopy.maxError);
      return;
    }
    const note = noteDraft.trim();
    setNoteError(null);
    if (!note) {
      if (!selectedTimelineEvent.private_note) {
        setNoteEditing(false);
        return;
      }
      deletePrivateNote.mutate(selectedTimelineEvent.id, {
        onSuccess: ({ event }) => {
          haptic('success');
          show(noteCopy.deleted, 'success');
          patchSelectedEventNote(event);
          setNoteEditing(false);
        },
        onError: () => show(noteCopy.deleteFailed, 'error'),
      });
      return;
    }
    updatePrivateNote.mutate(
      { id: selectedTimelineEvent.id, input: { note } },
      {
        onSuccess: ({ event }) => {
          haptic('success');
          show(noteCopy.saved, 'success');
          patchSelectedEventNote(event);
          setNoteEditing(false);
          setNoteExpanded(false);
        },
        onError: () => show(noteCopy.saveFailed, 'error'),
      },
    );
  };

  const removePrivateNote = () => {
    if (!selectedTimelineEvent?.private_note) return;
    deletePrivateNote.mutate(selectedTimelineEvent.id, {
      onSuccess: ({ event }) => {
        haptic('success');
        show(noteCopy.deleted, 'success');
        patchSelectedEventNote(event);
        setNoteEditing(false);
      },
      onError: () => show(noteCopy.deleteFailed, 'error'),
    });
  };

  const openTimelineEvent = (item: TimelineItem) => {
    setSelectedTimelineEvent(item);
  };

  const suggestionBusy = (suggestion: Suggestion): boolean => {
    switch (suggestion.action.type) {
      case 'confirm_block':
        return confirmBlock.isPending;
    }
    return false;
  };

  if (todayQuery.isPending) return <TodaySkeleton label={copy.loading} />;
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
      subtitle: timelineSubtitle(item, locale, timeDisplay, copy),
      hasPersonalNote: Boolean(item.private_note?.trim()),
      onPress: item.kind === 'task' || item.kind === 'focus_session' ? undefined : () => openTimelineEvent(item),
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

  const timelineEntries = [...timelineItems, ...slotEntries]
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());
  const attentionItems = data.needs_attention.filter(isProductAttentionItem);
  const suggestions = data.suggestions.filter(
    (suggestion) =>
      suggestion.kind !== 'email_triage' &&
      suggestion.kind !== 'news_digest' &&
      suggestion.kind !== 'plan_day' &&
      suggestion.action.type !== 'run_triage' &&
      suggestion.action.type !== 'run_digest' &&
      suggestion.action.type !== 'plan_day',
  );
  const showSuggestions = suggestions.length > 0 && slotEntries.length === 0;
  const showAllClear = attentionItems.length === 0 && !showSuggestions && slotEntries.length === 0;
  const nextBlock = data.next_block;
  const canStartNextBlock = nextBlock?.kind === 'work_block' && nextBlock.status === 'confirmed';

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

            <CapacityOverview capacity={data.capacity} locale={locale} copy={copy} />

            <div className="mt-4 border-t border-hairline pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-hint">{copy.nextBlock}</p>
              {nextBlock ? (
                <div className="mt-2 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15px] font-semibold text-ink">{nextBlock.title}</p>
                    <p className="tnum mt-0.5 text-[12.5px] text-hint">
                      {formatTimeRange(nextBlock.start_at, nextBlock.end_at, timeDisplay)}
                    </p>
                  </div>
                  {canStartNextBlock && (
                    <Button
                      size="sm"
                      icon={<Play size={14} fill="currentColor" />}
                      busy={startFocus.isPending}
                      onClick={() => handleStartNextBlock(nextBlock)}
                    >
                      {copy.start}
                    </Button>
                  )}
                </div>
              ) : (
                <div className="mt-2">
                  <p className="text-[14px] font-medium text-ink">{copy.noNextBlock}</p>
                  <p className="mt-0.5 text-[12.5px] text-hint">{copy.noNextHint}</p>
                </div>
              )}
            </div>

            <div className="mt-4 flex flex-wrap gap-2.5">
              <Button
                variant="secondary"
                icon={<CalendarDays size={16} />}
                busy={planTomorrowAction.isRunning}
                disabled={replanAction.isRunning}
                onClick={() => planTomorrowAction.trigger()}
              >
                {copy.planTomorrow}
              </Button>
              {data.planning.can_replan && (
                <Button
                  variant="ghost"
                  icon={<RotateCcw size={15} />}
                  busy={replanAction.isRunning}
                  disabled={planTomorrowAction.isRunning}
                  onClick={() => replanAction.trigger()}
                >
                  {copy.replanRemaining}
                </Button>
              )}
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

      {/* ----------------------------------------------------------- Planned tasks */}
      <Rise>
        <SectionHeader
          title={copy.plannedTasks}
          action={(
            <button
              type="button"
              onClick={() => navigate('/tasks')}
              className="text-[12.5px] font-medium text-accent-text"
            >
              {copy.openTasks}
            </button>
          )}
        />
        <Card className="card-strong overflow-hidden !p-0">
          {data.planned_tasks.length > 0 ? (
            <div className="divide-y divide-hairline">
              {data.planned_tasks.map((task) => {
                const meta = taskMeta(task, locale, timeDisplay);
                return (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => navigate('/tasks')}
                    className="flex min-h-[52px] w-full items-center gap-3 px-4 py-2.5 text-left transition-colors active:bg-[var(--secondary-bg)]"
                  >
                    <span
                      aria-hidden
                      className="h-2 w-2 shrink-0 rounded-full bg-[var(--success)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium text-ink">{task.title}</span>
                      {meta && <span className="block truncate text-[12px] text-hint">{meta}</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="flex items-start gap-3 px-4 py-4">
              <ListTodo size={17} className="mt-0.5 shrink-0 text-hint" />
              <div>
                <p className="text-[13.5px] font-medium text-ink">{copy.noPlannedTasks}</p>
                <p className="mt-0.5 text-[12.5px] leading-relaxed text-hint">{copy.addFromTasks}</p>
              </div>
            </div>
          )}
        </Card>
      </Rise>

      {/* ----------------------------------------------------------- Needs attention */}
      {attentionItems.length > 0 && (
        <div>
          <SectionHeader title={copy.needsAttention} />
          <Card className="card-strong divide-y divide-[var(--hairline)] overflow-hidden !p-0">
            {attentionItems.map((item) => {
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
                          <Button fullWidth variant="ghost" onClick={() => handleAttentionNavigate('/tasks')}>
                            {copy.openTasks}
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
      {showSuggestions && (
        <Rise>
          <SectionHeader title={copy.lumiSuggests} />
          <div className="flex flex-col gap-3">
            {suggestions.map((suggestion) => (
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
      {showAllClear && (
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

      <Sheet open={selectedTimelineEvent !== null} onClose={closeEventSheet} title={selectedTimelineEvent?.title ?? ''}>
        {selectedTimelineEvent && (
          <div className="space-y-4">
            <p className="tnum text-[14px] text-hint">
              {formatTimeRange(selectedTimelineEvent.start_at, selectedTimelineEvent.end_at, timeDisplay)}
              {selectedTimelineEvent.source === 'google' && ' · Google'}
              {selectedTimelineEvent.source === 'yandex' && (locale === 'en' ? ' · Yandex' : ' · Яндекс')}
              {selectedTimelineEvent.status === 'proposed' && (locale === 'en' ? ' · Lumi proposal' : ' · предложение Lumi')}
            </p>
            <PrivateNoteSection
              event={selectedTimelineEvent}
              editing={noteEditing}
              expanded={noteExpanded}
              draft={noteDraft}
              error={noteError}
              saving={updatePrivateNote.isPending || deletePrivateNote.isPending}
              deleting={deletePrivateNote.isPending}
              onEdit={() => {
                setNoteDraft(selectedTimelineEvent.private_note ?? '');
                setNoteError(null);
                setNoteEditing(true);
              }}
              onCancel={() => {
                setNoteDraft(selectedTimelineEvent.private_note ?? '');
                setNoteError(null);
                setNoteEditing(false);
              }}
              onDelete={removePrivateNote}
              onDraftChange={setNoteDraft}
              onExpandedChange={setNoteExpanded}
              onSave={savePrivateNote}
            />
          </div>
        )}
      </Sheet>
    </Stagger>
  );
}
