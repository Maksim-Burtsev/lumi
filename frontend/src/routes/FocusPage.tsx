import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  Check,
  ChevronRight,
  CircleDot,
  ClipboardPenLine,
  Clock3,
  Flame,
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
  useFinishFocusSession,
  useFocusSessions,
  useFocusState,
  useFocusSummary,
  useLogFocusSession,
  useStartFocusSession,
  useTasks,
  useUpdateFocusSession,
} from '../api/hooks';
import type { FocusDailyActivity, FocusSession, FocusSummaryResponse, Task } from '../api/types';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Sheet } from '../components/ui/Sheet';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import type { AppLocale } from '../lib/i18n';
import { formatTime } from '../lib/format';
import { useAppLocale } from '../lib/useAppLocale';
import { haptic } from '../telegram/webapp';

const DURATIONS = [25, 45, 60];
const DEFAULT_DURATION = 45;

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
    editSession: 'Review session',
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
    reflectionTitle: 'Session review',
    doneQuestion: 'What got done?',
    donePlaceholder: 'Short result',
    blockersQuestion: 'What got in the way?',
    blockersPlaceholder: 'Distractions, blockers, context',
    nextStep: 'Next step',
    nextStepPlaceholder: 'What happens next?',
    score: 'Focus',
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
    week: 'Week',
    month: 'Month',
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
    vsAverage: 'vs 4-week avg',
    morning: 'Morning',
    afternoon: 'Afternoon',
    evening: 'Evening',
    night: 'Night',
    historyEmpty: 'Completed sessions appear here.',
    historyDetails: 'Session history',
    days: 'Days',
    projects: 'Projects',
    recentSessions: 'Recent sessions',
    searchSessions: 'Search sessions',
    selectedDay: 'Selected day',
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
    editSession: 'Итоги сессии',
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
    reflectionTitle: 'Итог сессии',
    doneQuestion: 'Что сделал?',
    donePlaceholder: 'Коротко зафиксируй результат',
    blockersQuestion: 'Что мешало?',
    blockersPlaceholder: 'Отвлечения, блокеры, контекст',
    nextStep: 'Следующий шаг',
    nextStepPlaceholder: 'Что сделать дальше?',
    score: 'Фокус',
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
    week: 'Неделя',
    month: 'Месяц',
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
    vsAverage: 'к 4-нед. среднему',
    morning: 'Утро',
    afternoon: 'День',
    evening: 'Вечер',
    night: 'Ночь',
    historyEmpty: 'Завершенные сессии появятся здесь.',
    historyDetails: 'История сессий',
    days: 'Дни',
    projects: 'Проекты',
    recentSessions: 'Последние сессии',
    searchSessions: 'Поиск сессий',
    selectedDay: 'Выбранный день',
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

function dateInputValue(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10);
}

function timeInputValue(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(11, 16);
}

function localPartsToDate(date: string, time: string): Date {
  const parsed = new Date(`${date}T${time || '00:00'}`);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

function localPartsToIso(date: string, time: string): string {
  return localPartsToDate(date, time).toISOString();
}

function dayValue(offsetDays: number): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return dateInputValue(date);
}

function previewStartEnd(date: string, time: string, duration: number): string {
  const start = localPartsToDate(date, time);
  const end = new Date(start.getTime() + duration * 60_000);
  return `${formatTime(start.toISOString())} — ${formatTime(end.toISOString())}`;
}

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

function playFocusDoneSound(): void {
  try {
    const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 720;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.22);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.24);
    window.setTimeout(() => void ctx.close(), 300);
  } catch {
    /* best-effort webview sound */
  }
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

function projectOptions(tasks: Task[], summaryProjects: string[]): string[] {
  const seen = new Set<string>();
  for (const value of [...tasks.map((task) => task.project), ...summaryProjects]) {
    const project = value?.trim();
    if (project) seen.add(project);
  }
  return [...seen].sort((a, b) => a.localeCompare(b, 'ru'));
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
  projects: string[];
  selectedProject: string;
  locale: AppLocale;
  onSelect: (project: string) => void;
}

function ProjectPickerSheet({ open, onClose, projects, selectedProject, locale, onSelect }: ProjectPickerSheetProps) {
  const copy = COPY[locale];
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((project) => project.toLowerCase().includes(q));
  }, [projects, query]);
  const custom = query.trim();
  const canUseCustom = custom.length > 0 && !projects.some((project) => project.toLowerCase() === custom.toLowerCase());

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const choose = (project: string) => {
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
            onClick={() => choose('')}
            className={`flex w-full items-center justify-between px-4 py-3 text-left ${selectedProject.trim() === '' ? 'bg-[var(--accent-soft)]' : 'bg-transparent'}`}
          >
            <span className="text-[14.5px] font-medium text-ink">{copy.noProject}</span>
            {selectedProject.trim() === '' && <Check size={16} className="text-accent-text" />}
          </button>
          {visible.map((project) => (
            <button
              key={project}
              type="button"
              onClick={() => choose(project)}
              className={`flex w-full items-center justify-between border-t border-hairline px-4 py-3 text-left ${
                selectedProject === project ? 'bg-[var(--accent-soft)]' : 'bg-transparent'
              }`}
            >
              <span className="text-[14.5px] font-medium text-ink">{project}</span>
              {selectedProject === project && <Check size={16} className="text-accent-text" />}
            </button>
          ))}
          {canUseCustom && (
            <button
              type="button"
              onClick={() => choose(custom)}
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

function StartSheet({
  open,
  onClose,
  locale,
  summaryProjects,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
  summaryProjects: string[];
}) {
  const copy = COPY[locale];
  const tasksQuery = useTasks('all');
  const start = useStartFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [taskId, setTaskId] = useState('');
  const [project, setProject] = useState('');

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const projects = useMemo(() => projectOptions(tasks, summaryProjects), [summaryProjects, tasks]);
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;

  useEffect(() => {
    if (selectedTask?.project) setProject(selectedTask.project);
  }, [selectedTask]);

  const submit = () => {
    const text = intention.trim() || selectedTask?.title || project.trim() || copy.defaultIntention;
    if (start.isPending) return;
    haptic('light');
    start.mutate(
      {
        task_id: taskId || null,
        project: project.trim() || selectedTask?.project || null,
        intention: text,
        planned_minutes: duration,
      },
      {
        onSuccess: () => {
          setIntention('');
          setTaskId('');
          setProject('');
          setDuration(DEFAULT_DURATION);
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
              <span className="min-w-0 truncate">{project.trim() || copy.noProject}</span>
              <span className="text-[12px] text-hint">{copy.chooseProject}</span>
            </button>
          </div>
          <Button fullWidth busy={start.isPending} onClick={submit} icon={<Timer size={16} />}>
            {copy.startCta} {duration} {locale === 'en' ? 'min' : 'мин'}
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
          setProject(task?.project ?? project);
        }}
      />
      <ProjectPickerSheet
        open={projectPickerOpen}
        onClose={() => setProjectPickerOpen(false)}
        projects={projects}
        selectedProject={project}
        locale={locale}
        onSelect={setProject}
      />
    </>
  );
}

function ScorePicker({ value, onChange, label }: { value: number; onChange: (value: number) => void; label: string }) {
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            className={`h-9 flex-1 rounded-full border text-[13px] font-medium ${
              item <= value ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-accent-text' : 'border-hairline text-hint'
            }`}
          >
            {item}
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
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState(4);

  useEffect(() => {
    if (open && session) {
      setAccomplished(session.reflection.accomplished_text ?? '');
      setDistraction(session.reflection.distraction_text ?? '');
      setNextStep(session.reflection.next_step_text ?? '');
      setScore(session.reflection.focus_score ?? 4);
    }
  }, [open, session]);

  if (!session) return null;

  const submit = () => {
    update.mutate(
      {
        id: session.id,
        input: {
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
          <p className="text-[13px] font-medium text-ink">{session.project ?? copy.noProject}</p>
          <p className="mt-0.5 text-[12.5px] text-hint">{session.intention}</p>
        </div>
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
        <ScorePicker value={score} onChange={setScore} label={copy.score} />
        <Button fullWidth busy={update.isPending} onClick={submit} icon={<Check size={16} />}>
          {copy.saveSession}
        </Button>
      </div>
    </Sheet>
  );
}

function ManualLogSheet({
  open,
  onClose,
  locale,
  summaryProjects,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
  summaryProjects: string[];
}) {
  const copy = COPY[locale];
  const tasksQuery = useTasks('all');
  const logFocus = useLogFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [taskId, setTaskId] = useState('');
  const [project, setProject] = useState('');
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState(4);
  const [logDate, setLogDate] = useState(() => dateInputValue(new Date()));
  const [logTime, setLogTime] = useState(() => timeInputValue(new Date()));

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const projects = useMemo(() => projectOptions(tasks, summaryProjects), [summaryProjects, tasks]);
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;
  const preview = useMemo(() => previewStartEnd(logDate, logTime, duration), [duration, logDate, logTime]);

  useEffect(() => {
    if (selectedTask?.project) setProject(selectedTask.project);
  }, [selectedTask]);

  const submit = () => {
    const text = intention.trim() || selectedTask?.title || project.trim() || copy.defaultIntention;
    if (logFocus.isPending) return;
    logFocus.mutate(
      {
        task_id: taskId || null,
        project: project.trim() || selectedTask?.project || null,
        intention: text,
        logged_at: localPartsToIso(logDate, logTime),
        duration_minutes: duration,
        accomplished_text: accomplished.trim() || null,
        distraction_text: distraction.trim() || null,
        next_step_text: nextStep.trim() || null,
        focus_score: score,
      },
      {
        onSuccess: () => {
          setIntention('');
          setDuration(DEFAULT_DURATION);
          setTaskId('');
          setProject('');
          setAccomplished('');
          setDistraction('');
          setNextStep('');
          setScore(4);
          setLogDate(dateInputValue(new Date()));
          setLogTime(timeInputValue(new Date()));
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
            <FieldLabel>{copy.startAt}</FieldLabel>
            <div className="flex gap-2">
              <Chip label={copy.todayChip} active={logDate === dayValue(0)} onClick={() => setLogDate(dayValue(0))} />
              <Chip label={copy.yesterdayChip} active={logDate === dayValue(-1)} onClick={() => setLogDate(dayValue(-1))} />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <label>
                <span className="sr-only">{copy.date}</span>
                <input
                  aria-label={copy.date}
                  type="date"
                  value={logDate}
                  onChange={(event) => setLogDate(event.target.value)}
                  className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
                />
              </label>
              <label>
                <span className="sr-only">{copy.time}</span>
                <input
                  aria-label={copy.time}
                  type="time"
                  value={logTime}
                  onChange={(event) => setLogTime(event.target.value)}
                  className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
                />
              </label>
            </div>
            <p className="tnum rounded-xl border border-hairline bg-[var(--surface)] px-3 py-2 text-[12.5px] text-hint">
              {copy.startEndPreview}: <span className="text-ink">{preview}</span>
            </p>
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
              <span className="min-w-0 truncate">{project.trim() || copy.noProject}</span>
              <span className="text-[12px] text-hint">{copy.chooseProject}</span>
            </button>
          </div>
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
          <ScorePicker value={score} onChange={setScore} label={copy.score} />
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
          setProject(task?.project ?? project);
        }}
      />
      <ProjectPickerSheet
        open={projectPickerOpen}
        onClose={() => setProjectPickerOpen(false)}
        projects={projects}
        selectedProject={project}
        locale={locale}
        onSelect={setProject}
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
  const now = useNow();
  const abandon = useAbandonFocusSession();
  const finish = useFinishFocusSession();
  const [notifiedFor, setNotifiedFor] = useState<string | null>(null);
  const [silencedFor, setSilencedFor] = useState<string | null>(null);
  const overtime = now >= new Date(session.target_end_at).getTime();
  const soundSilenced = silencedFor === session.id;

  useEffect(() => {
    if (!overtime || finish.isPending || soundSilenced) return undefined;
    if (notifiedFor !== session.id) {
      setNotifiedFor(session.id);
      haptic('success');
    }
    playFocusDoneSound();
    const timer = window.setInterval(playFocusDoneSound, 1200);
    return () => window.clearInterval(timer);
  }, [finish.isPending, notifiedFor, overtime, session.id, soundSilenced]);

  const stopAndReview = () => {
    if (finish.isPending) return;
    finish.mutate(
      {
        id: session.id,
        input: { ended_at: new Date().toISOString() },
      },
      {
        onSuccess: (response) => {
          haptic('success');
          onReviewSession(response.session);
        },
      },
    );
  };

  return (
    <Card className="relative overflow-hidden px-4 py-4 sm:px-5 sm:py-5">
        <div aria-hidden className="dawn-glow opacity-50" />
        <div className="relative">
          <div className="flex items-center justify-between gap-3">
            <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-hairline bg-[var(--accent-soft)] px-3 py-1 text-[12px] font-medium text-accent-text">
              <Folder size={14} />
              {session.project ?? copy.noProject}
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
            {formatTime(session.started_at)} — {formatTime(session.target_end_at)}
          </p>
          <div className="mt-4 border-t border-hairline pt-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="truncate text-[20px] font-semibold leading-tight tracking-normal text-ink">{session.intention}</h2>
                <p className="mt-1 truncate text-[13px] text-hint">
                  {session.task?.title ?? session.project ?? copy.session}
                </p>
              </div>
              <button
                type="button"
                onClick={stopAndReview}
                aria-label={copy.editSession}
                className="flex h-11 w-16 shrink-0 items-center justify-center rounded-full border border-hairline text-hint"
              >
                <Pencil size={18} />
              </button>
            </div>
          </div>
          {overtime ? (
            <div className="mt-4 space-y-3">
              <button
                type="button"
                onClick={stopAndReview}
                disabled={finish.isPending}
                aria-label={copy.stopTimerReview}
                className="relative inline-flex h-12 w-full min-w-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-full bg-accent px-5 text-[15.5px] font-semibold text-white shadow-[0_8px_22px_rgba(46,99,231,0.34)] transition-opacity disabled:opacity-55"
              >
                {finish.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={17} />}
                {copy.stopTimerReview}
              </button>
              <div className="grid grid-cols-2 gap-3">
                <Button variant="secondary" onClick={() => setSilencedFor(session.id)}>
                  {copy.keepCounting}
                </Button>
                <Button variant="ghost" busy={abandon.isPending} onClick={() => abandon.mutate(session.id)} icon={<X size={16} />} className="min-w-0">
                  {copy.cancel}
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={stopAndReview}
                disabled={finish.isPending}
                aria-label={copy.finishSession}
                className="relative inline-flex h-11 min-w-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-full bg-accent px-5 text-[14.5px] font-medium text-white shadow-[0_6px_18px_rgba(46,99,231,0.3)] transition-opacity disabled:opacity-55"
              >
                {finish.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                {copy.finishSession}
              </button>
              <Button variant="ghost" busy={abandon.isPending} onClick={() => abandon.mutate(session.id)} icon={<X size={16} />} className="min-w-0">
                {copy.cancel}
              </Button>
            </div>
          )}
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
          <Button onClick={onStart} icon={<Plus size={16} />}>
            {copy.startSession}
          </Button>
          <Button variant="secondary" onClick={onLog} icon={<ClipboardPenLine size={16} />}>
            {copy.logSession}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function sessionDateKey(session: FocusSession): string {
  return session.started_at.slice(0, 10);
}

function ActivityBarChart({
  items,
  locale,
  selectedDate,
  onSelectDate,
}: {
  items: FocusDailyActivity[];
  locale: AppLocale;
  selectedDate: string | null;
  onSelectDate?: (date: string) => void;
}) {
  const copy = COPY[locale];
  const max = Math.max(1, ...items.map((item) => item.focus_seconds));
  const isMonth = items.length > 14;
  const selected = items.find((item) => item.date === selectedDate) ?? [...items].reverse().find((item) => item.focus_seconds > 0) ?? items[items.length - 1];
  const tickIndexes = new Set(
    isMonth
      ? [0, 6, 13, 20, 26, items.length - 1].filter((index) => index >= 0 && index < items.length)
      : items.map((_item, index) => index),
  );

  return (
    <div className="rounded-2xl border border-hairline p-3">
      <div className="grid grid-cols-[28px_1fr] gap-2">
        <div className="flex h-28 flex-col justify-between py-1 text-right text-[10px] text-hint">
          <span>{isMonth ? '8h' : '6h'}</span>
          <span>{isMonth ? '4h' : '3h'}</span>
          <span>0h</span>
        </div>
        <div>
          <div
            className="grid h-28 items-end gap-1.5 border-b border-hairline bg-[linear-gradient(to_bottom,transparent_0,transparent_32%,var(--hairline)_33%,transparent_34%,transparent_66%,var(--hairline)_67%,transparent_68%)]"
            style={{ gridTemplateColumns: `repeat(${items.length}, minmax(${isMonth ? '5px' : '14px'}, 1fr))` }}
          >
            {items.map((item) => {
              const active = selected?.date === item.date;
              const percent = item.focus_seconds > 0 ? Math.max(8, Math.round((item.focus_seconds / max) * 100)) : 0;
              return (
                <button
                  key={item.date}
                  type="button"
                  data-testid="focus-day-bar"
                  onClick={() => onSelectDate?.(item.date)}
                  className={`group flex h-full min-w-0 items-end justify-center rounded-t-xl px-0.5 outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)] ${
                    active ? 'bg-[var(--accent-soft)]' : ''
                  }`}
                  aria-label={`${item.date}: ${secondsLabel(item.focus_seconds, locale)}`}
                >
                  <span
                    className={`block w-full max-w-[18px] rounded-t-full transition-all ${
                      active ? 'bg-accent shadow-[0_0_0_1px_var(--accent-border)]' : item.focus_seconds > 0 ? 'bg-accent opacity-70' : 'bg-[var(--hairline)]'
                    }`}
                    style={{ height: `${percent}%` }}
                  />
                </button>
              );
            })}
          </div>
          <div
            className="mt-1 grid gap-1.5"
            style={{ gridTemplateColumns: `repeat(${items.length}, minmax(${isMonth ? '5px' : '14px'}, 1fr))` }}
          >
            {items.map((item, index) => (
              <span key={item.date} className={`tnum text-center text-[10px] ${tickIndexes.has(index) ? 'text-hint' : 'text-transparent'}`}>
                {isMonth ? new Date(`${item.date}T00:00:00`).getDate() : weekdayLabel(item.date, locale).slice(0, 2)}
              </span>
            ))}
          </div>
        </div>
      </div>
      {selected && (
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
  summary,
  sessions,
  onSelectSession,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
  period: 'week' | 'month';
  onPeriodChange: (period: 'week' | 'month') => void;
  summary: FocusSummaryResponse | undefined;
  sessions: FocusSession[];
  onSelectSession: (session: FocusSession) => void;
}) {
  const copy = COPY[locale];
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const daily = summary?.daily_activity ?? [];
  const activeDate = selectedDate ?? [...daily].reverse().find((item) => item.focus_seconds > 0)?.date ?? daily[daily.length - 1]?.date ?? null;
  const normalizedQuery = query.trim().toLowerCase();
  const visibleSessions = sessions.filter((item) => {
    if (!normalizedQuery) return true;
    return `${item.intention} ${item.project ?? ''} ${item.task?.title ?? ''}`.toLowerCase().includes(normalizedQuery);
  });
  const groupedSessions = visibleSessions.reduce<Array<{ date: string; items: FocusSession[] }>>((groups, item) => {
    const date = sessionDateKey(item);
    const group = groups.find((entry) => entry.date === date);
    if (group) group.items.push(item);
    else groups.push({ date, items: [item] });
    return groups;
  }, []);
  const maxProjectSeconds = Math.max(1, ...(summary?.project_breakdown ?? []).map((item) => item.focus_seconds));

  useEffect(() => {
    if (open) {
      setSelectedDate(null);
      setQuery('');
    }
  }, [open]);

  return (
    <Sheet open={open} onClose={onClose} title={copy.historyDetails}>
      <div className="space-y-5">
        <div className="flex gap-1.5">
          <Chip label={copy.week} active={period === 'week'} onClick={() => onPeriodChange('week')} />
          <Chip label={copy.month} active={period === 'month'} onClick={() => onPeriodChange('month')} />
          <Chip label="Custom" active={false} onClick={() => undefined} />
        </div>
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
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-ink">{copy.days}</h3>
            <span className="tnum text-[12px] text-hint">{activeDate ?? '—'}</span>
          </div>
          <ActivityBarChart items={daily} locale={locale} selectedDate={activeDate} onSelectDate={setSelectedDate} />
        </section>

        <section>
          <h3 className="mb-2 text-[13px] font-semibold text-ink">{copy.projects}</h3>
          <div className="space-y-2.5">
            {(summary?.project_breakdown ?? []).map((item) => (
              <div key={item.project}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[12.5px]">
                  <span className="truncate font-medium text-ink">{item.project}</span>
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
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-[13px] font-semibold text-ink">{copy.recentSessions}</h3>
          <div className="max-h-[34dvh] overflow-y-auto rounded-2xl border border-hairline">
            {groupedSessions.length > 0 ? (
              groupedSessions.map((group) => (
                <div key={group.date} className="border-b border-hairline last:border-b-0">
                  <div className="bg-[var(--surface)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-hint">
                    {shortDateLabel(group.date, locale)}
                  </div>
                  {group.items.map((item) => (
                    <button key={item.id} type="button" onClick={() => onSelectSession(item)} className="block w-full border-t border-hairline px-4 py-3 text-left first:border-t-0">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                          <p className="mt-0.5 truncate text-[12.5px] text-hint">
                            {item.project ?? copy.noProject}{item.task ? ` · ${item.task.title}` : ''}
                          </p>
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
              <p className="px-4 py-4 text-[13px] text-hint">{copy.noSessionsForDay}</p>
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

function AnalyticsKpis({ summary, locale }: { summary: FocusSummaryResponse | undefined; locale: AppLocale }) {
  const copy = COPY[locale];
  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3">
        <p className="text-[11px] font-medium text-hint">{copy.avgDay}</p>
        <p className="tnum mt-1 text-[18px] font-semibold text-ink">{secondsLabel(summary?.average_daily_focus_seconds ?? 0, locale)}</p>
        <KpiDelta value={summary?.average_daily_focus_delta_percent ?? null} />
      </div>
      <div className="rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3">
        <p className="text-[11px] font-medium text-hint">{copy.total}</p>
        <p className="tnum mt-1 text-[18px] font-semibold text-ink">{secondsLabel(summary?.total_focus_seconds ?? 0, locale)}</p>
        <KpiDelta value={summary?.total_focus_delta_percent ?? null} />
      </div>
      <div className="rounded-2xl border border-hairline bg-[var(--surface)] px-3 py-3">
        <p className="text-[11px] font-medium text-hint">{copy.mostFocused}</p>
        <p className="mt-1 truncate text-[18px] font-semibold text-ink">{daypartLabel(summary?.most_focused_daypart ?? null, copy)}</p>
        <p className="truncate text-[11px] text-hint">{copy.vsAverage}</p>
      </div>
    </div>
  );
}

function SessionDetailsSheet({
  open,
  onClose,
  onDeleted,
  session,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  onDeleted?: () => void;
  session: FocusSession | null;
  locale: AppLocale;
}) {
  const copy = COPY[locale];
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
      <Sheet open={open} onClose={onClose} title={copy.sessionDetails}>
        <div className="space-y-4">
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] p-4">
            <p className="text-[19px] font-semibold text-ink">{session.intention}</p>
            <p className="mt-1 text-[13px] text-hint">
              {session.project ?? copy.noProject}{session.task ? ` · ${session.task.title}` : ''}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 text-[13px]">
              <div className="rounded-xl bg-[var(--surface-strong)] px-3 py-2">
                <p className="text-hint">{copy.startEndPreview}</p>
                <p className="tnum mt-0.5 text-ink">{formatTime(session.started_at)} — {formatTime(session.ended_at ?? session.target_end_at)}</p>
              </div>
              <div className="rounded-xl bg-[var(--surface-strong)] px-3 py-2">
                <p className="text-hint">{copy.duration}</p>
                <p className="tnum mt-0.5 text-ink">{secondsLabel(session.duration_seconds ?? 0, locale)}</p>
              </div>
            </div>
          </div>
          <div className="rounded-2xl border border-hairline bg-[var(--surface)] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[14px] font-semibold text-ink">{copy.reflectionTitle}</h3>
              <span className="tnum text-[13px] text-hint">{reflection.focus_score ? `${reflection.focus_score}/5` : '—'}</span>
            </div>
            {reflection.accomplished_text || reflection.distraction_text || reflection.next_step_text ? (
              <div className="space-y-3 text-[13px] leading-relaxed">
                {reflection.accomplished_text && <p><span className="font-medium text-ink">{copy.doneQuestion}</span><br /><span className="text-hint">{reflection.accomplished_text}</span></p>}
                {reflection.distraction_text && <p><span className="font-medium text-ink">{copy.blockersQuestion}</span><br /><span className="text-hint">{reflection.distraction_text}</span></p>}
                {reflection.next_step_text && <p><span className="font-medium text-ink">{copy.nextStep}</span><br /><span className="text-hint">{reflection.next_step_text}</span></p>}
              </div>
            ) : (
              <p className="text-[13px] text-hint">{copy.noReflection}</p>
            )}
          </div>
          <Button fullWidth onClick={() => setEditOpen(true)} icon={<Pencil size={16} />}>
            {copy.editReview}
          </Button>
          <Button fullWidth variant="danger" busy={deleteFocus.isPending} onClick={() => setConfirmDelete(true)} icon={<Trash2 size={16} />}>
            {copy.deleteSession}
          </Button>
        </div>
      </Sheet>
      <ReflectionSheet session={session} open={editOpen} onClose={() => setEditOpen(false)} locale={locale} />
      {confirmDelete && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/35 px-5" role="dialog" aria-modal="true" aria-labelledby="focus-delete-title">
          <div className="w-full max-w-[360px] rounded-3xl border border-hairline bg-[var(--surface-strong)] p-5 shadow-card">
            <h3 id="focus-delete-title" className="text-[19px] font-semibold text-ink">{copy.deleteTitle}</h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-hint">{copy.deleteBody}</p>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>{copy.cancel}</Button>
              <Button
                variant="danger"
                busy={deleteFocus.isPending}
                onClick={() => {
                  deleteFocus.mutate(session.id, {
                    onSuccess: closeAfterDelete,
                  });
                }}
              >
                {copy.deleteAction}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function FocusPage() {
  const locale = useAppLocale();
  const copy = COPY[locale];
  const [startOpen, setStartOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reviewSession, setReviewSession] = useState<FocusSession | null>(null);
  const [detailsSession, setDetailsSession] = useState<FocusSession | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const state = useFocusState();
  const summary = useFocusSummary(period);
  const sessionsQuery = useFocusSessions(period);
  const active = state.data?.active_session ?? null;
  const today = state.data?.today;
  const sessions = sessionsQuery.data?.items ?? state.data?.recent_sessions ?? [];
  const daily = summary.data?.daily_activity ?? [];
  const activeDate = selectedDate ?? [...daily].reverse().find((item) => item.focus_seconds > 0)?.date ?? null;
  const summaryProjects = useMemo(() => summary.data?.project_breakdown.map((item) => item.project) ?? [], [summary.data]);
  const historyPreview = sessions.slice(0, 5);
  const scopedSessionsLabel = period === 'month' ? copy.sessionsThisMonth : copy.sessionsThisWeek;

  return (
    <Stagger className="pb-32">
      {state.isPending ? (
        <SkeletonList count={4} lines={2} />
      ) : active ? (
        <Rise>
          <ActiveSessionCard session={active} locale={locale} onReviewSession={setReviewSession} />
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

      {active ? (
        <Rise>
          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
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
          <Rise>
        <SectionHeader
          title={copy.analytics}
          action={
            <div className="flex gap-1.5">
              <Chip label={copy.week} active={period === 'week'} onClick={() => setPeriod('week')} />
              <Chip label={copy.month} active={period === 'month'} onClick={() => setPeriod('month')} />
            </div>
          }
        />
        <Card className="p-4" strong>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="tnum text-[25px] font-semibold text-ink">{secondsLabel(summary.data?.total_focus_seconds ?? 0, locale)}</p>
              <p className="text-[12.5px] text-hint">{period === 'week' ? copy.forWeek : copy.forMonth}</p>
            </div>
            <div className="text-right text-[12.5px] text-hint">
              <p>{summary.data?.total_sessions ?? 0} {scopedSessionsLabel}</p>
              <p>{summary.data?.average_focus_score ?? '—'} {copy.avgFocusScore}</p>
            </div>
          </div>
          <div className="mt-4">
            <AnalyticsKpis summary={summary.data} locale={locale} />
          </div>
          <div className="mt-4">
            <ActivityBarChart items={daily} locale={locale} selectedDate={activeDate} onSelectDate={(date) => {
              setSelectedDate(date);
              setHistoryOpen(true);
            }} />
          </div>
          {summary.data?.project_breakdown.length ? (
            <div className="mt-4 divide-y divide-hairline">
              {summary.data.project_breakdown.map((item) => (
                <div key={item.project} className="py-2.5">
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2 text-[13.5px] font-medium text-ink">
                      <CircleDot size={14} className="shrink-0 text-accent-text" />
                      <span className="truncate">{item.project}</span>
                    </span>
                    <span className="tnum shrink-0 text-[13px] text-hint">{secondsLabel(item.focus_seconds, locale)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--hairline)]">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{
                        width: `${Math.max(4, Math.round((item.focus_seconds / Math.max(1, summary.data.project_breakdown[0]?.focus_seconds ?? 1)) * 100))}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
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
              onClick={() => setHistoryOpen(true)}
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
                onClick={() => setDetailsSession(item)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                  <p className="truncate text-[12.5px] text-hint">{item.project ?? copy.noProject}{item.task ? ` · ${item.task.title}` : ''}</p>
                </div>
                <span className="tnum shrink-0 text-[13px] font-medium text-ink">{secondsLabel(item.duration_seconds ?? 0, locale)}</span>
              </button>
            ))}
            {sessions.length > historyPreview.length && (
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
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

      <StartSheet open={startOpen} onClose={() => setStartOpen(false)} locale={locale} summaryProjects={summaryProjects} />
      <ManualLogSheet open={logOpen} onClose={() => setLogOpen(false)} locale={locale} summaryProjects={summaryProjects} />
      <ReflectionSheet session={reviewSession} open={reviewSession !== null} onClose={() => setReviewSession(null)} locale={locale} />
      <SessionDetailsSheet
        open={detailsSession !== null}
        onClose={() => setDetailsSession(null)}
        onDeleted={() => setDetailsSession(null)}
        session={detailsSession}
        locale={locale}
      />
      <HistoryDetailsSheet
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        locale={locale}
        period={period}
        onPeriodChange={setPeriod}
        summary={summary.data}
        sessions={sessions}
        onSelectSession={(session) => {
          setHistoryOpen(false);
          setDetailsSession(session);
        }}
      />
    </Stagger>
  );
}
