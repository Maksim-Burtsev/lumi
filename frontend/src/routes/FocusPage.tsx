import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ClipboardPenLine,
  Clock3,
  Flame,
  FlaskConical,
  Folder,
  Loader2,
  Pencil,
  Plus,
  Search,
  Timer,
  Trash2,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react';
import {
  useAbandonFocusSession,
  useDeleteFocusSession,
  useDismissFocusInsight,
  useFinishFocusBreak,
  useFinishFocusSession,
  useFocusInsights,
  useFocusSession,
  useFocusSessions,
  useFocusState,
  useFocusSummary,
  useFocusTasks,
  useInfiniteFocusSessions,
  useLogFocusSession,
  useProjects,
  useStartFocusSession,
  useTryFocusInsight,
  useUpdateFocusSession,
} from '../api/hooks';
import type { FocusPeriod } from '../api/client';
import type {
  FocusCyclePreset,
  FocusDailyActivity,
  FocusInsight,
  FocusReflectionOutcome,
  FocusSession,
  FocusSummaryResponse,
  Project,
  Task,
} from '../api/types';
import { Button } from '../components/ui/Button';
import { prepareFocusAlarm, silenceFocusAlarm } from '../components/focus/FocusTimerCoordinator';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Sheet } from '../components/ui/Sheet';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import type { AppLocale } from '../lib/i18n';
import { formatTime } from '../lib/format';
import type { TimeDisplayOptions } from '../lib/format';
import { dateTimeInputParts, localPartsToDate, localRangeToIso } from '../lib/focusTime';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';
import { haptic } from '../telegram/webapp';

const DURATIONS = [25, 45, 60];
const DEFAULT_DURATION = 45;
const DEFAULT_FOCUS_CYCLE = { preset: '25/5' as FocusCyclePreset, focusMinutes: 25, breakMinutes: 5 };
const FOCUS_CYCLE_PRESETS = [
  { preset: '25/5' as const, focusMinutes: 25, breakMinutes: 5 },
  { preset: '50/10' as const, focusMinutes: 50, breakMinutes: 10 },
  { preset: '90/15' as const, focusMinutes: 90, breakMinutes: 15 },
] satisfies Array<{ preset: FocusCyclePreset; focusMinutes: number; breakMinutes: number }>;
type MainPeriod = Exclude<FocusPeriod, 'custom'>;

const COPY = {
  en: {
    session: 'Session',
    sessions: 'Sessions',
    noProject: 'No project',
    noTask: 'No task',
    taskStatusActive: 'active',
    taskStatusInbox: 'inbox',
    onlyIntentProject: 'Intent and project only',
    search: 'Search',
    searchTasks: 'Search tasks',
    chooseTask: 'Choose task',
    taskPicker: 'Choose task',
    projectPicker: 'Choose project',
    chooseProject: 'Choose project',
    searchProjects: 'Search projects',
    customProject: 'Use custom project',
    nothingFound: 'Nothing found.',
    duration: 'Duration',
    customDuration: 'Custom duration',
    cycle: 'Focus / break',
    customCycle: 'Custom',
    focusMinutes: 'Focus minutes',
    breakMinutes: 'Break minutes',
    intention: 'Intent',
    project: 'Project',
    task: 'Task',
    newSession: 'New session',
    startSession: 'Start session',
    startCta: 'Start',
    logSession: 'Log session',
    logShort: 'Log',
    readyTitle: 'Ready for a session?',
    readyBody: 'Start a timer or log work you already did elsewhere.',
    whatWork: 'What will you work on?',
    optionalProject: 'Optional',
    active: 'session running',
    focusModeOn: 'Focus mode is on',
    detailsHistory: 'Details & History',
    detailsHistoryBody: 'See analytics, projects and past sessions',
    editSession: 'Edit session',
    finishSession: 'Finish session',
    stopReview: 'Stop & review',
    stopTimerReview: 'Stop timer & review',
    keepCounting: 'Keep counting',
    overtime: 'over plan',
    timerEnded: 'Timer ended',
    timeIsUp: 'time is up',
    remaining: 'left',
    plan: 'plan',
    finish: 'Finish',
    cancel: 'Cancel',
    cancelTitle: 'Cancel this session?',
    cancelBody: 'The running block will be discarded and will not appear in analytics.',
    cancelAction: 'Discard session',
    finishError: 'Could not finish session',
    cancelError: 'Could not cancel session',
    reflectionTitle: 'Session review',
    outcome: 'Outcome',
    outcomeDone: 'Done',
    outcomeProgress: 'Progress',
    outcomeBlocked: 'Blocked',
    reflectionNote: 'Optional note',
    reflectionNotePlaceholder: 'What matters from this session?',
    advancedReflection: 'Advanced details',
    doneQuestion: 'What got done?',
    donePlaceholder: 'Short result',
    blockersQuestion: 'What got in the way?',
    blockersPlaceholder: 'Distractions, blockers, context',
    nextStep: 'Next step',
    nextStepPlaceholder: 'What happens next?',
    score: 'Focus',
    unscored: 'Not scored',
    saveSession: 'Save session',
    saveBlock: 'Save block',
    today: 'today',
    countSessions: 'sessions',
    sessionsToday: 'sessions today',
    sessionsThisWeek: 'sessions this week',
    sessionsThisMonth: 'sessions this month',
    streak: 'streak',
    dayStreak: 'day streak',
    focusDays: 'focus days',
    analytics: 'Analytics',
    insights: 'Patterns to test',
    insightObserved: 'Observed pattern',
    insightExperiment: 'Experiment',
    insightWhy: 'Why?',
    insightEvidence: 'Evidence',
    insightWindow: 'Window',
    insightSupport: 'Supporting sessions',
    insightConfidence: 'Confidence',
    insightSources: 'Source sessions',
    insightSource: 'Session',
    insightTry: 'Try',
    insightDismiss: 'Dismiss',
    insightTrying: 'Trying',
    insightSafety: 'Try only marks this as an experiment. Lumi won’t change your calendar or settings.',
    insightCorrelation: 'Observed together, not proven as a cause.',
    insightTried: 'Experiment confirmed',
    insightDismissed: 'Pattern dismissed',
    insightTryError: 'Could not confirm the experiment',
    insightDismissError: 'Could not dismiss the pattern',
    insightLoadError: 'Could not load patterns.',
    week: 'Week',
    month: 'Month',
    custom: 'Custom',
    forWeek: 'this week',
    forMonth: 'this month',
    projectsEmpty: 'Projects appear after completed sessions.',
    history: 'History',
    viewAll: 'View all',
    viewAllHistory: 'View all history',
    details: 'Details',
    sessionDetails: 'Session details',
    editReview: 'Edit review',
    deleteSession: 'Delete session',
    deleteTitle: 'Delete session?',
    deleteBody: 'This removes the time block from analytics and history.',
    deleteAction: 'Delete',
    noReflection: 'No review yet.',
    avgDay: 'Avg/day',
    total: 'Total',
    mostFocused: 'Most focused',
    vsWeekAverage: 'vs prior 4 weeks',
    vsMonthAverage: 'vs prior 4 months',
    morning: 'Morning',
    afternoon: 'Afternoon',
    evening: 'Evening',
    night: 'Night',
    historyEmpty: 'Completed sessions appear here.',
    historyDetails: 'Session history',
    days: 'Days',
    projects: 'Projects',
    projectsThisWeek: 'Projects this week',
    projectsThisMonth: 'Projects this month',
    projectsInRange: 'Projects in range',
    projectsOn: 'Projects on',
    recentSessions: 'Recent sessions',
    sessionsOn: 'Sessions on',
    searchSessions: 'Search sessions',
    selectedDay: 'Selected day',
    allDays: 'All days',
    clearDay: 'Clear day',
    range: 'Range',
    from: 'From',
    to: 'To',
    applyRange: 'Apply range',
    saveChanges: 'Save changes',
    startTime: 'Start time',
    endTime: 'End time',
    startDate: 'Start date',
    endDate: 'End date',
    avgFocusScore: 'avg focus score',
    noSessionsForDay: 'No sessions for this day.',
    startAt: 'Start',
    date: 'Date',
    time: 'Time',
    todayChip: 'Today',
    yesterdayChip: 'Yesterday',
    startEndPreview: 'Start — End',
    durationMinutes: 'Duration, minutes',
    whatDid: 'What did you do?',
    logIntentPlaceholder: 'What did you do?',
    defaultIntention: 'Session',
    startError: 'Could not start session',
    saveError: 'Could not save session',
    logError: 'Could not save block',
    progressLabel: 'Session progress',
    breakProgressLabel: 'Break progress',
    breakRunning: 'break running',
    breakReady: 'Reset before the next block',
    breakEnded: 'Break finished',
    breakRemaining: 'break left',
    finishBreak: 'Finish break',
    skipBreak: 'Skip break',
    finishBreakError: 'Could not finish break',
    planned: 'Planned',
    actual: 'Actual',
    allProjects: 'All projects',
    loadMore: 'Load more',
    loadingMore: 'Loading…',
    invalidRange: 'End must be after start and the session cannot exceed 240 minutes.',
    invalidCustomRange: 'Choose a valid range of up to 180 days.',
    stateError: 'Could not load the active focus session. Your timer may still be running.',
    retry: 'Try again',
  },
  ru: {
    session: 'Сессия',
    sessions: 'Сессии',
    noProject: 'Без проекта',
    noTask: 'Без задачи',
    taskStatusActive: 'активная',
    taskStatusInbox: 'входящая',
    onlyIntentProject: 'Только намерение и проект',
    search: 'Поиск',
    searchTasks: 'Поиск задач',
    chooseTask: 'Выбрать задачу',
    taskPicker: 'Выбор задачи',
    projectPicker: 'Выбор проекта',
    chooseProject: 'Выбрать проект',
    searchProjects: 'Поиск проектов',
    customProject: 'Свой проект',
    nothingFound: 'Ничего не найдено.',
    duration: 'Длительность',
    customDuration: 'Своя длительность',
    cycle: 'Фокус / перерыв',
    customCycle: 'Свой',
    focusMinutes: 'Минут фокуса',
    breakMinutes: 'Минут перерыва',
    intention: 'Намерение',
    project: 'Проект',
    task: 'Задача',
    newSession: 'Новая сессия',
    startSession: 'Начать сессию',
    startCta: 'Старт',
    logSession: 'Залогировать сессию',
    logShort: 'Лог',
    readyTitle: 'Готов к сессии?',
    readyBody: 'Запусти таймер или залогируй блок, который уже сделал в другом месте.',
    whatWork: 'Над чем будешь работать?',
    optionalProject: 'Опционально',
    active: 'идет сессия',
    focusModeOn: 'Фокус-режим включен',
    detailsHistory: 'Детали и история',
    detailsHistoryBody: 'Аналитика, проекты и прошлые сессии',
    editSession: 'Редактировать сессию',
    finishSession: 'Завершить сессию',
    stopReview: 'Стоп и итог',
    stopTimerReview: 'Остановить и заполнить итог',
    keepCounting: 'Продолжить счет',
    overtime: 'сверх плана',
    timerEnded: 'Таймер завершен',
    timeIsUp: 'время вышло',
    remaining: 'осталось',
    plan: 'план',
    finish: 'Завершить',
    cancel: 'Отменить',
    cancelTitle: 'Отменить сессию?',
    cancelBody: 'Текущий блок будет удалён и не попадёт в аналитику.',
    cancelAction: 'Удалить сессию',
    finishError: 'Не удалось завершить сессию',
    cancelError: 'Не удалось отменить сессию',
    reflectionTitle: 'Итог сессии',
    outcome: 'Результат',
    outcomeDone: 'Готово',
    outcomeProgress: 'Продвинулся',
    outcomeBlocked: 'Заблокирован',
    reflectionNote: 'Короткая заметка',
    reflectionNotePlaceholder: 'Что важно сохранить после сессии?',
    advancedReflection: 'Дополнительные детали',
    doneQuestion: 'Что сделал?',
    donePlaceholder: 'Коротко зафиксируй результат',
    blockersQuestion: 'Что мешало?',
    blockersPlaceholder: 'Отвлечения, блокеры, контекст',
    nextStep: 'Следующий шаг',
    nextStepPlaceholder: 'Что сделать дальше?',
    score: 'Фокус',
    unscored: 'Без оценки',
    saveSession: 'Сохранить сессию',
    saveBlock: 'Сохранить блок',
    today: 'сегодня',
    countSessions: 'сессий',
    sessionsToday: 'сессий сегодня',
    sessionsThisWeek: 'сессий за неделю',
    sessionsThisMonth: 'сессий за месяц',
    streak: 'стрик',
    dayStreak: 'дней подряд',
    focusDays: 'дни с фокусом',
    analytics: 'Аналитика',
    insights: 'Паттерны для проверки',
    insightObserved: 'Наблюдаемый паттерн',
    insightExperiment: 'Эксперимент',
    insightWhy: 'Почему?',
    insightEvidence: 'Основания',
    insightWindow: 'Период',
    insightSupport: 'Сессий в выборке',
    insightConfidence: 'Уверенность',
    insightSources: 'Исходные сессии',
    insightSource: 'Сессия',
    insightTry: 'Попробовать',
    insightDismiss: 'Скрыть',
    insightTrying: 'Проверяю',
    insightSafety: 'Попробовать — значит только подтвердить эксперимент. Lumi не изменит календарь или настройки.',
    insightCorrelation: 'Наблюдается вместе, но причинная связь не доказана.',
    insightTried: 'Эксперимент подтверждён',
    insightDismissed: 'Паттерн скрыт',
    insightTryError: 'Не удалось подтвердить эксперимент',
    insightDismissError: 'Не удалось скрыть паттерн',
    insightLoadError: 'Не удалось загрузить паттерны.',
    week: 'Неделя',
    month: 'Месяц',
    custom: 'Свой период',
    forWeek: 'за неделю',
    forMonth: 'за месяц',
    projectsEmpty: 'Проекты появятся после завершенных сессий.',
    history: 'История',
    viewAll: 'Все',
    viewAllHistory: 'Вся история',
    details: 'Детали',
    sessionDetails: 'Детали сессии',
    editReview: 'Редактировать итог',
    deleteSession: 'Удалить сессию',
    deleteTitle: 'Удалить сессию?',
    deleteBody: 'Этот блок пропадет из аналитики и истории.',
    deleteAction: 'Удалить',
    noReflection: 'Итог пока не заполнен.',
    avgDay: 'Сред/день',
    total: 'Всего',
    mostFocused: 'Лучший слот',
    vsWeekAverage: 'к предыдущим 4 неделям',
    vsMonthAverage: 'к предыдущим 4 месяцам',
    morning: 'Утро',
    afternoon: 'День',
    evening: 'Вечер',
    night: 'Ночь',
    historyEmpty: 'Завершенные сессии появятся здесь.',
    historyDetails: 'История сессий',
    days: 'Дни',
    projects: 'Проекты',
    projectsThisWeek: 'Проекты за неделю',
    projectsThisMonth: 'Проекты за месяц',
    projectsInRange: 'Проекты за период',
    projectsOn: 'Проекты за',
    recentSessions: 'Последние сессии',
    sessionsOn: 'Сессии за',
    searchSessions: 'Поиск сессий',
    selectedDay: 'Выбранный день',
    allDays: 'Все дни',
    clearDay: 'Снять день',
    range: 'Период',
    from: 'С',
    to: 'По',
    applyRange: 'Применить',
    saveChanges: 'Сохранить изменения',
    startTime: 'Время начала',
    endTime: 'Время окончания',
    startDate: 'Дата начала',
    endDate: 'Дата окончания',
    avgFocusScore: 'средний фокус',
    noSessionsForDay: 'В этот день сессий нет.',
    startAt: 'Начало',
    date: 'Дата',
    time: 'Время',
    todayChip: 'Сегодня',
    yesterdayChip: 'Вчера',
    startEndPreview: 'Старт — финиш',
    durationMinutes: 'Длительность, минут',
    whatDid: 'Что сделал?',
    logIntentPlaceholder: 'Что делал?',
    defaultIntention: 'Сессия',
    startError: 'Не удалось начать сессию',
    saveError: 'Не удалось сохранить сессию',
    logError: 'Не удалось сохранить блок',
    progressLabel: 'Прогресс сессии',
    breakProgressLabel: 'Прогресс перерыва',
    breakRunning: 'идёт перерыв',
    breakReady: 'Перезагрузка перед следующим блоком',
    breakEnded: 'Перерыв завершён',
    breakRemaining: 'осталось перерыва',
    finishBreak: 'Завершить перерыв',
    skipBreak: 'Пропустить перерыв',
    finishBreakError: 'Не удалось завершить перерыв',
    planned: 'План',
    actual: 'Факт',
    allProjects: 'Все проекты',
    loadMore: 'Загрузить ещё',
    loadingMore: 'Загрузка…',
    invalidRange: 'Окончание должно быть позже начала, а сессия — не длиннее 240 минут.',
    invalidCustomRange: 'Выберите корректный период не длиннее 180 дней.',
    stateError: 'Не удалось загрузить активную фокус-сессию. Таймер может всё ещё идти.',
    retry: 'Повторить',
  },
} satisfies Record<AppLocale, Record<string, string>>;

function secondsLabel(seconds: number, locale: AppLocale): string {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  if (locale === 'en') {
    if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m`;
    return `${minutes}m`;
  }
  if (hours > 0) return `${hours}ч ${String(minutes).padStart(2, '0')}м`;
  return `${minutes}м`;
}

function shortDateLabel(date: string, locale: AppLocale): string {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US', {
    month: 'short',
    day: 'numeric',
  }).format(parsed);
}

function weekdayLabel(date: string, locale: AppLocale): string {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US', {
    weekday: 'short',
  }).format(parsed);
}

function daypartLabel(daypart: FocusSummaryResponse['most_focused_daypart'], copy: (typeof COPY)[AppLocale]): string {
  if (!daypart) return '—';
  return copy[daypart];
}

function deltaLabel(value: number | null): string {
  if (value === null) return '—';
  const arrow = value >= 0 ? '↑' : '↓';
  return `${arrow} ${Math.abs(value)}%`;
}

function insightWindowLabel(
  insight: FocusInsight,
  locale: AppLocale,
  timeDisplay: TimeDisplayOptions,
): string {
  const start = new Date(insight.window_start);
  const windowEnd = new Date(insight.window_end);
  if (Number.isNaN(start.getTime()) || Number.isNaN(windowEnd.getTime())) {
    return `${insight.window_start} — ${insight.window_end}`;
  }
  const end = windowEnd.getTime() > start.getTime()
    ? new Date(windowEnd.getTime() - 1)
    : windowEnd;
  const options: Intl.DateTimeFormatOptions = {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...(timeDisplay.timezone ? { timeZone: timeDisplay.timezone } : {}),
  };
  try {
    const formatter = new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US', options);
    return `${formatter.format(start)} — ${formatter.format(end)}`;
  } catch {
    const formatter = new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
    return `${formatter.format(start)} — ${formatter.format(end)}`;
  }
}

function evidenceLabel(key: string): string {
  const words = key
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim();
  return words ? `${words.charAt(0).toUpperCase()}${words.slice(1)}` : key;
}

function evidenceValue(value: unknown, locale: AppLocale): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'boolean') {
    if (locale === 'ru') return value ? 'Да' : 'Нет';
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => evidenceValue(item, locale))
      .filter((item): item is string => item !== null);
    return parts.length ? parts.slice(0, 6).join(', ') : null;
  }
  if (typeof value === 'object') {
    const parts = Object.entries(value)
      .map(([key, item]) => {
        const formatted = evidenceValue(item, locale);
        return formatted === null ? null : `${evidenceLabel(key)}: ${formatted}`;
      })
      .filter((item): item is string => item !== null);
    return parts.length ? parts.slice(0, 6).join(' · ') : null;
  }
  return null;
}

function insightEvidenceRows(insight: FocusInsight, locale: AppLocale) {
  return Object.entries(insight.evidence)
    .filter(([key]) => key !== 'supporting_session_ids')
    .map(([key, value]) => ({ label: evidenceLabel(key), value: evidenceValue(value, locale) }))
    .filter((row): row is { label: string; value: string } => row.value !== null)
    .slice(0, 8);
}

function insightSupportingSessionIds(insight: FocusInsight): string[] {
  const ids = insight.evidence.supporting_session_ids;
  if (!Array.isArray(ids)) return [];
  return [...new Set(ids.filter((id): id is string => typeof id === 'string' && id.length > 0))];
}

function confidenceLabel(value: number): string {
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(Math.max(0, Math.min(100, normalized)))}%`;
}

function timerLabel(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function clampMinutes(value: string | number): number {
  const parsed = typeof value === 'number' ? value : Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return DEFAULT_DURATION;
  return Math.min(240, Math.max(1, parsed));
}

function dateInputValue(date: Date, timezone?: string | null): string {
  return dateTimeInputParts(date, timezone).date;
}

function timeInputValue(date: Date, timezone?: string | null): string {
  return dateTimeInputParts(date, timezone).time;
}

function dayValue(offsetDays: number, timezone?: string | null): string {
  const today = dateInputValue(new Date(), timezone);
  const date = new Date(`${today}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

function sessionEndIso(session: FocusSession): string {
  return session.ended_at ?? session.target_end_at;
}

function sessionTimeRangeLabel(session: FocusSession, timeDisplay: TimeDisplayOptions): string {
  return `${formatTime(session.started_at, timeDisplay)}–${formatTime(sessionEndIso(session), timeDisplay)}`;
}

function plannedVsActualLabel(session: FocusSession, copy: (typeof COPY)[AppLocale]): string | null {
  if (session.actual_minutes == null) return null;
  const delta = session.planned_vs_actual_minutes ?? session.actual_minutes - session.planned_minutes;
  const deltaLabel = delta === 0 ? '' : ` (${delta > 0 ? '+' : ''}${delta})`;
  return `${copy.planned} ${session.planned_minutes} · ${copy.actual} ${session.actual_minutes}${deltaLabel}`;
}

function sessionMetaLabel(session: FocusSession, copy: (typeof COPY)[AppLocale], timeDisplay: TimeDisplayOptions): string {
  const parts = [sessionTimeRangeLabel(session, timeDisplay), session.project_name ?? copy.noProject];
  if (session.task?.title) parts.push(session.task.title);
  const comparison = plannedVsActualLabel(session, copy);
  if (comparison) parts.push(comparison);
  return parts.join(' · ');
}

function rangeDefaults(timezone?: string | null): { from_date: string; to_date: string } {
  return { from_date: dayValue(-29, timezone), to_date: dayValue(0, timezone) };
}

interface DateTimeRangeDraft {
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
}

function manualRangeDefaults(durationMinutes: number, timezone?: string | null): DateTimeRangeDraft {
  const end = new Date();
  const start = new Date(end.getTime() - durationMinutes * 60_000);
  const startParts = dateTimeInputParts(start, timezone);
  const endParts = dateTimeInputParts(end, timezone);
  return { startDate: startParts.date, startTime: startParts.time, endDate: endParts.date, endTime: endParts.time };
}

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export function getDialMetrics({ started, target, now }: { started: number; target: number; now: number }) {
  const total = Math.max(1, Math.round((target - started) / 1000));
  const elapsed = Math.max(0, Math.round((now - started) / 1000));
  const remaining = Math.max(0, total - elapsed);
  const overtime = Math.max(0, elapsed - total);
  const progress = Math.min(1, elapsed / total);
  return { total, elapsed, remaining, overtime, progress };
}

function activeTasks(items: Task[]): Task[] {
  return items
    .filter((task) => task.status === 'active' || task.status === 'inbox')
    .sort((a, b) => {
      const project = (a.project ?? '').localeCompare(b.project ?? '', 'ru');
      if (project !== 0) return project;
      return a.title.localeCompare(b.title, 'ru');
    });
}

function matchesTask(task: Task, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return `${task.title} ${task.project ?? ''} ${task.tags.join(' ')}`.toLowerCase().includes(q);
}

function groupTasks(tasks: Task[], copy: (typeof COPY)[AppLocale]): Array<{ project: string; tasks: Task[] }> {
  const groups = new Map<string, Task[]>();
  for (const task of tasks) {
    const project = task.project?.trim() || copy.noProject;
    groups.set(project, [...(groups.get(project) ?? []), task]);
  }
  return [...groups.entries()].map(([project, items]) => ({ project, tasks: items }));
}

interface TaskPickerSheetProps {
  open: boolean;
  onClose: () => void;
  tasks: Task[];
  selectedTaskId: string;
  locale: AppLocale;
  onSelect: (task: Task | null) => void;
}

function TaskPickerSheet({ open, onClose, tasks, selectedTaskId, locale, onSelect }: TaskPickerSheetProps) {
  const copy = COPY[locale];
  const [query, setQuery] = useState('');
  const visible = useMemo(() => tasks.filter((task) => matchesTask(task, query)), [query, tasks]);
  const grouped = useMemo(() => groupTasks(visible, copy), [copy, visible]);

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const choose = (task: Task | null) => {
    onSelect(task);
    onClose();
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.taskPicker}>
      <div className="space-y-3">
        <label className="sticky top-[74px] z-20 block bg-[var(--surface-strong)] pb-2">
          <FieldLabel>{copy.search}</FieldLabel>
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hint" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={copy.searchTasks}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] pl-9 pr-3 text-[15px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </div>
        </label>
        <div className="max-h-[68dvh] overflow-y-auto rounded-2xl border border-hairline">
          <button
            type="button"
            onClick={() => choose(null)}
            className={`flex w-full items-center justify-between px-4 py-3 text-left ${selectedTaskId === '' ? 'bg-[var(--accent-soft)]' : 'bg-transparent'}`}
          >
            <span>
              <span className="block text-[14.5px] font-medium text-ink">{copy.noTask}</span>
              <span className="block text-[12.5px] text-hint">{copy.onlyIntentProject}</span>
            </span>
            {selectedTaskId === '' && <Check size={16} className="text-accent-text" />}
          </button>
          {grouped.map((group) => (
            <div key={group.project} className="border-t border-hairline">
              <div className="sticky top-0 z-10 bg-[var(--surface-strong)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-hint">
                {group.project}
              </div>
              {group.tasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => choose(task)}
                  className={`flex w-full items-center justify-between border-t border-hairline px-4 py-3 text-left first:border-t-0 ${
                    selectedTaskId === task.id ? 'bg-[var(--accent-soft)]' : 'bg-transparent'
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[14.5px] font-medium text-ink">{task.title}</span>
                    <span className="block truncate text-[12.5px] text-hint">
                      {task.tags.length ? `${task.tags.join(', ')} · ` : ''}{task.status === 'active' ? copy.taskStatusActive : copy.taskStatusInbox}
                    </span>
                  </span>
                  {selectedTaskId === task.id && <Check size={16} className="shrink-0 text-accent-text" />}
                </button>
              ))}
            </div>
          ))}
          {visible.length === 0 && <p className="border-t border-hairline px-4 py-4 text-[13px] text-hint">{copy.nothingFound}</p>}
        </div>
      </div>
    </Sheet>
  );
}

interface ProjectPickerSheetProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  selectedProjectId: string | null;
  selectedProjectName: string;
  locale: AppLocale;
  onSelect: (project: { id: string | null; name: string }) => void;
}

function ProjectPickerSheet({ open, onClose, projects, selectedProjectId, selectedProjectName, locale, onSelect }: ProjectPickerSheetProps) {
  const copy = COPY[locale];
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((project) => project.name.toLowerCase().includes(q));
  }, [projects, query]);
  const custom = query.trim();
  const canUseCustom = custom.length > 0 && !projects.some((project) => project.name.toLowerCase() === custom.toLowerCase());

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const choose = (project: { id: string | null; name: string }) => {
    onSelect(project);
    onClose();
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.projectPicker}>
      <div className="space-y-3">
        <label className="sticky top-[74px] z-20 block bg-[var(--surface-strong)] pb-2">
          <FieldLabel>{copy.search}</FieldLabel>
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hint" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={copy.searchProjects}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] pl-9 pr-3 text-[15px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </div>
        </label>
        <div className="max-h-[50dvh] overflow-y-auto rounded-2xl border border-hairline">
          <button
            type="button"
            onClick={() => choose({ id: null, name: '' })}
            className={`flex w-full items-center justify-between px-4 py-3 text-left ${selectedProjectId === null && selectedProjectName.trim() === '' ? 'bg-[var(--accent-soft)]' : 'bg-transparent'}`}
          >
            <span className="text-[14.5px] font-medium text-ink">{copy.noProject}</span>
            {selectedProjectId === null && selectedProjectName.trim() === '' && <Check size={16} className="text-accent-text" />}
          </button>
          {visible.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => choose({ id: project.id, name: project.name })}
              className={`flex w-full items-center justify-between border-t border-hairline px-4 py-3 text-left ${
                selectedProjectId === project.id ? 'bg-[var(--accent-soft)]' : 'bg-transparent'
              }`}
            >
              <span className="text-[14.5px] font-medium text-ink">{project.name}</span>
              {selectedProjectId === project.id && <Check size={16} className="text-accent-text" />}
            </button>
          ))}
          {canUseCustom && (
            <button
              type="button"
              onClick={() => choose({ id: null, name: custom })}
              className="flex w-full items-center justify-between border-t border-hairline px-4 py-3 text-left"
            >
              <span>
                <span className="block text-[14.5px] font-medium text-ink">{custom}</span>
                <span className="block text-[12.5px] text-hint">{copy.customProject}</span>
              </span>
              <Plus size={16} className="text-accent-text" />
            </button>
          )}
          {visible.length === 0 && !canUseCustom && <p className="border-t border-hairline px-4 py-4 text-[13px] text-hint">{copy.nothingFound}</p>}
        </div>
      </div>
    </Sheet>
  );
}

function DurationControl({
  value,
  onChange,
  label,
  heading,
}: {
  value: number;
  onChange: (value: number) => void;
  label: string;
  heading: string;
}) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const update = (next: string) => {
    setDraft(next);
    if (next.trim() !== '') onChange(clampMinutes(next));
  };

  return (
    <div>
      <FieldLabel>{heading}</FieldLabel>
      <div className="flex flex-wrap items-center gap-2">
        {DURATIONS.map((item) => (
          <Chip key={item} label={`${item}`} active={value === item} onClick={() => onChange(item)} />
        ))}
        <label className="ml-auto min-w-[112px] flex-1">
          <span className="sr-only">{label}</span>
          <input
            aria-label={label}
            type="number"
            min={1}
            max={240}
            value={draft}
            onBlur={() => setDraft(String(clampMinutes(draft)))}
            onChange={(event) => update(event.target.value)}
            className="h-9 w-full rounded-full border border-hairline bg-[var(--surface-strong)] px-3 text-center text-[13px] font-medium text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          />
        </label>
      </div>
    </div>
  );
}

function FocusCycleControl({
  preset,
  focusMinutes,
  breakMinutes,
  locale,
  onChange,
}: {
  preset: FocusCyclePreset;
  focusMinutes: number;
  breakMinutes: number;
  locale: AppLocale;
  onChange: (value: { preset: FocusCyclePreset; focusMinutes: number; breakMinutes: number }) => void;
}) {
  const copy = COPY[locale];
  return (
    <fieldset>
      <legend className="mb-1.5 block text-[12.5px] font-medium text-hint">{copy.cycle}</legend>
      <div className="flex flex-wrap gap-2">
        {FOCUS_CYCLE_PRESETS.map((item) => (
          <Chip
            key={item.preset}
            label={item.preset}
            active={preset === item.preset}
            onClick={() => onChange(item)}
          />
        ))}
        <Chip
          label={copy.customCycle}
          active={preset === 'custom'}
          onClick={() => onChange({ preset: 'custom', focusMinutes, breakMinutes })}
        />
      </div>
      {preset === 'custom' && (
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label>
            <FieldLabel>{copy.focusMinutes}</FieldLabel>
            <input
              aria-label={copy.focusMinutes}
              type="number"
              min={1}
              max={240}
              value={focusMinutes}
              onChange={(event) => onChange({
                preset: 'custom',
                focusMinutes: clampMinutes(event.target.value),
                breakMinutes,
              })}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3 text-center text-[14px] font-medium text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </label>
          <label>
            <FieldLabel>{copy.breakMinutes}</FieldLabel>
            <input
              aria-label={copy.breakMinutes}
              type="number"
              min={0}
              max={60}
              value={breakMinutes}
              onChange={(event) => onChange({
                preset: 'custom',
                focusMinutes,
                breakMinutes: Math.max(0, Math.min(60, Number(event.target.value) || 0)),
              })}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3 text-center text-[14px] font-medium text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </label>
        </div>
      )}
    </fieldset>
  );
}

function StartSheet({
  open,
  onClose,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
  const tasksQuery = useFocusTasks();
  const projectsQuery = useProjects();
  const start = useStartFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [cycle, setCycle] = useState(DEFAULT_FOCUS_CYCLE);
  const [taskId, setTaskId] = useState('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState('');

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const projects = useMemo(
    () => (projectsQuery.data?.items ?? []).filter((project) => project.status === 'active').sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    [projectsQuery.data],
  );
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;

  const submit = () => {
    const text = intention.trim() || selectedTask?.title || projectName.trim() || copy.defaultIntention;
    if (start.isPending) return;
    prepareFocusAlarm();
    haptic('light');
    start.mutate(
      {
        task_id: taskId || null,
        project_id: projectId,
        project_name: projectName.trim() || null,
        intention: text,
        planned_minutes: cycle.focusMinutes,
        break_minutes: cycle.breakMinutes,
      },
      {
        onSuccess: () => {
          setIntention('');
          setTaskId('');
          setProjectId(null);
          setProjectName('');
          setCycle(DEFAULT_FOCUS_CYCLE);
          onClose();
        },
        onError: () => show(copy.startError, 'error'),
      },
    );
  };

  return (
    <>
      <Sheet open={open} onClose={onClose} title={copy.newSession}>
        <div className="space-y-4">
          <label>
            <FieldLabel>{copy.intention}</FieldLabel>
            <Input value={intention} onChange={setIntention} placeholder={copy.whatWork} />
          </label>
          <FocusCycleControl {...cycle} locale={locale} onChange={setCycle} />
          <div>
            <FieldLabel>{copy.task}</FieldLabel>
            <button
              type="button"
              onClick={() => setTaskPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{selectedTask ? selectedTask.title : copy.noTask}</span>
              <span className="text-[12px] text-hint">{copy.chooseTask}</span>
            </button>
          </div>
          <div>
            <FieldLabel>{copy.project}</FieldLabel>
            <button
              type="button"
              onClick={() => setProjectPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{projectName.trim() || copy.noProject}</span>
              <span className="text-[12px] text-hint">{copy.chooseProject}</span>
            </button>
          </div>
          <Button fullWidth busy={start.isPending} onClick={submit} icon={<Timer size={16} />}>
            {copy.startCta} {cycle.focusMinutes} {locale === 'en' ? 'min' : 'мин'}
          </Button>
        </div>
      </Sheet>
      <TaskPickerSheet
        open={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        tasks={tasks}
        selectedTaskId={taskId}
        locale={locale}
        onSelect={(task) => {
          setTaskId(task?.id ?? '');
          setProjectId(task?.project_id ?? null);
          setProjectName(task?.project ?? '');
        }}
      />
      <ProjectPickerSheet
        open={projectPickerOpen}
        onClose={() => setProjectPickerOpen(false)}
        projects={projects}
        selectedProjectId={projectId}
        selectedProjectName={projectName}
        locale={locale}
        onSelect={(project) => {
          setProjectId(project.id);
          setProjectName(project.name);
        }}
      />
    </>
  );
}

function ScorePicker({
  value,
  onChange,
  label,
  unscoredLabel,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  label: string;
  unscoredLabel: string;
}) {
  const groupName = useId();
  const options: Array<{ value: number | null; label: string }> = [
    { value: null, label: unscoredLabel },
    ...[1, 2, 3, 4, 5].map((item) => ({ value: item, label: `${label}: ${item}` })),
  ];

  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <div role="radiogroup" aria-label={label} className="grid grid-cols-6 gap-1.5">
        {options.map((option) => (
          <label key={option.value ?? 'unscored'} className="h-9 cursor-pointer">
            <input
              type="radio"
              name={groupName}
              value={option.value ?? ''}
              checked={value === option.value}
              aria-label={option.label}
              onChange={() => onChange(option.value)}
              className="peer sr-only"
            />
            <span
              className={`flex h-full items-center justify-center rounded-full border text-[13px] font-medium peer-focus-visible:shadow-[0_0_0_3px_var(--accent-soft)] ${
                value === option.value
                  ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-accent-text'
                  : 'border-hairline text-hint'
              }`}
            >
              {option.value ?? '—'}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

function OutcomePicker({
  value,
  onChange,
  label,
  labels,
}: {
  value: FocusReflectionOutcome | null;
  onChange: (value: FocusReflectionOutcome) => void;
  label: string;
  labels: Record<FocusReflectionOutcome, string>;
}) {
  const options: FocusReflectionOutcome[] = ['done', 'progress', 'blocked'];
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <div role="radiogroup" aria-label={label} className="grid grid-cols-3 gap-2">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            onClick={() => onChange(option)}
            className={`h-10 rounded-full border px-2 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_var(--accent-soft)] ${
              value === option
                ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-accent-text'
                : 'border-hairline bg-[var(--surface-strong)] text-hint'
            }`}
          >
            {labels[option]}
          </button>
        ))}
      </div>
    </div>
  );
}

function ReflectionSheet({
  session,
  open,
  onClose,
  locale,
}: {
  session: FocusSession | null;
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
  const update = useUpdateFocusSession();
  const { show } = useToast();
  const [outcome, setOutcome] = useState<FocusReflectionOutcome | null>(null);
  const [reflectionText, setReflectionText] = useState('');
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState<number | null>(null);

  useEffect(() => {
    if (open && session) {
      setOutcome(session.reflection.outcome);
      setReflectionText(session.reflection.raw_text ?? '');
      setAccomplished(session.reflection.accomplished_text ?? '');
      setDistraction(session.reflection.distraction_text ?? '');
      setNextStep(session.reflection.next_step_text ?? '');
      setScore(session.reflection.focus_score);
    }
  }, [open, session]);

  if (!session) return null;

  const submit = () => {
    update.mutate(
      {
        id: session.id,
        input: {
          reflection_outcome: outcome,
          reflection_text: reflectionText.trim() || null,
          accomplished_text: accomplished,
          distraction_text: distraction,
          next_step_text: nextStep,
          focus_score: score,
        },
      },
      {
        onSuccess: () => {
          haptic('success');
          onClose();
        },
        onError: () => show(copy.saveError, 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.reflectionTitle}>
      <div className="space-y-4">
        <div className="rounded-2xl bg-[var(--accent-soft)] px-4 py-3">
          <p className="text-[13px] font-medium text-ink">{session.project_name ?? copy.noProject}</p>
          <p className="mt-0.5 text-[12.5px] text-hint">{session.intention}</p>
        </div>
        <OutcomePicker
          value={outcome}
          onChange={setOutcome}
          label={copy.outcome}
          labels={{
            done: copy.outcomeDone,
            progress: copy.outcomeProgress,
            blocked: copy.outcomeBlocked,
          }}
        />
        <ScorePicker value={score} onChange={setScore} label={copy.score} unscoredLabel={copy.unscored} />
        <label>
          <FieldLabel>{copy.reflectionNote}</FieldLabel>
          <Textarea value={reflectionText} onChange={setReflectionText} rows={3} placeholder={copy.reflectionNotePlaceholder} />
        </label>
        <details className="rounded-2xl border border-hairline bg-[var(--surface)] px-4 py-3">
          <summary className="cursor-pointer text-[13px] font-medium text-ink">{copy.advancedReflection}</summary>
          <div className="mt-4 space-y-4">
            <label>
              <FieldLabel>{copy.doneQuestion}</FieldLabel>
              <Textarea value={accomplished} onChange={setAccomplished} rows={3} placeholder={copy.donePlaceholder} />
            </label>
            <label>
              <FieldLabel>{copy.blockersQuestion}</FieldLabel>
              <Textarea value={distraction} onChange={setDistraction} rows={2} placeholder={copy.blockersPlaceholder} />
            </label>
            <label>
              <FieldLabel>{copy.nextStep}</FieldLabel>
              <Textarea value={nextStep} onChange={setNextStep} rows={2} placeholder={copy.nextStepPlaceholder} />
            </label>
          </div>
        </details>
        <Button fullWidth busy={update.isPending} onClick={submit} icon={<Check size={16} />}>
          {copy.saveSession}
        </Button>
      </div>
    </Sheet>
  );
}

function EditSessionSheet({
  session,
  open,
  onClose,
  locale,
}: {
  session: FocusSession | null;
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const update = useUpdateFocusSession();
  const { show } = useToast();
  const [intention, setIntention] = useState('');
  const [startDate, setStartDate] = useState(() => dateInputValue(new Date(), timeDisplay.timezone));
  const [startTime, setStartTime] = useState(() => timeInputValue(new Date(), timeDisplay.timezone));
  const [endDate, setEndDate] = useState(() => dateInputValue(new Date(), timeDisplay.timezone));
  const [endTime, setEndTime] = useState(() => timeInputValue(new Date(), timeDisplay.timezone));
  const [outcome, setOutcome] = useState<FocusReflectionOutcome | null>(null);
  const [reflectionText, setReflectionText] = useState('');
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState<number | null>(null);

  useEffect(() => {
    if (open && session) {
      const started = new Date(session.started_at);
      const ended = new Date(sessionEndIso(session));
      setIntention(session.intention);
      setStartDate(dateInputValue(started, timeDisplay.timezone));
      setStartTime(timeInputValue(started, timeDisplay.timezone));
      setEndDate(dateInputValue(ended, timeDisplay.timezone));
      setEndTime(timeInputValue(ended, timeDisplay.timezone));
      setOutcome(session.reflection.outcome);
      setReflectionText(session.reflection.raw_text ?? '');
      setAccomplished(session.reflection.accomplished_text ?? '');
      setDistraction(session.reflection.distraction_text ?? '');
      setNextStep(session.reflection.next_step_text ?? '');
      setScore(session.reflection.focus_score);
    }
  }, [open, session, timeDisplay.timezone]);

  if (!session) return null;

  const range = localRangeToIso(startDate, startTime, endDate, endTime, timeDisplay.timezone);
  const preview = range.valid
    ? `${formatTime(range.started_at, timeDisplay)} — ${formatTime(range.ended_at, timeDisplay)} · ${secondsLabel(range.duration_minutes * 60, locale)}`
    : '—';

  const submit = () => {
    const nextRange = localRangeToIso(startDate, startTime, endDate, endTime, timeDisplay.timezone);
    if (!nextRange.valid) {
      show(copy.saveError, 'error');
      return;
    }
    update.mutate(
      {
        id: session.id,
        input: {
          intention: intention.trim() || copy.defaultIntention,
          started_at: nextRange.started_at,
          ended_at: nextRange.ended_at,
          reflection_outcome: outcome,
          reflection_text: reflectionText.trim() || null,
          accomplished_text: accomplished.trim() || null,
          distraction_text: distraction.trim() || null,
          next_step_text: nextStep.trim() || null,
          focus_score: score,
        },
      },
      {
        onSuccess: () => {
          haptic('success');
          onClose();
        },
        onError: () => show(copy.saveError, 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.editSession}>
      <div className="space-y-4">
        <div className="rounded-2xl bg-[var(--accent-soft)] px-4 py-3">
          <p className="text-[13px] font-medium text-ink">{session.project_name ?? copy.noProject}</p>
          <p className="mt-0.5 text-[12.5px] text-hint">{session.task?.title ?? session.intention}</p>
        </div>
        <label>
          <FieldLabel>{copy.intention}</FieldLabel>
          <Input value={intention} onChange={setIntention} placeholder={copy.whatWork} />
        </label>
        <div className="space-y-3">
          <div>
            <FieldLabel>{copy.startAt}</FieldLabel>
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_104px] gap-2">
              <input aria-label={copy.startDate} type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
              <input aria-label={copy.startTime} type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
            </div>
          </div>
          <div>
            <FieldLabel>{copy.finish}</FieldLabel>
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_104px] gap-2">
              <input aria-label={copy.endDate} type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
              <input aria-label={copy.endTime} type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
            </div>
          </div>
        </div>
        <p className="tnum rounded-xl border border-hairline bg-[var(--surface)] px-3 py-2 text-[12.5px] text-hint">
          {copy.startEndPreview}: <span className="text-ink">{preview}</span>
        </p>
        {!range.valid && <p role="alert" className="text-[12.5px] text-danger">{copy.invalidRange}</p>}
        <OutcomePicker
          value={outcome}
          onChange={setOutcome}
          label={copy.outcome}
          labels={{
            done: copy.outcomeDone,
            progress: copy.outcomeProgress,
            blocked: copy.outcomeBlocked,
          }}
        />
        <ScorePicker value={score} onChange={setScore} label={copy.score} unscoredLabel={copy.unscored} />
        <label>
          <FieldLabel>{copy.reflectionNote}</FieldLabel>
          <Textarea value={reflectionText} onChange={setReflectionText} rows={3} placeholder={copy.reflectionNotePlaceholder} />
        </label>
        <details className="rounded-2xl border border-hairline bg-[var(--surface)] px-4 py-3">
          <summary className="cursor-pointer text-[13px] font-medium text-ink">{copy.advancedReflection}</summary>
          <div className="mt-4 space-y-4">
            <label>
              <FieldLabel>{copy.doneQuestion}</FieldLabel>
              <Textarea value={accomplished} onChange={setAccomplished} rows={3} placeholder={copy.donePlaceholder} />
            </label>
            <label>
              <FieldLabel>{copy.blockersQuestion}</FieldLabel>
              <Textarea value={distraction} onChange={setDistraction} rows={2} placeholder={copy.blockersPlaceholder} />
            </label>
            <label>
              <FieldLabel>{copy.nextStep}</FieldLabel>
              <Textarea value={nextStep} onChange={setNextStep} rows={2} placeholder={copy.nextStepPlaceholder} />
            </label>
          </div>
        </details>
        <Button fullWidth busy={update.isPending} onClick={submit} icon={<Check size={16} />}>
          {copy.saveChanges}
        </Button>
      </div>
    </Sheet>
  );
}

function ManualLogSheet({
  open,
  onClose,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const tasksQuery = useFocusTasks();
  const projectsQuery = useProjects();
  const logFocus = useLogFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [taskId, setTaskId] = useState('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState('');
  const [outcome, setOutcome] = useState<FocusReflectionOutcome | null>(null);
  const [reflectionText, setReflectionText] = useState('');
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState<number | null>(null);
  const [rangeDraft, setRangeDraft] = useState<DateTimeRangeDraft>(() => manualRangeDefaults(DEFAULT_DURATION, timeDisplay.timezone));
  const wasOpenRef = useRef(false);

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const projects = useMemo(
    () => (projectsQuery.data?.items ?? []).filter((project) => project.status === 'active').sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    [projectsQuery.data],
  );
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;
  const range = localRangeToIso(
    rangeDraft.startDate,
    rangeDraft.startTime,
    rangeDraft.endDate,
    rangeDraft.endTime,
    timeDisplay.timezone,
  );
  const duration = range.valid ? range.duration_minutes : DEFAULT_DURATION;
  const preview = range.valid
    ? `${formatTime(range.started_at, timeDisplay)} — ${formatTime(range.ended_at, timeDisplay)} · ${secondsLabel(range.duration_minutes * 60, locale)}`
    : '—';

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setRangeDraft(manualRangeDefaults(DEFAULT_DURATION, timeDisplay.timezone));
    }
    wasOpenRef.current = open;
  }, [open, timeDisplay.timezone]);

  const setDuration = (nextDuration: number) => {
    const end = localPartsToDate(rangeDraft.endDate, rangeDraft.endTime, timeDisplay.timezone);
    if (Number.isNaN(end.getTime())) return;
    const start = new Date(end.getTime() - nextDuration * 60_000);
    const startParts = dateTimeInputParts(start, timeDisplay.timezone);
    setRangeDraft((current) => ({ ...current, startDate: startParts.date, startTime: startParts.time }));
  };

  const setEndDay = (endDate: string) => {
    const end = localPartsToDate(endDate, rangeDraft.endTime, timeDisplay.timezone);
    if (Number.isNaN(end.getTime())) return;
    const start = new Date(end.getTime() - duration * 60_000);
    const startParts = dateTimeInputParts(start, timeDisplay.timezone);
    setRangeDraft((current) => ({
      ...current,
      startDate: startParts.date,
      startTime: startParts.time,
      endDate,
    }));
  };

  const submit = () => {
    const nextRange = localRangeToIso(
      rangeDraft.startDate,
      rangeDraft.startTime,
      rangeDraft.endDate,
      rangeDraft.endTime,
      timeDisplay.timezone,
    );
    if (!nextRange.valid) {
      show(copy.invalidRange, 'error');
      return;
    }
    const text = intention.trim() || selectedTask?.title || projectName.trim() || copy.defaultIntention;
    if (logFocus.isPending) return;
    logFocus.mutate(
      {
        task_id: taskId || null,
        project_id: projectId,
        project_name: projectName.trim() || null,
        intention: text,
        logged_at: nextRange.started_at,
        duration_minutes: nextRange.duration_minutes,
        reflection_outcome: outcome,
        reflection_text: reflectionText.trim() || null,
        accomplished_text: accomplished.trim() || null,
        distraction_text: distraction.trim() || null,
        next_step_text: nextStep.trim() || null,
        focus_score: score,
      },
      {
        onSuccess: () => {
          setIntention('');
          setTaskId('');
          setProjectId(null);
          setProjectName('');
          setOutcome(null);
          setReflectionText('');
          setAccomplished('');
          setDistraction('');
          setNextStep('');
          setScore(null);
          setRangeDraft(manualRangeDefaults(DEFAULT_DURATION, timeDisplay.timezone));
          onClose();
        },
        onError: () => show(copy.logError, 'error'),
      },
    );
  };

  return (
    <>
      <Sheet open={open} onClose={onClose} title={copy.logSession}>
        <div className="space-y-4">
          <label>
            <FieldLabel>{copy.intention}</FieldLabel>
            <Input value={intention} onChange={setIntention} placeholder={copy.logIntentPlaceholder} />
          </label>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Chip label={copy.todayChip} active={rangeDraft.endDate === dayValue(0, timeDisplay.timezone)} onClick={() => setEndDay(dayValue(0, timeDisplay.timezone))} />
              <Chip label={copy.yesterdayChip} active={rangeDraft.endDate === dayValue(-1, timeDisplay.timezone)} onClick={() => setEndDay(dayValue(-1, timeDisplay.timezone))} />
            </div>
            <div>
              <FieldLabel>{copy.startAt}</FieldLabel>
              <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_104px] gap-2">
                <input aria-label={copy.startDate} type="date" value={rangeDraft.startDate} onChange={(event) => setRangeDraft((current) => ({ ...current, startDate: event.target.value }))} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
                <input aria-label={copy.startTime} type="time" value={rangeDraft.startTime} onChange={(event) => setRangeDraft((current) => ({ ...current, startTime: event.target.value }))} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
              </div>
            </div>
            <div>
              <FieldLabel>{copy.finish}</FieldLabel>
              <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_104px] gap-2">
                <input aria-label={copy.endDate} type="date" value={rangeDraft.endDate} onChange={(event) => setRangeDraft((current) => ({ ...current, endDate: event.target.value }))} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
                <input aria-label={copy.endTime} type="time" value={rangeDraft.endTime} onChange={(event) => setRangeDraft((current) => ({ ...current, endTime: event.target.value }))} className="h-11 min-w-0 rounded-xl border border-hairline bg-[var(--surface-strong)] px-2.5 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]" />
              </div>
            </div>
            <p className="tnum rounded-xl border border-hairline bg-[var(--surface)] px-3 py-2 text-[12.5px] text-hint">
              {copy.startEndPreview}: <span className="text-ink">{preview}</span>
            </p>
            {!range.valid && <p role="alert" className="text-[12.5px] text-danger">{copy.invalidRange}</p>}
          </div>
          <DurationControl value={duration} onChange={setDuration} label={copy.customDuration} heading={copy.duration} />
          <div>
            <FieldLabel>{copy.task}</FieldLabel>
            <button
              type="button"
              onClick={() => setTaskPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{selectedTask ? selectedTask.title : copy.noTask}</span>
              <span className="text-[12px] text-hint">{copy.chooseTask}</span>
            </button>
          </div>
          <div>
            <FieldLabel>{copy.project}</FieldLabel>
            <button
              type="button"
              onClick={() => setProjectPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{projectName.trim() || copy.noProject}</span>
              <span className="text-[12px] text-hint">{copy.chooseProject}</span>
            </button>
          </div>
          <OutcomePicker
            value={outcome}
            onChange={setOutcome}
            label={copy.outcome}
            labels={{
              done: copy.outcomeDone,
              progress: copy.outcomeProgress,
              blocked: copy.outcomeBlocked,
            }}
          />
          <ScorePicker value={score} onChange={setScore} label={copy.score} unscoredLabel={copy.unscored} />
          <label>
            <FieldLabel>{copy.reflectionNote}</FieldLabel>
            <Textarea value={reflectionText} onChange={setReflectionText} rows={3} placeholder={copy.reflectionNotePlaceholder} />
          </label>
          <details className="rounded-2xl border border-hairline bg-[var(--surface)] px-4 py-3">
            <summary className="cursor-pointer text-[13px] font-medium text-ink">{copy.advancedReflection}</summary>
            <div className="mt-4 space-y-4">
              <label>
                <FieldLabel>{copy.whatDid}</FieldLabel>
                <Textarea value={accomplished} onChange={setAccomplished} rows={3} placeholder={copy.donePlaceholder} />
              </label>
              <label>
                <FieldLabel>{copy.blockersQuestion}</FieldLabel>
                <Textarea value={distraction} onChange={setDistraction} rows={2} placeholder={copy.optionalProject} />
              </label>
              <label>
                <FieldLabel>{copy.nextStep}</FieldLabel>
                <Textarea value={nextStep} onChange={setNextStep} rows={2} placeholder={copy.optionalProject} />
              </label>
            </div>
          </details>
          <Button fullWidth busy={logFocus.isPending} onClick={submit} icon={<ClipboardPenLine size={16} />}>
            {copy.saveBlock}
          </Button>
        </div>
      </Sheet>
      <TaskPickerSheet
        open={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        tasks={tasks}
        selectedTaskId={taskId}
        locale={locale}
        onSelect={(task) => {
          setTaskId(task?.id ?? '');
          setProjectId(task?.project_id ?? null);
          setProjectName(task?.project ?? '');
        }}
      />
      <ProjectPickerSheet
        open={projectPickerOpen}
        onClose={() => setProjectPickerOpen(false)}
        projects={projects}
        selectedProjectId={projectId}
        selectedProjectName={projectName}
        locale={locale}
        onSelect={(project) => {
          setProjectId(project.id);
          setProjectName(project.name);
        }}
      />
    </>
  );
}

function BreathingOrbTimer({ session, now, locale }: { session: FocusSession; now: number; locale: AppLocale }) {
  const copy = COPY[locale];
  const started = new Date(session.started_at).getTime();
  const target = new Date(session.target_end_at).getTime();
  const { total, remaining, overtime } = getDialMetrics({ started, target, now });
  const over = overtime > 0;
  const orbStyle = over
    ? {
        background:
          'radial-gradient(circle at 50% 38%, rgba(114, 255, 190, 0.42) 0%, rgba(42, 142, 111, 0.26) 45%, rgba(8, 31, 28, 0.68) 72%, rgba(4, 12, 18, 0.22) 100%)',
        boxShadow:
          '0 0 46px rgba(76, 216, 158, 0.34), inset 0 0 56px rgba(147, 255, 208, 0.2), inset 0 -24px 54px rgba(31, 129, 105, 0.24)',
      }
    : {
        background:
          'radial-gradient(circle at 50% 38%, rgba(176, 203, 255, 0.72) 0%, rgba(78, 126, 238, 0.36) 44%, rgba(46, 99, 231, 0.58) 72%, rgba(46, 99, 231, 0.16) 100%)',
        boxShadow:
          '0 0 54px rgba(46, 99, 231, 0.30), inset 0 0 66px rgba(207, 224, 255, 0.34), inset 0 -28px 58px rgba(46, 99, 231, 0.26)',
      };

  return (
    <div
      aria-label={copy.progressLabel}
      className="orb-breathe relative mx-auto mt-3 flex aspect-square w-[min(62vw,250px)] max-w-[250px] items-center justify-center rounded-full"
      style={orbStyle}
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-full border border-white/10"
        style={{ boxShadow: 'inset 0 1px 18px rgba(255,255,255,0.18)' }}
      />
      <div aria-hidden className="absolute left-[18%] top-[14%] h-[30%] w-[44%] rounded-full bg-white/10 blur-2xl" />
      <div aria-hidden className="absolute inset-[-7%] rounded-full bg-[radial-gradient(circle,rgba(105,139,255,0.20),transparent_68%)] blur-xl" />
      <div className="text-center">
        <p className={`tnum text-[clamp(52px,15vw,78px)] font-semibold leading-none tracking-normal ${overtime > 0 ? 'text-success' : 'text-ink'}`}>
          {overtime > 0 ? `+${timerLabel(overtime)}` : timerLabel(remaining)}
        </p>
        <p className="mt-3 text-[14px] font-medium text-hint">
          {overtime > 0 ? copy.overtime : copy.remaining} <span className="text-hint">·</span>{' '}
          <span className={over ? 'text-success' : 'text-accent-text'}>{secondsLabel(total, locale)} {copy.plan}</span>
        </p>
      </div>
    </div>
  );
}

function ActiveSessionCard({ session, locale, onReviewSession }: { session: FocusSession; locale: AppLocale; onReviewSession: (session: FocusSession) => void }) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const { show } = useToast();
  const now = useNow();
  const abandon = useAbandonFocusSession();
  const finish = useFinishFocusSession();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const overtime = now >= new Date(session.target_end_at).getTime();
  const mutationPending = finish.isPending || abandon.isPending;

  const stopAndReview = () => {
    if (mutationPending) return;
    setActionError(null);
    finish.mutate(
      {
        id: session.id,
        input: {},
      },
      {
        onSuccess: (response) => {
          silenceFocusAlarm(session.id);
          haptic('success');
          onReviewSession(response.session);
        },
        onError: () => {
          setActionError(copy.finishError);
          show(copy.finishError, 'error');
        },
      },
    );
  };

  const cancelSession = () => {
    if (mutationPending) return;
    setActionError(null);
    abandon.mutate(session.id, {
      onSuccess: () => {
        silenceFocusAlarm(session.id);
        setConfirmCancel(false);
        haptic('light');
      },
      onError: () => {
        setActionError(copy.cancelError);
        show(copy.cancelError, 'error');
      },
    });
  };

  return (
    <Card className="relative overflow-hidden px-4 py-4 sm:px-5 sm:py-5">
        <div aria-hidden className="dawn-glow opacity-50" />
        <div className="relative">
          <div className="flex items-center justify-between gap-3">
            <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-hairline bg-[var(--accent-soft)] px-3 py-1 text-[12px] font-medium text-accent-text">
              <Folder size={14} />
              {session.project_name ?? copy.noProject}
            </span>
            <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${overtime ? 'text-success' : 'text-hint'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${overtime ? 'bg-success' : 'bg-accent'}`} />
              {overtime ? copy.overtime : copy.active}
            </span>
          </div>
          <BreathingOrbTimer session={session} now={now} locale={locale} />
          <p className={`mt-3 flex items-center justify-center gap-2 text-[14px] font-medium ${overtime ? 'text-success' : 'text-accent-text'}`}>
            <CircleDot size={17} />
            {overtime ? copy.timerEnded : copy.focusModeOn}
          </p>
          <p className="tnum mt-2 text-center text-[13px] text-hint">
            {formatTime(session.started_at, timeDisplay)} — {formatTime(session.target_end_at, timeDisplay)}
          </p>
          <div className="mt-4 border-t border-hairline pt-3">
            <div className="min-w-0 text-center">
              <h2 className="truncate text-[20px] font-semibold leading-tight tracking-normal text-ink">{session.intention}</h2>
              <p className="mt-1 truncate text-[13px] text-hint">
                {session.task?.title ?? session.project_name ?? copy.session}
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            <button
              type="button"
              onClick={stopAndReview}
              disabled={mutationPending}
              aria-label={overtime ? copy.stopTimerReview : copy.finishSession}
              className="relative inline-flex h-12 w-full min-w-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-full bg-accent px-5 text-[15.5px] font-semibold text-white shadow-[0_8px_22px_rgba(46,99,231,0.34)] transition-opacity disabled:opacity-55"
            >
              {finish.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={17} />}
              {overtime ? copy.stopTimerReview : copy.stopReview}
            </button>
            <div className={`grid gap-3 ${overtime ? 'grid-cols-2' : 'grid-cols-1'}`}>
              {overtime && (
                <Button variant="secondary" disabled={mutationPending} onClick={() => silenceFocusAlarm(session.id)}>
                  {copy.keepCounting}
                </Button>
              )}
              <Button variant="ghost" disabled={mutationPending} onClick={() => setConfirmCancel(true)} icon={<X size={16} />} className="min-w-0">
                {copy.cancel}
              </Button>
            </div>
          </div>
          {actionError && <p role="alert" className="mt-3 text-center text-[12.5px] text-danger">{actionError}</p>}
        </div>
        <Sheet open={confirmCancel} onClose={() => setConfirmCancel(false)} title={copy.cancelTitle}>
          <p className="text-[13.5px] leading-relaxed text-hint">{copy.cancelBody}</p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            <Button variant="ghost" disabled={mutationPending} onClick={() => setConfirmCancel(false)}>{copy.keepCounting}</Button>
            <Button variant="danger" busy={abandon.isPending} disabled={finish.isPending} onClick={cancelSession}>{copy.cancelAction}</Button>
          </div>
        </Sheet>
      </Card>
  );
}

function ActiveBreakCard({ session, locale }: { session: FocusSession; locale: AppLocale }) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const now = useNow();
  const finishBreak = useFinishFocusBreak();
  const { show } = useToast();
  const targetAt = new Date(session.cycle?.break_target_end_at ?? '').getTime();
  const startedAt = new Date(session.cycle?.break_started_at ?? '').getTime();
  const validRange = Number.isFinite(targetAt) && Number.isFinite(startedAt);
  const remaining = validRange ? Math.max(0, Math.round((targetAt - now) / 1000)) : 0;
  const ended = validRange && now >= targetAt;
  const totalSeconds = Math.max(1, (session.cycle?.break_minutes ?? 0) * 60);

  const completeBreak = () => {
    if (finishBreak.isPending) return;
    finishBreak.mutate(session.id, {
      onSuccess: () => {
        silenceFocusAlarm(session.id, 'break');
        haptic('success');
      },
      onError: () => show(copy.finishBreakError, 'error'),
    });
  };

  return (
    <Card className="relative overflow-hidden px-4 py-5 sm:px-5">
      <div
        aria-hidden
        className="absolute -right-24 -top-28 h-80 w-80 rounded-full bg-[radial-gradient(circle,var(--success-soft),transparent_68%)] blur-2xl"
      />
      <div className="relative">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-hairline bg-[var(--success-soft)] px-3 py-1 text-[12px] font-medium text-success">
            <Clock3 size={14} />
            {session.cycle?.preset ?? copy.customCycle}
          </span>
          <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-success">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            {ended ? copy.breakEnded : copy.breakRunning}
          </span>
        </div>
        <div
          aria-label={copy.breakProgressLabel}
          className="orb-breathe relative mx-auto mt-5 flex aspect-square w-[min(58vw,230px)] max-w-[230px] items-center justify-center rounded-full"
          style={{
            background:
              'radial-gradient(circle at 50% 36%, rgba(183, 255, 220, 0.66) 0%, rgba(52, 178, 127, 0.34) 46%, rgba(31, 157, 107, 0.54) 72%, rgba(31, 157, 107, 0.12) 100%)',
            boxShadow:
              '0 0 48px rgba(52, 178, 127, 0.27), inset 0 0 58px rgba(210, 255, 232, 0.28), inset 0 -26px 54px rgba(31, 157, 107, 0.2)',
          }}
        >
          <div aria-hidden className="absolute inset-0 rounded-full border border-white/10" />
          <div className="text-center">
            <p className="tnum text-[clamp(50px,14vw,72px)] font-semibold leading-none text-ink">
              {timerLabel(remaining)}
            </p>
            <p className="mt-3 text-[13px] font-medium text-hint">
              {ended ? copy.breakEnded : copy.breakRemaining} · {secondsLabel(totalSeconds, locale)}
            </p>
          </div>
        </div>
        <div className="mt-5 text-center">
          <h2 className="truncate text-[20px] font-semibold text-ink">{copy.breakReady}</h2>
          <p className="mt-1 truncate text-[13px] text-hint">{session.intention}</p>
          {validRange && (
            <p className="tnum mt-2 text-[12.5px] text-hint">
              {formatTime(session.cycle?.break_started_at ?? '', timeDisplay)} —{' '}
              {formatTime(session.cycle?.break_target_end_at ?? '', timeDisplay)}
            </p>
          )}
        </div>
        <Button
          fullWidth
          className="mt-5"
          busy={finishBreak.isPending}
          onClick={completeBreak}
          icon={<Check size={17} />}
        >
          {ended ? copy.finishBreak : copy.skipBreak}
        </Button>
      </div>
    </Card>
  );
}

function EmptyFocusCard({ onStart, onLog, locale }: { onStart: () => void; onLog: () => void; locale: AppLocale }) {
  const copy = COPY[locale];
  return (
    <Card className="relative overflow-hidden p-5">
      <div aria-hidden className="dawn-glow" />
      <div className="relative">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-soft)] text-accent-text">
          <Timer size={19} />
        </span>
        <h2 className="mt-4 text-[23px] font-semibold leading-tight text-ink">{copy.readyTitle}</h2>
        <p className="mt-2 text-[13.5px] leading-relaxed text-hint">
          {copy.readyBody}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={onStart}
            className="relative inline-flex h-11 select-none items-center justify-center gap-2 whitespace-nowrap rounded-full bg-accent px-5 text-[14.5px] font-medium text-[var(--accent-foreground)] shadow-[0_6px_18px_var(--accent-shadow)] transition-opacity"
          >
            <Plus size={16} />
            {copy.startSession}
          </button>
          <button
            type="button"
            onClick={onLog}
            className="relative inline-flex h-11 select-none items-center justify-center gap-2 whitespace-nowrap rounded-full bg-[var(--secondary-bg)] px-5 text-[14.5px] font-medium text-[var(--secondary-text)] transition-opacity"
          >
            <ClipboardPenLine size={16} />
            {copy.logSession}
          </button>
        </div>
      </div>
    </Card>
  );
}

function sessionDateKey(session: FocusSession): string {
  return session.local_date;
}

interface ChartActivity extends FocusDailyActivity {
  end_date?: string;
}

export function aggregateActivityForChart(items: FocusDailyActivity[]): ChartActivity[] {
  if (items.length <= 31) return items;
  const weeks: ChartActivity[] = [];
  for (let index = 0; index < items.length; index += 7) {
    const chunk = items.slice(index, index + 7);
    const scored = chunk.filter((item) => item.average_focus_score !== null && item.average_focus_score !== undefined);
    const scoredSessions = scored.reduce((sum, item) => sum + item.session_count, 0);
    weeks.push({
      date: chunk[0].date,
      end_date: chunk[chunk.length - 1]?.date,
      focus_seconds: chunk.reduce((sum, item) => sum + item.focus_seconds, 0),
      session_count: chunk.reduce((sum, item) => sum + item.session_count, 0),
      average_focus_score: scoredSessions > 0
        ? Math.round((scored.reduce((sum, item) => sum + (item.average_focus_score ?? 0) * item.session_count, 0) / scoredSessions) * 10) / 10
        : null,
    });
  }
  return weeks;
}

function niceChartMax(maxSeconds: number): number {
  if (maxSeconds <= 0) return 60 * 60;
  if (maxSeconds <= 60 * 60) return Math.ceil(maxSeconds / (15 * 60)) * 15 * 60;
  return Math.ceil(maxSeconds / (60 * 60)) * 60 * 60;
}

function ActivityBarChart({
  items,
  locale,
  selectedDate,
  onSelectDate,
  showSummary = true,
}: {
  items: FocusDailyActivity[];
  locale: AppLocale;
  selectedDate: string | null;
  onSelectDate?: (date: string) => void;
  showSummary?: boolean;
}) {
  const copy = COPY[locale];
  const chartItems = aggregateActivityForChart(items);
  const weekly = items.length > 31;
  const max = niceChartMax(Math.max(0, ...chartItems.map((item) => item.focus_seconds)));
  const isDense = chartItems.length > 14;
  const selected = selectedDate ? chartItems.find((item) => item.date === selectedDate) ?? null : null;
  const tickIndexes = new Set(
    isDense
      ? [0, Math.floor((chartItems.length - 1) / 4), Math.floor((chartItems.length - 1) / 2), Math.floor(((chartItems.length - 1) * 3) / 4), chartItems.length - 1]
          .filter((index) => index >= 0 && index < chartItems.length)
      : chartItems.map((_item, index) => index),
  );

  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-hairline p-3">
      <div className="grid min-w-0 grid-cols-[38px_minmax(0,1fr)] gap-2">
        <div className="flex h-28 flex-col justify-between py-1 text-right text-[10px] text-hint">
          <span>{secondsLabel(max, locale)}</span>
          <span>{secondsLabel(max / 2, locale)}</span>
          <span>0</span>
        </div>
        <div className="min-w-0 overflow-hidden">
          <div
            className={`grid h-28 min-w-0 items-end border-b border-hairline bg-[linear-gradient(to_bottom,transparent_0,transparent_49%,var(--hairline)_50%,transparent_51%)] ${isDense ? 'gap-[2px]' : 'gap-1.5'}`}
            style={{ gridTemplateColumns: `repeat(${Math.max(1, chartItems.length)}, minmax(0, 1fr))` }}
          >
            {chartItems.map((item) => {
              const active = selected?.date === item.date;
              const percent = item.focus_seconds > 0 ? Math.max(5, Math.round((item.focus_seconds / max) * 100)) : 0;
              return (
                <button
                  key={item.date}
                  type="button"
                  data-testid="focus-day-bar"
                  onClick={() => onSelectDate?.(item.date)}
                  onPointerUp={(event) => event.currentTarget.blur()}
                  disabled={weekly || !onSelectDate}
                  className="group flex h-full min-w-0 items-end justify-center rounded-t-xl px-px outline-none focus-visible:shadow-[0_0_0_3px_var(--accent-soft)] disabled:cursor-default"
                  aria-label={`${item.date}${item.end_date ? `–${item.end_date}` : ''}: ${secondsLabel(item.focus_seconds, locale)}`}
                  aria-pressed={active}
                >
                  <span
                    className={`block w-full max-w-[18px] rounded-t-full transition-all ${
                      active ? 'bg-accent shadow-[0_0_0_2px_var(--accent-border),0_0_18px_rgba(95,135,255,0.34)]' : item.focus_seconds > 0 ? 'bg-accent opacity-70' : 'bg-[var(--hairline)]'
                    }`}
                    style={{ height: `${percent}%` }}
                  />
                </button>
              );
            })}
          </div>
          <div
            className={`mt-1 grid min-w-0 ${isDense ? 'gap-[2px]' : 'gap-1.5'}`}
            style={{ gridTemplateColumns: `repeat(${Math.max(1, chartItems.length)}, minmax(0, 1fr))` }}
          >
            {chartItems.map((item, index) => (
              <span
                key={item.date}
                className={`tnum whitespace-nowrap text-[10px] ${index === 0 ? 'justify-self-start' : index === chartItems.length - 1 ? 'justify-self-end' : 'justify-self-center'} ${tickIndexes.has(index) ? 'text-hint' : 'text-transparent'}`}
              >
                {weekly ? shortDateLabel(item.date, locale) : isDense ? new Date(`${item.date}T00:00:00`).getDate() : weekdayLabel(item.date, locale).slice(0, 2)}
              </span>
            ))}
          </div>
        </div>
      </div>
      {showSummary && selected && (
        <div className="mt-3 grid grid-cols-4 gap-2 rounded-xl bg-[var(--surface)] px-3 py-2 text-[12px]">
          <div>
            <p className="text-hint">{copy.selectedDay}</p>
            <p className="tnum mt-0.5 font-medium text-ink">{shortDateLabel(selected.date, locale)}</p>
          </div>
          <div>
            <p className="text-hint">{copy.total}</p>
            <p className="tnum mt-0.5 font-medium text-ink">{secondsLabel(selected.focus_seconds, locale)}</p>
          </div>
          <div>
            <p className="text-hint">{copy.sessions}</p>
            <p className="tnum mt-0.5 font-medium text-ink">{selected.session_count} {copy.countSessions}</p>
          </div>
          <div>
            <p className="text-hint">{copy.score}</p>
            <p className="tnum mt-0.5 font-medium text-ink">{selected.average_focus_score ?? '—'}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function HistoryDetailsSheet({
  open,
  onClose,
  locale,
  period,
  onPeriodChange,
  customRange,
  onCustomRangeChange,
  summary,
  onSelectSession,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
  period: 'week' | 'month' | 'custom';
  onPeriodChange: (period: 'week' | 'month' | 'custom') => void;
  customRange: { from_date: string; to_date: string };
  onCustomRangeChange: (range: { from_date: string; to_date: string }) => void;
  summary: FocusSummaryResponse | undefined;
  onSelectSession: (sessionId: string) => void;
}) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [projectId, setProjectId] = useState('');
  const [draftFrom, setDraftFrom] = useState(customRange.from_date);
  const [draftTo, setDraftTo] = useState(customRange.to_date);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const wasOpenRef = useRef(false);
  const filteredSummaryQuery = useFocusSummary(period, {
    ...(period === 'custom' ? customRange : {}),
    q: query,
    project_id: projectId,
    enabled: open,
  });
  const selectedDaySummaryQuery = useFocusSummary('custom', {
    from_date: selectedDate ?? undefined,
    to_date: selectedDate ?? undefined,
    q: query,
    project_id: projectId,
    enabled: open && selectedDate !== null,
  });
  const sessionsQuery = useInfiniteFocusSessions(selectedDate ? 'custom' : period, {
    ...(selectedDate
      ? { from_date: selectedDate, to_date: selectedDate }
      : period === 'custom'
        ? customRange
        : {}),
    q: query,
    project_id: projectId,
    enabled: open,
  });
  const daily = filteredSummaryQuery.data?.daily_activity ?? [];
  const sessions = sessionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const groupedSessions = sessions.reduce<Array<{ date: string; items: FocusSession[] }>>((groups, item) => {
    const date = sessionDateKey(item);
    const group = groups.find((entry) => entry.date === date);
    if (group) group.items.push(item);
    else groups.push({ date, items: [item] });
    return groups;
  }, []);
  const scopedSummary = selectedDate ? selectedDaySummaryQuery.data : filteredSummaryQuery.data;
  const scopedProjectBreakdown = scopedSummary?.project_breakdown ?? [];
  const maxProjectSeconds = Math.max(1, ...scopedProjectBreakdown.map((item) => item.focus_seconds));
  const projectTitle = selectedDate
    ? `${copy.projectsOn} ${shortDateLabel(selectedDate, locale)}`
    : period === 'month'
      ? copy.projectsThisMonth
      : period === 'custom'
        ? copy.projectsInRange
        : copy.projectsThisWeek;
  const sessionsTitle = selectedDate ? `${copy.sessionsOn} ${shortDateLabel(selectedDate, locale)}` : copy.sessions;

  useLayoutEffect(() => {
    if (open && !wasOpenRef.current) {
      setSelectedDate(null);
      setQuery('');
      setProjectId('');
      setRangeError(null);
      setDraftFrom(customRange.from_date);
      setDraftTo(customRange.to_date);
    }
    wasOpenRef.current = open;
  }, [customRange.from_date, customRange.to_date, open]);

  useEffect(() => {
    if (!open) return;
    setSelectedDate(null);
    setRangeError(null);
    setDraftFrom(customRange.from_date);
    setDraftTo(customRange.to_date);
  }, [customRange.from_date, customRange.to_date, open, timeDisplay.timezone]);

  const setPeriod = (next: 'week' | 'month' | 'custom') => {
    onPeriodChange(next);
    setSelectedDate(null);
    setRangeError(null);
    if (next === 'custom') onCustomRangeChange(customRange);
  };

  const applyRange = () => {
    const from = Date.parse(`${draftFrom}T12:00:00Z`);
    const to = Date.parse(`${draftTo}T12:00:00Z`);
    const spanDays = Math.round((to - from) / 86_400_000) + 1;
    if (!Number.isFinite(from) || !Number.isFinite(to) || spanDays < 1 || spanDays > 180) {
      setRangeError(copy.invalidCustomRange);
      return;
    }
    setRangeError(null);
    onPeriodChange('custom');
    onCustomRangeChange({ from_date: draftFrom, to_date: draftTo });
    setSelectedDate(null);
  };

  const toggleDate = (date: string) => {
    setSelectedDate((current) => (current === date ? null : date));
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.historyDetails} height="stable">
      <div className="space-y-5">
        <div className="flex gap-1.5">
          <Chip label={copy.week} active={period === 'week'} onClick={() => setPeriod('week')} />
          <Chip label={copy.month} active={period === 'month'} onClick={() => setPeriod('month')} />
          <Chip label={copy.custom} active={period === 'custom'} onClick={() => setPeriod('custom')} />
        </div>
        {period === 'custom' && (
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] p-3">
            <FieldLabel>{copy.range}</FieldLabel>
            <div className="grid grid-cols-2 gap-2">
              <label>
                <span className="sr-only">{copy.from}</span>
                <input
                  aria-label={copy.from}
                  type="date"
                  value={draftFrom}
                  onChange={(event) => {
                    setDraftFrom(event.target.value);
                    setRangeError(null);
                  }}
                  className="h-10 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
                />
              </label>
              <label>
                <span className="sr-only">{copy.to}</span>
                <input
                  aria-label={copy.to}
                  type="date"
                  value={draftTo}
                  onChange={(event) => {
                    setDraftTo(event.target.value);
                    setRangeError(null);
                  }}
                  className="h-10 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={applyRange}
              className="mt-2 h-10 w-full rounded-full bg-[var(--accent-soft)] text-[13px] font-medium text-accent-text"
            >
              {copy.applyRange}
            </button>
            {rangeError && <p role="alert" className="mt-2 text-[12.5px] text-danger">{rangeError}</p>}
          </div>
        )}
        <label className="block">
          <FieldLabel>{copy.search}</FieldLabel>
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hint" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={copy.searchSessions}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] pl-9 pr-3 text-[15px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </div>
        </label>
        <label className="block">
          <FieldLabel>{copy.project}</FieldLabel>
          <select
            aria-label={copy.project}
            value={projectId}
            onChange={(event) => {
              setProjectId(event.target.value);
              setSelectedDate(null);
            }}
            className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3 text-[14px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          >
            <option value="">{copy.allProjects}</option>
            {(summary?.project_breakdown ?? []).filter((project) => project.project_id !== null).map((project) => (
              <option key={project.project_id} value={project.project_id ?? ''}>{project.project_name ?? copy.noProject}</option>
            ))}
          </select>
        </label>
        <section>
          <h3 className="mb-2 text-[13px] font-semibold text-ink">{sessionsTitle}</h3>
          <div className="max-h-[42dvh] overflow-y-auto rounded-2xl border border-hairline">
            {groupedSessions.length > 0 ? (
              groupedSessions.map((group) => (
                <div key={group.date} className="border-b border-hairline last:border-b-0">
                  <div className="bg-[var(--surface)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-hint">
                    {shortDateLabel(group.date, locale)}
                  </div>
                  {group.items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      data-testid="focus-history-session-row"
                      onClick={() => onSelectSession(item.id)}
                      className="block w-full border-t border-hairline px-4 py-3 text-left first:border-t-0"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                          <p className="mt-0.5 truncate text-[12.5px] text-hint">{sessionMetaLabel(item, copy, timeDisplay)}</p>
                        </div>
                        <span className="tnum shrink-0 text-[13px] font-medium text-ink">{secondsLabel(item.duration_seconds ?? 0, locale)}</span>
                      </div>
                      {(item.reflection.accomplished_text || item.reflection.next_step_text) && (
                        <p className="mt-2 max-h-10 overflow-hidden text-[12.5px] leading-relaxed text-hint">
                          {item.reflection.accomplished_text ?? item.reflection.next_step_text}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              ))
            ) : (
              <p className="px-4 py-4 text-[13px] text-hint">{sessionsQuery.isPending ? copy.loadingMore : copy.noSessionsForDay}</p>
            )}
            {sessionsQuery.hasNextPage && (
              <button
                type="button"
                onClick={() => void sessionsQuery.fetchNextPage()}
                disabled={sessionsQuery.isFetchingNextPage}
                className="h-11 w-full border-t border-hairline text-[13px] font-medium text-accent-text disabled:opacity-60"
              >
                {sessionsQuery.isFetchingNextPage ? copy.loadingMore : copy.loadMore}
              </button>
            )}
          </div>
          {sessionsQuery.isError && <p role="alert" className="mt-2 text-[12.5px] text-danger">{copy.saveError}</p>}
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-ink">{copy.days}</h3>
            <button
              type="button"
              onClick={() => setSelectedDate(null)}
              className="tnum rounded-full px-2 py-1 text-[12px] text-hint"
            >
              {selectedDate ? copy.clearDay : copy.allDays}
            </button>
          </div>
          <ActivityBarChart items={daily} locale={locale} selectedDate={selectedDate} onSelectDate={toggleDate} showSummary={false} />
          {selectedDate && (
            <div className="mt-2 grid grid-cols-4 gap-2 rounded-xl bg-[var(--surface)] px-3 py-2 text-[12px]">
              <div>
                <p className="text-hint">{copy.selectedDay}</p>
                <p className="tnum mt-0.5 font-medium text-ink">{shortDateLabel(selectedDate, locale)}</p>
              </div>
              <div>
                <p className="text-hint">{copy.total}</p>
                <p className="tnum mt-0.5 font-medium text-ink">{secondsLabel(scopedSummary?.total_focus_seconds ?? 0, locale)}</p>
              </div>
              <div>
                <p className="text-hint">{copy.sessions}</p>
                <p className="tnum mt-0.5 font-medium text-ink">{scopedSummary?.total_sessions ?? 0} {copy.countSessions}</p>
              </div>
              <div>
                <p className="text-hint">{copy.score}</p>
                <p className="tnum mt-0.5 font-medium text-ink">{scopedSummary?.average_focus_score ?? '—'}</p>
              </div>
            </div>
          )}
        </section>

        <section>
          <h3 className="mb-2 text-[13px] font-semibold text-ink">{projectTitle}</h3>
          <div className="space-y-2.5">
            {scopedProjectBreakdown.map((item) => (
              <div key={item.project_id ?? item.project_name ?? copy.noProject}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[12.5px]">
                  <span className="truncate font-medium text-ink">{item.project_name ?? copy.noProject}</span>
                  <span className="tnum shrink-0 text-hint">{secondsLabel(item.focus_seconds, locale)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[var(--hairline)]">
                  <div
                    className="h-full rounded-full bg-[var(--accent)]"
                    style={{ width: `${Math.max(6, Math.round((item.focus_seconds / maxProjectSeconds) * 100))}%` }}
                  />
                </div>
              </div>
            ))}
            {!scopedProjectBreakdown.length && (
              <p className="text-[13px] text-hint">{copy.projectsEmpty}</p>
            )}
          </div>
        </section>
      </div>
    </Sheet>
  );
}

function KpiDelta({ value }: { value: number | null }) {
  const positive = (value ?? 0) >= 0;
  if (value === null) return <span className="text-hint">—</span>;
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-1 text-[12px] font-medium ${positive ? 'text-success' : 'text-danger'}`}>
      <Icon size={13} />
      {deltaLabel(value)}
    </span>
  );
}

function InsightRow({
  insight,
  locale,
  timeDisplay,
  onOpenSession,
}: {
  insight: FocusInsight;
  locale: AppLocale;
  timeDisplay: TimeDisplayOptions;
  onOpenSession: (sessionId: string) => void;
}) {
  const copy = COPY[locale];
  const { show } = useToast();
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const tryInsight = useTryFocusInsight();
  const dismissInsight = useDismissFocusInsight();
  const evidenceRows = insightEvidenceRows(insight, locale);
  const supportingSessionIds = insightSupportingSessionIds(insight);
  const isTrying = tryInsight.isPending && tryInsight.variables === insight.id;
  const isDismissing = dismissInsight.isPending && dismissInsight.variables === insight.id;
  const confirmed = insight.status === 'confirmed';

  return (
    <article data-testid="focus-insight" className="px-4 py-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
          <FlaskConical size={17} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-accent-text">
              {confirmed ? copy.insightExperiment : copy.insightObserved}
            </span>
            {confirmed && (
              <span className="rounded-full bg-[var(--success-soft)] px-2 py-0.5 text-[11px] font-medium text-success">
                {copy.insightTrying}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[14.5px] font-medium leading-snug text-ink">{insight.statement}</p>
        </div>
      </div>

      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => setExpanded((current) => !current)}
        className="mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-full text-[12.5px] font-medium text-accent-text"
      >
        {copy.insightWhy}
        <ChevronDown
          size={15}
          aria-hidden
          className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {expanded && (
        <div
          id={detailsId}
          role="region"
          aria-label={copy.insightEvidence}
          className="rounded-2xl bg-[var(--surface-strong)] px-3.5 py-3"
        >
          <dl className="divide-y divide-hairline text-[12.5px]">
            <div className="flex items-start justify-between gap-4 py-1.5 first:pt-0">
              <dt className="text-hint">{copy.insightWindow}</dt>
              <dd className="tnum text-right text-ink">{insightWindowLabel(insight, locale, timeDisplay)}</dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-1.5">
              <dt className="text-hint">{copy.insightSupport}</dt>
              <dd className="tnum text-right text-ink">{insight.support_count}</dd>
            </div>
            <div className="flex items-start justify-between gap-4 py-1.5">
              <dt className="text-hint">{copy.insightConfidence}</dt>
              <dd className="tnum text-right text-ink">{confidenceLabel(insight.confidence)}</dd>
            </div>
            {evidenceRows.map((row) => (
              <div key={row.label} className="flex items-start justify-between gap-4 py-1.5">
                <dt className="text-hint">{row.label}</dt>
                <dd className="max-w-[62%] break-words text-right text-ink">{row.value}</dd>
              </div>
            ))}
          </dl>
          {supportingSessionIds.length > 0 && (
            <div className="mt-3 border-t border-hairline pt-3">
              <p className="text-[11.5px] font-medium text-hint">{copy.insightSources}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {supportingSessionIds.map((sessionId, index) => (
                  <button
                    key={sessionId}
                    type="button"
                    onClick={() => onOpenSession(sessionId)}
                    className="inline-flex min-h-9 items-center gap-1 rounded-full border border-hairline bg-[var(--surface)] px-3 text-[12px] font-medium text-accent-text"
                  >
                    {copy.insightSource} {index + 1}
                    <ChevronRight size={14} aria-hidden />
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="mt-2 text-[11.5px] leading-relaxed text-hint">{copy.insightCorrelation}</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!confirmed && (
          <Button
            size="sm"
            variant="secondary"
            busy={isTrying}
            disabled={dismissInsight.isPending}
            onClick={() => {
              tryInsight.mutate(insight.id, {
                onSuccess: () => {
                  haptic('success');
                  show(copy.insightTried, 'success');
                },
                onError: () => show(copy.insightTryError, 'error'),
              });
            }}
          >
            {copy.insightTry}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          busy={isDismissing}
          disabled={tryInsight.isPending}
          onClick={() => {
            dismissInsight.mutate(insight.id, {
              onSuccess: () => {
                haptic('light');
                show(copy.insightDismissed, 'info');
              },
              onError: () => show(copy.insightDismissError, 'error'),
            });
          }}
        >
          {copy.insightDismiss}
        </Button>
      </div>
      {!confirmed && (
        <p className="mt-2.5 text-[11.5px] leading-relaxed text-hint">{copy.insightSafety}</p>
      )}
    </article>
  );
}

function InsightsSection({
  locale,
  timeDisplay,
  onOpenSession,
}: {
  locale: AppLocale;
  timeDisplay: TimeDisplayOptions;
  onOpenSession: (sessionId: string) => void;
}) {
  const copy = COPY[locale];
  const insights = useFocusInsights(3);
  const items = (insights.data?.items ?? [])
    .filter((item) => item.status === 'proposed' || item.status === 'confirmed')
    .slice(0, 3);

  if (insights.isSuccess && items.length === 0) return null;

  return (
    <Rise>
      <section aria-label={copy.insights}>
        <SectionHeader title={copy.insights} />
        <Card className="divide-y divide-hairline overflow-hidden !p-0" strong>
          {insights.isPending ? (
            <div aria-label={copy.insights} className="px-4 py-4">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="mt-2.5 h-4 w-4/5" />
              <Skeleton className="mt-2 h-4 w-3/5" />
            </div>
          ) : insights.isError ? (
            <div role="alert" className="flex items-center justify-between gap-3 px-4 py-4">
              <p className="text-[13px] text-hint">{copy.insightLoadError}</p>
              <Button size="sm" variant="ghost" onClick={() => void insights.refetch()}>
                {copy.retry}
              </Button>
            </div>
          ) : (
            items.map((insight) => (
              <InsightRow
                key={insight.id}
                insight={insight}
                locale={locale}
                timeDisplay={timeDisplay}
                onOpenSession={onOpenSession}
              />
            ))
          )}
        </Card>
      </section>
    </Rise>
  );
}

function AnalyticsKpis({ summary, locale, period }: { summary: FocusSummaryResponse | undefined; locale: AppLocale; period: MainPeriod }) {
  const copy = COPY[locale];
  return (
    <div className="grid min-w-0 grid-cols-2 gap-2 min-[390px]:grid-cols-3">
      <div className="min-w-0 rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3">
        <p className="text-[11px] font-medium text-hint">{copy.avgDay}</p>
        <p className="tnum mt-1 truncate text-[clamp(15px,4.5vw,18px)] font-semibold text-ink">{secondsLabel(summary?.average_daily_focus_seconds ?? 0, locale)}</p>
        <KpiDelta value={summary?.average_daily_focus_delta_percent ?? null} />
      </div>
      <div className="min-w-0 rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3">
        <p className="text-[11px] font-medium text-hint">{copy.total}</p>
        <p className="tnum mt-1 truncate text-[clamp(15px,4.5vw,18px)] font-semibold text-ink">{secondsLabel(summary?.total_focus_seconds ?? 0, locale)}</p>
        <KpiDelta value={summary?.total_focus_delta_percent ?? null} />
      </div>
      <div className="col-span-2 min-w-0 rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3 min-[390px]:col-span-1">
        <p className="text-[11px] font-medium text-hint">{copy.mostFocused}</p>
        <p className="mt-1 truncate text-[18px] font-semibold text-ink">{daypartLabel(summary?.most_focused_daypart ?? null, copy)}</p>
        <p className="truncate text-[11px] text-hint">{period === 'month' ? copy.vsMonthAverage : copy.vsWeekAverage}</p>
      </div>
    </div>
  );
}

function SessionDetailsSheet({
  open,
  onClose,
  onBack,
  onDeleted,
  session,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  onBack?: () => void;
  onDeleted?: () => void;
  session: FocusSession | null;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
  const timeDisplay = useTimeDisplay();
  const { show } = useToast();
  const [editOpen, setEditOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteFocus = useDeleteFocusSession();
  if (!session) return null;
  const reflection = session.reflection;
  const closeAfterDelete = () => {
    setConfirmDelete(false);
    onDeleted?.();
    onClose();
  };
  return (
    <>
      <Sheet
        open={open}
        onClose={onClose}
        title={copy.sessionDetails}
        headerStart={onBack ? (
          <button
            type="button"
            onClick={onBack}
            className="-ml-2 inline-flex h-9 items-center gap-1 rounded-full px-2 text-[13px] font-medium text-accent-text"
          >
            <ChevronLeft size={17} />
            {copy.history}
          </button>
        ) : undefined}
        headerActions={(
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            aria-label={copy.deleteSession}
            className="flex h-10 w-10 items-center justify-center rounded-full text-danger"
          >
            <Trash2 size={17} />
          </button>
        )}
      >
        <div className="space-y-4">
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] p-4">
            <p className="text-[19px] font-semibold text-ink">{session.intention}</p>
            <p className="mt-1 text-[13px] text-hint">
              {session.project_name ?? copy.noProject}{session.task ? ` · ${session.task.title}` : ''}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 text-[13px]">
              <div className="rounded-xl bg-[var(--surface-strong)] px-3 py-2">
                <p className="text-hint">{copy.startEndPreview}</p>
                <p className="tnum mt-0.5 text-ink">{sessionTimeRangeLabel(session, timeDisplay)}</p>
              </div>
              <div className="rounded-xl bg-[var(--surface-strong)] px-3 py-2">
                <p className="text-hint">{copy.duration}</p>
                <p className="tnum mt-0.5 text-ink">{secondsLabel(session.duration_seconds ?? 0, locale)}</p>
              </div>
            </div>
            {plannedVsActualLabel(session, copy) && (
              <p className="tnum mt-3 rounded-xl bg-[var(--accent-soft)] px-3 py-2 text-[12.5px] font-medium text-accent-text">
                {plannedVsActualLabel(session, copy)}
              </p>
            )}
          </div>
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[14px] font-semibold text-ink">{copy.reflectionTitle}</h3>
              <div className="flex items-center gap-2">
                {reflection.outcome && (
                  <span className="rounded-full bg-[var(--accent-soft)] px-2 py-1 text-[11.5px] font-medium text-accent-text">
                    {{
                      done: copy.outcomeDone,
                      progress: copy.outcomeProgress,
                      blocked: copy.outcomeBlocked,
                    }[reflection.outcome]}
                  </span>
                )}
                <span className="tnum text-[13px] text-hint">{reflection.focus_score ? `${reflection.focus_score}/5` : '—'}</span>
              </div>
            </div>
            {reflection.raw_text || reflection.accomplished_text || reflection.distraction_text || reflection.next_step_text ? (
              <div className="space-y-3 text-[13px] leading-relaxed">
                {reflection.raw_text && <p className="text-hint">{reflection.raw_text}</p>}
                {reflection.accomplished_text && <p><span className="font-medium text-ink">{copy.doneQuestion}</span><br /><span className="text-hint">{reflection.accomplished_text}</span></p>}
                {reflection.distraction_text && <p><span className="font-medium text-ink">{copy.blockersQuestion}</span><br /><span className="text-hint">{reflection.distraction_text}</span></p>}
                {reflection.next_step_text && <p><span className="font-medium text-ink">{copy.nextStep}</span><br /><span className="text-hint">{reflection.next_step_text}</span></p>}
              </div>
            ) : (
              <p className="text-[13px] text-hint">{copy.noReflection}</p>
            )}
          </div>
          <Button fullWidth onClick={() => setEditOpen(true)} icon={<Pencil size={16} />}>
            {copy.editSession}
          </Button>
        </div>
      </Sheet>
      <EditSessionSheet session={session} open={editOpen} onClose={() => setEditOpen(false)} locale={locale} />
      <Sheet open={confirmDelete} onClose={() => setConfirmDelete(false)} title={copy.deleteTitle}>
        <p className="text-[13.5px] leading-relaxed text-hint">{copy.deleteBody}</p>
        <div className="mt-4 rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-2">
          <p className="truncate text-[13.5px] font-medium text-ink">{session.intention}</p>
          <p className="tnum mt-0.5 text-[12px] text-hint">{shortDateLabel(sessionDateKey(session), locale)} · {sessionTimeRangeLabel(session, timeDisplay)} · {secondsLabel(session.duration_seconds ?? 0, locale)}</p>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <Button variant="ghost" onClick={() => setConfirmDelete(false)}>{copy.cancel}</Button>
          <Button
            variant="danger"
            busy={deleteFocus.isPending}
            onClick={() => {
              deleteFocus.mutate(session.id, {
                onSuccess: closeAfterDelete,
                onError: () => show(copy.saveError, 'error'),
              });
            }}
          >
            {copy.deleteAction}
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export default function FocusPage() {
  const locale = useAppLocale();
  const timeDisplay = useTimeDisplay();
  const copy = COPY[locale];
  const [startOpen, setStartOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reviewSession, setReviewSession] = useState<FocusSession | null>(null);
  const [detailsSessionId, setDetailsSessionId] = useState<string | null>(null);
  const [detailsFromHistory, setDetailsFromHistory] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [mainPeriod, setMainPeriod] = useState<MainPeriod>('week');
  const [historyPeriod, setHistoryPeriod] = useState<FocusPeriod>('week');
  const [historyCustomRange, setHistoryCustomRange] = useState(() => rangeDefaults(timeDisplay.timezone));
  const state = useFocusState();
  const summary = useFocusSummary(mainPeriod);
  const selectedDateSummary = useFocusSummary('custom', {
    from_date: selectedDate ?? undefined,
    to_date: selectedDate ?? undefined,
    enabled: selectedDate !== null,
  });
  const sessionsQuery = useFocusSessions(mainPeriod);
  const historySummary = useFocusSummary(historyPeriod, historyPeriod === 'custom' ? historyCustomRange : undefined);
  const detailsQuery = useFocusSession(detailsSessionId);
  const active = state.data?.active_session ?? null;
  const activeBreak = state.data?.active_break ?? null;
  const today = state.data?.today;
  const sessions = sessionsQuery.data?.items ?? state.data?.recent_sessions ?? [];
  const daily = summary.data?.daily_activity ?? [];
  const historyPreview = sessions.slice(0, 5);
  const scopedSessionsLabel = mainPeriod === 'month' ? copy.sessionsThisMonth : copy.sessionsThisWeek;
  const mainProjectBreakdown = selectedDate
    ? (selectedDateSummary.data?.project_breakdown ?? [])
    : (summary.data?.project_breakdown ?? []);
  const mainMaxProjectSeconds = Math.max(1, ...(mainProjectBreakdown.map((item) => item.focus_seconds)));
  const openMainDetails = (session: FocusSession) => {
    setDetailsFromHistory(false);
    setDetailsSessionId(session.id);
  };
  const openHistoryDetails = (sessionId: string) => {
    setDetailsFromHistory(true);
    setDetailsSessionId(sessionId);
  };
  const openInsightDetails = (sessionId: string) => {
    setDetailsFromHistory(false);
    setDetailsSessionId(sessionId);
  };
  const closeDetails = () => {
    setDetailsSessionId(null);
    setDetailsFromHistory(false);
  };
  const toggleMainDate = (date: string) => {
    setSelectedDate((current) => (current === date ? null : date));
  };
  const openHistory = () => {
    setHistoryPeriod(mainPeriod);
    setHistoryCustomRange(rangeDefaults(timeDisplay.timezone));
    setHistoryOpen(true);
  };

  useEffect(() => {
    setSelectedDate(null);
  }, [mainPeriod]);

  useEffect(() => {
    setSelectedDate(null);
    setHistoryCustomRange(rangeDefaults(timeDisplay.timezone));
  }, [timeDisplay.timezone]);

  if (state.isPending) {
    return (
      <div className="pb-32">
        <SkeletonList count={4} lines={2} />
      </div>
    );
  }

  if (!state.data) {
    return (
      <div className="pb-32">
        <Card className="p-5" strong>
          <div role="alert">
            <p className="text-[15px] font-semibold text-ink">{copy.stateError}</p>
            <Button className="mt-4" onClick={() => void state.refetch()}>{copy.retry}</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <Stagger className="pb-32">
      {active ? (
        <Rise>
          <ActiveSessionCard session={active} locale={locale} onReviewSession={setReviewSession} />
        </Rise>
      ) : activeBreak ? (
        <Rise>
          <ActiveBreakCard session={activeBreak} locale={locale} />
        </Rise>
      ) : (
        <Rise>
          <EmptyFocusCard onStart={() => setStartOpen(true)} onLog={() => setLogOpen(true)} locale={locale} />
        </Rise>
      )}

      <Rise>
        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <Card className="px-3 py-3 text-center" strong>
            <Clock3 size={18} className="mx-auto mb-1.5 text-accent-text" />
            <p className="tnum text-[19px] font-semibold text-ink">{secondsLabel(today?.focus_seconds ?? 0, locale)}</p>
            <p className="mt-0.5 text-[12px] text-hint">{copy.today}</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <BarChart3 size={18} className="mx-auto mb-1.5 text-accent-text" />
            <p className="tnum text-[19px] font-semibold text-ink">{today?.completed_sessions ?? 0}</p>
            <p className="mt-0.5 text-[12px] text-hint">{copy.sessionsToday}</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <Flame size={18} className="mx-auto mb-1.5 text-accent-text" />
            <p className="tnum text-[19px] font-semibold text-ink">{today?.streak_days ?? 0}</p>
            <p className="mt-0.5 text-[12px] text-hint">{copy.dayStreak}</p>
            <p className="mt-0.5 text-[10.5px] text-hint">{copy.focusDays}</p>
          </Card>
        </div>
      </Rise>

      {active || activeBreak ? (
        <Rise>
          <button
            type="button"
            onClick={openHistory}
            className="mt-4 flex w-full items-center justify-between rounded-2xl border border-hairline bg-[var(--surface-strong)] px-4 py-4 text-left shadow-card"
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-accent-text">
                <BarChart3 size={23} />
              </span>
              <span className="min-w-0">
                <span className="block text-[16px] font-semibold text-ink">{copy.detailsHistory}</span>
                <span className="mt-0.5 block truncate text-[13px] text-hint">{copy.detailsHistoryBody}</span>
              </span>
            </span>
            <ChevronRight size={20} className="shrink-0 text-hint" />
          </button>
        </Rise>
      ) : (
        <>
          <InsightsSection
            locale={locale}
            timeDisplay={timeDisplay}
            onOpenSession={openInsightDetails}
          />

          <Rise>
        <SectionHeader
          title={copy.analytics}
          action={
            <div className="flex gap-1.5">
              <Chip label={copy.week} active={mainPeriod === 'week'} onClick={() => setMainPeriod('week')} />
              <Chip label={copy.month} active={mainPeriod === 'month'} onClick={() => setMainPeriod('month')} />
            </div>
          }
        />
        <Card className="p-4" strong>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="tnum text-[25px] font-semibold text-ink">{secondsLabel(summary.data?.total_focus_seconds ?? 0, locale)}</p>
              <p className="text-[12.5px] text-hint">{mainPeriod === 'week' ? copy.forWeek : copy.forMonth}</p>
            </div>
            <div className="text-right text-[12.5px] text-hint">
              <p>{summary.data?.total_sessions ?? 0} {scopedSessionsLabel}</p>
              <p>{summary.data?.average_focus_score ?? '—'} {copy.avgFocusScore}</p>
            </div>
          </div>
          <div className="mt-4">
            <AnalyticsKpis summary={summary.data} locale={locale} period={mainPeriod} />
          </div>
          <div className="mt-4">
            <ActivityBarChart items={daily} locale={locale} selectedDate={selectedDate} onSelectDate={toggleMainDate} />
          </div>
          {mainProjectBreakdown.length ? (
            <div className="mt-4 divide-y divide-hairline">
              {mainProjectBreakdown.slice(0, 5).map((item) => (
                <div key={item.project_id ?? item.project_name ?? copy.noProject} className="py-2.5">
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2 text-[13.5px] font-medium text-ink">
                      <CircleDot size={14} className="shrink-0 text-accent-text" />
                      <span className="truncate">{item.project_name ?? copy.noProject}</span>
                    </span>
                    <span className="tnum shrink-0 text-[13px] text-hint">{secondsLabel(item.focus_seconds, locale)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--hairline)]">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{
                        width: `${Math.max(4, Math.round((item.focus_seconds / mainMaxProjectSeconds) * 100))}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
              {mainProjectBreakdown.length > 5 && (
                <button type="button" onClick={openHistory} className="flex w-full items-center justify-between py-3 text-[13px] font-medium text-accent-text">
                  <span>{copy.viewAllHistory}</span>
                  <ChevronRight size={17} />
                </button>
              )}
            </div>
          ) : (
            <p className="mt-4 text-[13px] text-hint">{copy.projectsEmpty}</p>
          )}
        </Card>
          </Rise>

          <Rise>
        <SectionHeader
          title={copy.history}
          action={
            <button
              type="button"
              onClick={openHistory}
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-[12.5px] font-medium text-ink"
            >
              <BarChart3 size={14} className="text-hint" />
              {copy.viewAll}
            </button>
          }
        />
        <Card className="divide-y divide-hairline overflow-hidden !p-0" strong>
          {historyPreview.length > 0 ? (
            <>
            {historyPreview.map((item) => (
              <button
                key={item.id}
                type="button"
                data-testid="focus-history-preview-row"
                onClick={() => openMainDetails(item)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                  <p className="truncate text-[12.5px] text-hint">{shortDateLabel(sessionDateKey(item), locale)} · {sessionMetaLabel(item, copy, timeDisplay)}</p>
                </div>
                <span className="tnum shrink-0 text-[13px] font-medium text-ink">{secondsLabel(item.duration_seconds ?? 0, locale)}</span>
              </button>
            ))}
            {sessions.length > historyPreview.length && (
              <button
                type="button"
                onClick={openHistory}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[14px] font-medium text-accent-text"
              >
                <span>{copy.viewAllHistory}</span>
                <ChevronRight size={18} />
              </button>
            )}
            </>
          ) : (
            <p className="px-4 py-4 text-[13px] text-hint">{copy.historyEmpty}</p>
          )}
        </Card>
          </Rise>
        </>
      )}

      <StartSheet open={startOpen} onClose={() => setStartOpen(false)} locale={locale} />
      <ManualLogSheet open={logOpen} onClose={() => setLogOpen(false)} locale={locale} />
      <ReflectionSheet session={reviewSession} open={reviewSession !== null} onClose={() => setReviewSession(null)} locale={locale} />
      <SessionDetailsSheet
        open={detailsSessionId !== null}
        onClose={closeDetails}
        onBack={detailsFromHistory ? closeDetails : undefined}
        onDeleted={closeDetails}
        session={detailsQuery.data?.session ?? null}
        locale={locale}
      />
      <HistoryDetailsSheet
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        locale={locale}
        period={historyPeriod}
        onPeriodChange={setHistoryPeriod}
        customRange={historyCustomRange}
        onCustomRangeChange={setHistoryCustomRange}
        summary={historySummary.data}
        onSelectSession={openHistoryDetails}
      />
    </Stagger>
  );
}
