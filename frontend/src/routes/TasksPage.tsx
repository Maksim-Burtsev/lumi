import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  FolderInput,
  FolderKanban,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react';
import {
  useAssistantSuggestions,
  useCompleteTask,
  useCreateTask,
  useDecideAssistantSuggestion,
  usePatchTask,
  useProjectTasks,
  useProjects,
  useSnoozeTask,
  useTasks,
} from '../api/hooks';
import type { AssistantSuggestion, Project, SnoozePreset, Task, TaskFilter } from '../api/types';
import { TaskCard } from '../components/task/TaskCard';
import { TaskEditSheet } from '../components/task/TaskEditSheet';
import { Chip } from '../components/ui/Chip';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Sheet } from '../components/ui/Sheet';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';
import { haptic } from '../telegram/webapp';

type TaskView = 'today' | 'projects' | 'review' | 'done';
type ReviewMode = 'estimates' | 'due_dates' | 'projects';
type EstimateSuggestion = { id: string; taskId: string; minutes: number; reason?: string | null };
type DueBucket = 'week' | 'backlog' | 'context';
type DueDateDecision = {
  id: string;
  task: Task;
  suggestionId?: string;
  bucket: DueBucket;
  dueAt: string | null;
  noDeadline: boolean;
  reason: string;
};
type ProjectDecision = {
  id: string;
  task: Task;
  suggestionId?: string;
  projectId?: string | null;
  projectName: string;
  confidence?: string | null;
  reason: string;
};

const COPY = {
  en: {
    tabs: { today: 'Today', projects: 'Projects', review: 'Review', done: 'Done' },
    newTask: 'New task...',
    searchTasks: 'Search tasks',
    addTask: 'Add task',
    create: 'Create',
    taskTitle: 'Task title',
    emptyToday: ['No tasks for today', 'Add a task. Lumi can fill details later.'],
    emptyProjects: ['Projects will appear here', 'Add #project or set a project in a task.'],
    emptyReview: ['Nothing to review', 'Lumi will show estimates, due dates, and project suggestions here.'],
    emptyDone: ['No completed tasks yet', 'Completed tasks will stay here.'],
    loadError: 'Could not load tasks.',
    createFailed: 'Could not create task',
    completeFailed: 'Could not complete task',
    snoozed: 'Task moved',
    snoozeFailed: 'Could not move task',
    estimateSaved: 'Estimate saved',
    saveFailed: 'Could not save',
    projectHealth: 'Project Health',
    projectSubtitle: 'Sorted by what needs your attention',
    needsAttention: 'Needs attention',
    moving: 'Moving',
    light: 'Light',
    quiet: 'Quiet',
    nextPrefix: 'Next:',
    noNext: 'No next move',
    openProject: 'Open project',
    whyAttention: 'Why it needs attention',
    nextMove: 'Next move',
    next: 'Next',
    later: 'Later',
    doneRecently: 'Done recently',
    open: 'Open',
    reviewHub: 'Review Hub',
    reviewSubtitle: 'Quick decisions Lumi can prepare without blocking capture',
    estimates: 'Estimates',
    estimatesHint: 'Time estimates ready to accept or edit',
    estimateSuggestions: 'Estimate suggestions',
    noEstimateSuggestions: 'No estimate suggestions ready',
    reviewEstimates: 'Review estimates',
    reviewDueDates: 'Review plan dates',
    reviewProjects: 'Review project sorting',
    dueDates: 'Plan dates',
    dueDatesHint: 'Prepared date or no-deadline decisions',
    projectSuggestions: 'Sort into projects',
    projectSuggestionsHint: 'Prepared project choices for loose tasks',
    likelyThisWeek: 'Likely this week',
    somedayBacklog: 'Someday / Backlog',
    needsContext: 'Needs context',
    suggestedDate: 'Suggested date',
    noDeadline: 'No deadline',
    suggestedProject: 'Suggested project',
    keepUnassigned: 'Keep unassigned',
    backlogCleanup: 'Backlog cleanup',
    backlogCleanupHint: 'Lumi can quietly turn this into clear next actions.',
    estimate: 'Estimate',
    planDates: 'Plan dates',
    sortProjects: 'Sort projects',
    workDone: 'Work done',
    completedThisWeek: 'Completed this week',
    clearedTime: 'Cleared time',
    yesterday: 'Yesterday',
    earlier: 'Earlier',
    undo: 'Undo',
    reopened: 'Task reopened',
    reopenFailed: 'Could not reopen task',
    chooseDate: 'Choose date',
    chooseProject: 'Choose project',
    estimateTask: 'Estimate task',
    suggested: 'Suggested',
    save: 'Save',
    close: 'Close',
    skip: 'Skip',
    change: 'Change',
    doNotEstimate: 'Do not estimate',
    custom: 'Custom',
  },
  ru: {
    tabs: { today: 'Сегодня', projects: 'Проекты', review: 'Разбор', done: 'Готово' },
    newTask: 'Новая задача...',
    searchTasks: 'Поиск задач',
    addTask: 'Добавить задачу',
    create: 'Создать',
    taskTitle: 'Название задачи',
    emptyToday: ['На сегодня всё чисто', 'Быстро добавь задачу сверху — Lumi разберёт детали позже.'],
    emptyProjects: ['Проекты появятся здесь', 'Добавь задачу с #проектом или укажи проект в карточке задачи.'],
    emptyReview: ['Разбор пуст', 'Здесь будут оценки, сроки и проекты, где Lumi может помочь.'],
    emptyDone: ['Здесь появятся выполненные задачи', 'Отмечай задачи кружком слева — Lumi сохранит историю.'],
    loadError: 'Не удалось загрузить задачи.',
    createFailed: 'Не удалось создать задачу',
    completeFailed: 'Не удалось выполнить',
    snoozed: 'Задача отложена',
    snoozeFailed: 'Не удалось отложить',
    estimateSaved: 'Оценка сохранена',
    saveFailed: 'Не удалось сохранить',
    projectHealth: 'Состояние проектов',
    projectSubtitle: 'Сначала то, что требует внимания',
    needsAttention: 'Требует внимания',
    moving: 'Движется',
    light: 'Легкий',
    quiet: 'Тихий',
    nextPrefix: 'Дальше:',
    noNext: 'Нет следующего шага',
    openProject: 'Открыть проект',
    whyAttention: 'Почему требует внимания',
    nextMove: 'Следующий шаг',
    next: 'Дальше',
    later: 'Позже',
    doneRecently: 'Недавно готово',
    open: 'Открыть',
    reviewHub: 'Разбор',
    reviewSubtitle: 'Быстрые решения, которые Lumi подготовила без блокировки создания задач',
    estimates: 'Оценки',
    estimatesHint: 'Оценки времени готовы к принятию или правке',
    estimateSuggestions: 'Предложенные оценки',
    noEstimateSuggestions: 'Нет готовых оценок',
    reviewEstimates: 'Разобрать оценки',
    reviewDueDates: 'Разобрать даты',
    reviewProjects: 'Разложить по проектам',
    dueDates: 'План дат',
    dueDatesHint: 'Готовые решения: дата или без срока',
    projectSuggestions: 'Разложить по проектам',
    projectSuggestionsHint: 'Готовые проектные решения для свободных задач',
    likelyThisWeek: 'Вероятно на этой неделе',
    somedayBacklog: 'Когда-нибудь / Backlog',
    needsContext: 'Нужен контекст',
    suggestedDate: 'Предложенная дата',
    noDeadline: 'Без срока',
    suggestedProject: 'Предложенный проект',
    keepUnassigned: 'Оставить без проекта',
    backlogCleanup: 'Разбор Backlog',
    backlogCleanupHint: 'Lumi может тихо превратить это в понятные следующие действия.',
    estimate: 'Оценить',
    planDates: 'Даты',
    sortProjects: 'Проекты',
    workDone: 'Сделано',
    completedThisWeek: 'Готово за неделю',
    clearedTime: 'Закрыто времени',
    yesterday: 'Вчера',
    earlier: 'Раньше',
    undo: 'Вернуть',
    reopened: 'Задача возвращена',
    reopenFailed: 'Не удалось вернуть задачу',
    chooseDate: 'Выбрать дату',
    chooseProject: 'Выбрать проект',
    estimateTask: 'Оценить задачу',
    suggested: 'Предложено',
    save: 'Сохранить',
    close: 'Закрыть',
    skip: 'Пропустить',
    change: 'Изменить',
    doNotEstimate: 'Не оценивать',
    custom: 'Свое',
  },
} satisfies Record<AppLocale, Record<string, unknown>>;

function copyFor(locale: AppLocale) {
  return COPY[locale] as typeof COPY.en;
}

function viewToTaskFilter(view: TaskView): TaskFilter {
  if (view === 'done') return 'done';
  if (view === 'review') return 'review';
  if (view === 'projects') return 'all';
  return 'today';
}

function parseEstimateSuggestion(suggestion: AssistantSuggestion): EstimateSuggestion | null {
  if (suggestion.kind !== 'task_estimate') return null;
  const taskId = typeof suggestion.payload.task_id === 'string'
    ? suggestion.payload.task_id
    : suggestion.affected_task_ids[0];
  const minutes = suggestion.payload.estimated_minutes;
  if (!taskId || typeof minutes !== 'number' || minutes <= 0) return null;
  return {
    id: suggestion.id,
    taskId,
    minutes,
    reason: typeof suggestion.payload.reason === 'string' ? suggestion.payload.reason : suggestion.description,
  };
}

function estimateMap(suggestions: AssistantSuggestion[]): Map<string, EstimateSuggestion> {
  const map = new Map<string, EstimateSuggestion>();
  for (const suggestion of suggestions) {
    const parsed = parseEstimateSuggestion(suggestion);
    if (parsed && !map.has(parsed.taskId)) map.set(parsed.taskId, parsed);
  }
  return map;
}

function suggestionTaskId(suggestion: AssistantSuggestion): string | null {
  return typeof suggestion.payload.task_id === 'string'
    ? suggestion.payload.task_id
    : suggestion.affected_task_ids[0] ?? null;
}

function bucketFromSuggestion(value: unknown, task: Task): DueBucket {
  if (typeof value === 'string') {
    const normalized = value.toLocaleLowerCase();
    if (normalized.includes('backlog') || normalized.includes('someday')) return 'backlog';
    if (normalized.includes('context')) return 'context';
    if (normalized.includes('week')) return 'week';
  }
  if (task.project === 'Backlog') return 'backlog';
  return task.estimated_minutes !== null && task.estimated_minutes <= 30 ? 'week' : 'context';
}

function defaultWeekDueIso(): string {
  const date = new Date();
  const day = date.getDay();
  const daysToFriday = (5 - day + 7) % 7 || 2;
  date.setDate(date.getDate() + daysToFriday);
  date.setHours(18, 0, 0, 0);
  return date.toISOString();
}

function formatDateDecisionLabel(dueAt: string | null, locale: AppLocale): string {
  if (!dueAt) return copyFor(locale).noDeadline;
  return new Intl.DateTimeFormat(locale === 'ru' ? 'ru-RU' : 'en-US', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dueAt));
}

function dueBucketLabel(bucket: DueBucket, locale: AppLocale): string {
  const copy = copyFor(locale);
  if (bucket === 'week') return copy.likelyThisWeek;
  if (bucket === 'backlog') return copy.somedayBacklog;
  return copy.needsContext;
}

function parseDueDateSuggestion(suggestion: AssistantSuggestion, task: Task): DueDateDecision | null {
  if (suggestion.kind !== 'task_due_date') return null;
  const taskId = suggestionTaskId(suggestion);
  if (taskId !== task.id) return null;
  const dueAt = typeof suggestion.payload.due_at === 'string' ? suggestion.payload.due_at : null;
  const noDeadline = suggestion.payload.no_deadline === true || dueAt === null;
  return {
    id: `due:${task.id}`,
    task,
    suggestionId: suggestion.id,
    bucket: bucketFromSuggestion(suggestion.payload.bucket, task),
    dueAt,
    noDeadline,
    reason: typeof suggestion.payload.reason === 'string' ? suggestion.payload.reason : suggestion.description ?? '',
  };
}

function buildDueDateDecisions(
  tasks: Task[],
  suggestions: AssistantSuggestion[],
  hiddenDecisionIds: Set<string>,
): DueDateDecision[] {
  return tasks
    .filter((task) => task.due_at === null && task.review_skips?.due_date !== true)
    .map((task) => {
      for (const suggestion of suggestions) {
        const parsed = parseDueDateSuggestion(suggestion, task);
        if (parsed) return parsed;
      }
      const backlog = task.project === 'Backlog';
      const shortTask = task.estimated_minutes !== null && task.estimated_minutes <= 30;
      return {
        id: `due:${task.id}`,
        task,
        bucket: backlog ? 'backlog' : shortTask ? 'week' : 'context',
        dueAt: backlog ? null : shortTask ? defaultWeekDueIso() : null,
        noDeadline: backlog,
        reason: backlog
          ? 'Backlog items can stay open without a deadline.'
          : shortTask
            ? 'Short enough to plan this week.'
            : 'No clear date yet; choose a date or leave it without a deadline.',
      } satisfies DueDateDecision;
    })
    .filter((decision) => !hiddenDecisionIds.has(decision.id));
}

function parseProjectSuggestion(suggestion: AssistantSuggestion, task: Task): ProjectDecision | null {
  if (suggestion.kind !== 'task_project') return null;
  const taskId = suggestionTaskId(suggestion);
  if (taskId !== task.id) return null;
  const projectName = typeof suggestion.payload.project === 'string' && suggestion.payload.project.trim()
    ? suggestion.payload.project.trim()
    : null;
  const projectId = typeof suggestion.payload.project_id === 'string' ? suggestion.payload.project_id : null;
  if (!projectName && !projectId) return null;
  return {
    id: `project:${task.id}`,
    task,
    suggestionId: suggestion.id,
    projectId,
    projectName: projectName ?? 'Project',
    confidence: typeof suggestion.payload.confidence === 'string' ? suggestion.payload.confidence : null,
    reason: typeof suggestion.payload.reason === 'string' ? suggestion.payload.reason : suggestion.description ?? '',
  };
}

function buildProjectDecisions(
  tasks: Task[],
  projects: Project[],
  suggestions: AssistantSuggestion[],
  hiddenDecisionIds: Set<string>,
): ProjectDecision[] {
  const backlog = projects.find((project) => project.system_key === 'backlog')
    ?? projects.find((project) => project.name === 'Backlog');
  return tasks
    .filter((task) => task.project_id === null && task.review_skips?.project !== true)
    .map((task) => {
      for (const suggestion of suggestions) {
        const parsed = parseProjectSuggestion(suggestion, task);
        if (parsed) return parsed;
      }
      return {
        id: `project:${task.id}`,
        task,
        projectId: backlog?.id ?? null,
        projectName: backlog?.name ?? 'Backlog',
        confidence: null,
        reason: 'Default place until a stronger project is clear.',
      } satisfies ProjectDecision;
    })
    .filter((decision) => !hiddenDecisionIds.has(decision.id));
}

function normalizeSearch(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function matchesTask(task: Task, query: string): boolean {
  const normalized = normalizeSearch(query);
  if (!normalized) return true;
  return [
    task.title,
    task.description ?? '',
    task.project ?? '',
    task.tags.join(' '),
  ].some((value) => value.toLocaleLowerCase().includes(normalized));
}

function matchesProject(project: Project, query: string): boolean {
  const normalized = normalizeSearch(query);
  if (!normalized) return true;
  return [
    project.name,
    project.health_reason,
    project.next_task?.title ?? '',
  ].some((value) => value.toLocaleLowerCase().includes(normalized));
}

function formatMinutes(minutes: number, locale: AppLocale): string {
  if (minutes < 60) return `${minutes} ${locale === 'en' ? 'min' : 'мин'}`;
  if (minutes % 60 === 0) return `${minutes / 60} ${locale === 'en' ? 'h' : 'ч'}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours} ${locale === 'en' ? 'h' : 'ч'} ${rest} ${locale === 'en' ? 'min' : 'мин'}`;
}

function startOfLocalDay(date: Date): Date {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function doneGroup(task: Task, now = new Date()): 'today' | 'yesterday' | 'earlier' {
  if (!task.completed_at) return 'earlier';
  const completed = startOfLocalDay(new Date(task.completed_at));
  const today = startOfLocalDay(now);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (completed.getTime() === today.getTime()) return 'today';
  if (completed.getTime() === yesterday.getTime()) return 'yesterday';
  return 'earlier';
}

function doneThisWeek(tasks: Task[]): Task[] {
  const now = new Date();
  const start = startOfLocalDay(now);
  const offset = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - offset);
  return tasks.filter((task) => task.completed_at && new Date(task.completed_at) >= start);
}

function healthLabel(project: Project, locale: AppLocale): string {
  const copy = copyFor(locale);
  if (project.health_status === 'needs_attention') return copy.needsAttention;
  if (project.health_status === 'moving') return copy.moving;
  if (project.health_status === 'light') return copy.light;
  return copy.quiet;
}

function healthTone(status: Project['health_status']): string {
  if (status === 'needs_attention') return 'bg-[rgba(217,122,43,0.18)] text-[#f0b35e]';
  if (status === 'moving') return 'bg-[rgba(46,185,118,0.16)] text-success';
  if (status === 'light') return 'bg-[var(--secondary-bg)] text-ink';
  return 'bg-[var(--secondary-bg)] text-hint';
}

function sectionTitle(status: Project['health_status'], locale: AppLocale): string {
  return healthLabel({ health_status: status } as Project, locale);
}

function ProjectRow({ project, locale, onOpen }: { project: Project; locale: AppLocale; onOpen: () => void }) {
  const copy = copyFor(locale);
  return (
    <button
      type="button"
      aria-label={`${copy.openProject} ${project.name}`}
      onClick={onOpen}
      className="card card-strong w-full p-4 text-left active:scale-[0.99]"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
          <span className="text-[16px] font-semibold">{project.name.slice(0, 1).toUpperCase()}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-[17px] font-semibold text-ink">{project.name}</p>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-semibold ${healthTone(project.health_status)}`}>
              {healthLabel(project, locale)}
            </span>
          </div>
          <p className="mt-1.5 truncate text-[13px] text-hint">
            {project.next_task ? `${copy.nextPrefix} ${project.next_task.title}` : copy.noNext}
          </p>
          <p className="mt-1 line-clamp-2 text-[12.5px] leading-snug text-hint">{project.health_reason}</p>
        </div>
        <ChevronRight size={18} className="mt-1 shrink-0 text-hint" />
      </div>
      {project.next_task && (
        <div className="mt-3 rounded-2xl border border-hairline bg-[var(--surface)] px-3.5 py-3">
          <p className="text-[11.5px] font-semibold uppercase tracking-wide text-accent-text">{copy.nextMove}</p>
          <div className="mt-1 flex items-center justify-between gap-3">
            <p className="min-w-0 truncate text-[15px] font-semibold text-ink">{project.next_task.title}</p>
            <span className="shrink-0 text-[12.5px] font-semibold text-accent-text">{copy.open}</span>
          </div>
        </div>
      )}
    </button>
  );
}

function ProjectList({
  projects,
  locale,
  onOpen,
}: {
  projects: Project[];
  locale: AppLocale;
  onOpen: (project: Project) => void;
}) {
  const copy = copyFor(locale);
  const groups: Project['health_status'][] = ['needs_attention', 'moving', 'light', 'quiet'];
  return (
    <div>
      <div className="mb-3 px-1">
        <h2 className="text-[19px] font-semibold tracking-[-0.01em] text-ink">{copy.projectHealth}</h2>
        <p className="mt-0.5 text-[13px] text-hint">{copy.projectSubtitle}</p>
      </div>
      <div className="space-y-4">
        {groups.map((status) => {
          const items = projects.filter((project) => project.health_status === status);
          if (items.length === 0) return null;
          return (
            <section key={status}>
              <div className="mb-2 flex items-center gap-2 px-1">
                {status === 'needs_attention' ? <AlertCircle size={16} className="text-[#f0b35e]" /> : <FolderKanban size={16} className="text-hint" />}
                <h3 className="text-[14px] font-semibold text-ink">{sectionTitle(status, locale)}</h3>
                <span className="tnum rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">{items.length}</span>
              </div>
              <div className="space-y-2.5">
                {items.map((project) => (
                  <ProjectRow key={project.id} project={project} locale={locale} onOpen={() => onOpen(project)} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ProjectDetail({
  project,
  tasks,
  locale,
  onBack,
  onOpenTask,
  renderTaskList,
}: {
  project: Project;
  tasks: Task[];
  locale: AppLocale;
  onBack: () => void;
  onOpenTask: (task: Task) => void;
  renderTaskList: (tasks: Task[]) => JSX.Element;
}) {
  const copy = copyFor(locale);
  const nextTask = project.next_task ?? tasks[0] ?? null;
  const later = nextTask ? tasks.filter((task) => task.id !== nextTask.id && task.status !== 'done') : tasks;
  const done = tasks.filter((task) => task.status === 'done').slice(0, 3);
  const openTasks = tasks.filter((task) => task.status !== 'done');
  const isBacklog = project.system_key === 'backlog';
  const cleanup = {
    estimates: openTasks.filter((task) => task.estimated_minutes === null && task.estimate_source !== 'skipped').length,
    dates: openTasks.filter((task) => task.due_at === null && task.review_skips?.due_date !== true).length,
    projects: openTasks.filter((task) => task.review_skips?.project !== true).length,
  };
  return (
    <div>
      <button type="button" onClick={onBack} className="mb-3 inline-flex h-10 items-center gap-2 rounded-full bg-[var(--secondary-bg)] px-3 text-[13px] font-semibold text-ink">
        <ArrowLeft size={16} />
        {copy.tabs.projects}
      </button>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[24px] font-semibold tracking-[-0.02em] text-ink">{project.name}</h2>
          <p className="mt-0.5 text-[13px] text-hint">{project.active_task_count} {locale === 'en' ? 'open tasks' : 'открытых задач'}</p>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-semibold ${healthTone(project.health_status)}`}>
          {healthLabel(project, locale)}
        </span>
      </div>

      {project.health_status === 'needs_attention' && (
        <div className="card card-strong mb-3 p-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-[#f0b35e]">{copy.whyAttention}</p>
          <p className="mt-1 text-[14px] text-ink">{project.health_reason}</p>
        </div>
      )}

      {isBacklog && (
        <div className="card card-strong mb-3 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
              <Sparkles size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold text-ink">{copy.backlogCleanup}</p>
              <p className="mt-1 text-[12.5px] leading-snug text-hint">{copy.backlogCleanupHint}</p>
              <div className="mt-3 grid grid-cols-3 gap-2">
                {[
                  [copy.estimate, cleanup.estimates],
                  [copy.planDates, cleanup.dates],
                  [copy.sortProjects, cleanup.projects],
                ].map(([label, count]) => (
                  <div key={String(label)} className="rounded-2xl border border-hairline bg-[var(--surface)] px-2.5 py-2">
                    <p className="tnum text-[15px] font-semibold text-ink">{count}</p>
                    <p className="mt-0.5 truncate text-[11.5px] text-hint">{label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {nextTask && (
        <div className="card card-strong mb-4 p-4">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-accent-text">{copy.nextMove}</p>
          <div className="mt-2 flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="break-words text-[17px] font-semibold leading-snug text-ink">{nextTask.title}</p>
              {nextTask.estimated_minutes && (
                <p className="tnum mt-1 text-[13px] text-hint">{nextTask.estimated_minutes} {locale === 'en' ? 'min' : 'мин'}</p>
              )}
            </div>
            <button type="button" onClick={() => onOpenTask(nextTask)} className="h-10 rounded-full bg-accent px-4 text-[13px] font-semibold text-white">
              {copy.open}
            </button>
          </div>
        </div>
      )}

      {nextTask && (
        <>
          <h3 className="mb-2 px-1 text-[14px] font-semibold text-ink">{copy.next}</h3>
          {renderTaskList([nextTask])}
        </>
      )}
      {later.length > 0 && (
        <>
          <h3 className="mb-2 mt-4 px-1 text-[14px] font-semibold text-ink">{copy.later}</h3>
          {renderTaskList(later)}
        </>
      )}
      {done.length > 0 && (
        <>
          <h3 className="mb-2 mt-4 px-1 text-[14px] font-semibold text-ink">{copy.doneRecently}</h3>
          {renderTaskList(done)}
        </>
      )}
    </div>
  );
}

function ReviewHub({
  suggestions,
  dueDateDecisions,
  projectDecisions,
  locale,
  onOpenReview,
}: {
  suggestions: EstimateSuggestion[];
  dueDateDecisions: DueDateDecision[];
  projectDecisions: ProjectDecision[];
  locale: AppLocale;
  onOpenReview: (mode: ReviewMode) => void;
}) {
  const copy = copyFor(locale);
  const categories = [
    { mode: 'estimates' as const, label: copy.estimates, hint: copy.estimatesHint, count: suggestions.length, action: copy.reviewEstimates },
    { mode: 'due_dates' as const, label: copy.dueDates, hint: copy.dueDatesHint, count: dueDateDecisions.length, action: copy.reviewDueDates },
    { mode: 'projects' as const, label: copy.projectSuggestions, hint: copy.projectSuggestionsHint, count: projectDecisions.length, action: copy.reviewProjects },
  ];
  return (
    <div>
      <div className="mb-3 px-1">
        <h2 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">{copy.reviewHub}</h2>
        <p className="mt-0.5 text-[13px] text-hint">{copy.reviewSubtitle}</p>
      </div>
      <div className="card card-strong overflow-hidden">
        {categories.map((category) => (
          <button
            key={category.mode}
            type="button"
            aria-label={category.action}
            onClick={() => onOpenReview(category.mode)}
            className="flex w-full items-center gap-3 border-t border-hairline px-4 py-3.5 text-left first:border-t-0 active:bg-[rgba(255,255,255,0.03)]"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
              <Sparkles size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[14.5px] font-semibold text-ink">{category.label}</p>
              <p className="truncate text-[12.5px] text-hint">{category.hint}</p>
            </div>
            <span className="tnum rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 text-[12px] font-semibold text-ink">{category.count}</span>
            <ChevronRight size={17} className="shrink-0 text-hint" />
          </button>
        ))}
      </div>
    </div>
  );
}

function NewTaskSheet({
  title,
  setTitle,
  locale,
  onClose,
  onSubmit,
  isPending,
}: {
  title: string;
  setTitle: (title: string) => void;
  locale: AppLocale;
  onClose: () => void;
  onSubmit: () => void;
  isPending: boolean;
}) {
  const copy = copyFor(locale);
  return (
    <Sheet open onClose={onClose} title={copy.newTask.replace('...', '')} closeLabel={copy.close}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-hint">{copy.taskTitle}</span>
          <input
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            aria-label={copy.taskTitle}
            className="h-12 w-full rounded-2xl border border-hairline bg-[var(--surface)] px-3.5 text-[15px] text-ink outline-none focus:border-[var(--accent-border)]"
          />
        </label>
        <button
          type="submit"
          disabled={isPending || title.trim().length === 0}
          className="mt-5 h-11 w-full rounded-2xl bg-accent text-[14px] font-semibold text-white disabled:opacity-45"
        >
          {copy.create}
        </button>
      </form>
    </Sheet>
  );
}

function EstimateReviewSheet({
  tasks,
  suggestions,
  locale,
  onClose,
  onAcceptEstimate,
  onEditEstimate,
}: {
  tasks: Task[];
  suggestions: EstimateSuggestion[];
  locale: AppLocale;
  onClose: () => void;
  onAcceptEstimate: (id: string) => void;
  onEditEstimate: (task: Task, suggestion: EstimateSuggestion) => void;
}) {
  const copy = copyFor(locale);
  const rows = suggestions
    .map((suggestion) => ({ suggestion, task: tasks.find((task) => task.id === suggestion.taskId) }))
    .filter((row): row is { suggestion: EstimateSuggestion; task: Task } => row.task !== undefined);

  return (
    <Sheet open onClose={onClose} title={copy.estimateSuggestions} closeLabel={copy.close}>
      {rows.length === 0 ? (
        <EmptyState icon={Sparkles} title={copy.noEstimateSuggestions} className="border-0 bg-transparent shadow-none" />
      ) : (
        <div className="space-y-2.5">
          {rows.map(({ suggestion, task }) => (
            <div key={suggestion.id} className="rounded-2xl border border-hairline bg-[var(--surface)] p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-words text-[15px] font-semibold leading-snug text-ink">{task.title}</p>
                  <p className="mt-1 truncate text-[12.5px] text-hint">
                    {[task.project, suggestion.reason].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <span className="tnum shrink-0 rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[12px] font-semibold text-accent-text">
                  {formatMinutes(suggestion.minutes, locale)}
                </span>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  aria-label={`${locale === 'en' ? 'Accept estimate for' : 'Принять оценку для'} ${task.title}`}
                  onClick={() => onAcceptEstimate(suggestion.id)}
                  className="h-9 flex-1 rounded-full bg-accent text-[12.5px] font-semibold text-white"
                >
                  {locale === 'en' ? 'Accept' : 'Принять'}
                </button>
                <button
                  type="button"
                  aria-label={`${copy.change} ${locale === 'en' ? 'estimate for' : 'оценку для'} ${task.title}`}
                  onClick={() => onEditEstimate(task, suggestion)}
                  className="h-9 flex-1 rounded-full bg-[var(--secondary-bg)] text-[12.5px] font-semibold text-ink"
                >
                  {copy.change}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Sheet>
  );
}

function PlanDatesSheet({
  decisions,
  locale,
  onClose,
  onAccept,
  onChange,
  onNoDeadline,
}: {
  decisions: DueDateDecision[];
  locale: AppLocale;
  onClose: () => void;
  onAccept: (decision: DueDateDecision) => void;
  onChange: (decision: DueDateDecision) => void;
  onNoDeadline: (decision: DueDateDecision) => void;
}) {
  const copy = copyFor(locale);
  const groups: DueBucket[] = ['week', 'backlog', 'context'];
  return (
    <Sheet open onClose={onClose} title={copy.dueDates} closeLabel={copy.close}>
      {decisions.length === 0 ? (
        <EmptyState icon={CheckCircle2} title={copy.emptyReview[0]} hint={copy.emptyReview[1]} className="border-0 bg-transparent shadow-none" />
      ) : (
        <div className="space-y-4">
          {groups.map((bucket) => {
            const items = decisions.filter((decision) => decision.bucket === bucket);
            if (items.length === 0) return null;
            return (
              <section key={bucket}>
                <div className="mb-2 flex items-center gap-2 px-1">
                  <CalendarDays size={15} className="text-accent-text" />
                  <h3 className="text-[13px] font-semibold text-ink">{dueBucketLabel(bucket, locale)}</h3>
                  <span className="tnum rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">{items.length}</span>
                </div>
                <div className="space-y-2.5">
                  {items.map((decision) => (
                    <div key={decision.id} className="rounded-2xl border border-hairline bg-[var(--surface)] p-3.5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="break-words text-[15px] font-semibold leading-snug text-ink">{decision.task.title}</p>
                          <p className="mt-1 text-[12.5px] text-hint">{decision.reason}</p>
                        </div>
                        <span className="tnum shrink-0 rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[12px] font-semibold text-accent-text">
                          {formatDateDecisionLabel(decision.dueAt, locale)}
                        </span>
                      </div>
                      <p className="mt-3 text-[11.5px] font-semibold uppercase tracking-wide text-hint">{copy.suggestedDate}</p>
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          aria-label={`${locale === 'en' ? 'Accept date for' : 'Принять дату для'} ${decision.task.title}`}
                          onClick={() => onAccept(decision)}
                          className="h-9 flex-1 rounded-full bg-accent text-[12.5px] font-semibold text-white"
                        >
                          {locale === 'en' ? 'Accept' : 'Принять'}
                        </button>
                        <button
                          type="button"
                          aria-label={`${copy.change} ${locale === 'en' ? 'date for' : 'дату для'} ${decision.task.title}`}
                          onClick={() => onChange(decision)}
                          className="h-9 flex-1 rounded-full bg-[var(--secondary-bg)] text-[12.5px] font-semibold text-ink"
                        >
                          {copy.change}
                        </button>
                        <button
                          type="button"
                          aria-label={`${copy.noDeadline} ${locale === 'en' ? 'for' : 'для'} ${decision.task.title}`}
                          onClick={() => onNoDeadline(decision)}
                          className="h-9 flex-1 rounded-full bg-[var(--secondary-bg)] text-[12.5px] font-semibold text-ink"
                        >
                          {copy.noDeadline}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </Sheet>
  );
}

function SortProjectsSheet({
  decisions,
  locale,
  onClose,
  onAccept,
  onChange,
  onKeepUnassigned,
}: {
  decisions: ProjectDecision[];
  locale: AppLocale;
  onClose: () => void;
  onAccept: (decision: ProjectDecision) => void;
  onChange: (decision: ProjectDecision) => void;
  onKeepUnassigned: (decision: ProjectDecision) => void;
}) {
  const copy = copyFor(locale);
  return (
    <Sheet open onClose={onClose} title={copy.projectSuggestions} closeLabel={copy.close}>
      {decisions.length === 0 ? (
        <EmptyState icon={CheckCircle2} title={copy.emptyReview[0]} hint={copy.emptyReview[1]} className="border-0 bg-transparent shadow-none" />
      ) : (
        <div className="space-y-2.5">
          {decisions.map((decision) => (
            <div key={decision.id} className="rounded-2xl border border-hairline bg-[var(--surface)] p-3.5">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
                  <FolderInput size={16} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-words text-[15px] font-semibold leading-snug text-ink">{decision.task.title}</p>
                  <p className="mt-1 text-[12.5px] text-hint">{decision.reason}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-[11.5px] font-semibold uppercase tracking-wide text-hint">{copy.suggestedProject}</span>
                    <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-1 text-[12px] font-semibold text-accent-text">{decision.projectName}</span>
                    {decision.confidence && (
                      <span className="rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 text-[12px] font-medium text-hint">{decision.confidence}</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  aria-label={`${locale === 'en' ? 'Accept project for' : 'Принять проект для'} ${decision.task.title}`}
                  onClick={() => onAccept(decision)}
                  className="h-9 flex-1 rounded-full bg-accent text-[12.5px] font-semibold text-white"
                >
                  {locale === 'en' ? 'Accept' : 'Принять'}
                </button>
                <button
                  type="button"
                  aria-label={`${copy.change} ${locale === 'en' ? 'project for' : 'проект для'} ${decision.task.title}`}
                  onClick={() => onChange(decision)}
                  className="h-9 flex-1 rounded-full bg-[var(--secondary-bg)] text-[12.5px] font-semibold text-ink"
                >
                  {copy.change}
                </button>
                <button
                  type="button"
                  aria-label={`${locale === 'en' ? 'Keep' : 'Оставить'} ${decision.task.title} ${locale === 'en' ? 'unassigned' : 'без проекта'}`}
                  onClick={() => onKeepUnassigned(decision)}
                  className="h-9 flex-1 rounded-full bg-[var(--secondary-bg)] text-[12.5px] font-semibold text-ink"
                >
                  {copy.keepUnassigned}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Sheet>
  );
}

function DateChangeSheet({
  decision,
  locale,
  onClose,
  onSave,
  onNoDeadline,
}: {
  decision: DueDateDecision;
  locale: AppLocale;
  onClose: () => void;
  onSave: (decision: DueDateDecision, dueAt: string) => void;
  onNoDeadline: (decision: DueDateDecision) => void;
}) {
  const copy = copyFor(locale);
  const toInput = (value: string | null) => {
    const date = value ? new Date(value) : new Date(defaultWeekDueIso());
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };
  const [value, setValue] = useState(toInput(decision.dueAt));
  return (
    <Sheet open onClose={onClose} title={copy.chooseDate} closeLabel={copy.close}>
      <p className="text-[15px] font-semibold text-ink">{decision.task.title}</p>
      <p className="mt-1 text-[13px] text-hint">{decision.reason}</p>
      <input
        type="datetime-local"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="mt-4 h-11 w-full rounded-xl border border-hairline bg-[var(--surface)] px-3.5 text-[15px] text-ink outline-none focus:border-[var(--accent-border)]"
      />
      <div className="mt-5 space-y-2">
        <button type="button" onClick={() => onSave(decision, new Date(value).toISOString())} className="h-11 w-full rounded-2xl bg-accent text-[14px] font-semibold text-white">
          {copy.save}
        </button>
        <button type="button" onClick={() => onNoDeadline(decision)} className="h-11 w-full rounded-2xl bg-[var(--secondary-bg)] text-[14px] font-semibold text-ink">
          {copy.noDeadline}
        </button>
      </div>
    </Sheet>
  );
}

function ProjectChangeSheet({
  decision,
  projects,
  locale,
  onClose,
  onSave,
}: {
  decision: ProjectDecision;
  projects: Project[];
  locale: AppLocale;
  onClose: () => void;
  onSave: (decision: ProjectDecision, project: { id?: string | null; name: string }) => void;
}) {
  const copy = copyFor(locale);
  const [custom, setCustom] = useState(decision.projectName);
  return (
    <Sheet open onClose={onClose} title={copy.chooseProject} closeLabel={copy.close}>
      <p className="text-[15px] font-semibold text-ink">{decision.task.title}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {projects.map((project) => (
          <button
            key={project.id}
            type="button"
            onClick={() => onSave(decision, { id: project.id, name: project.name })}
            className="min-h-[36px] rounded-full border border-hairline bg-[var(--secondary-bg)] px-3 text-[13px] font-semibold text-ink"
          >
            {project.name}
          </button>
        ))}
      </div>
      <label className="mt-4 block">
        <span className="mb-1.5 block text-[12.5px] font-medium text-hint">{copy.custom}</span>
        <input
          value={custom}
          onChange={(event) => setCustom(event.target.value)}
          className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface)] px-3.5 text-[15px] text-ink outline-none focus:border-[var(--accent-border)]"
        />
      </label>
      <button
        type="button"
        disabled={custom.trim().length === 0}
        onClick={() => onSave(decision, { name: custom.trim() })}
        className="mt-5 h-11 w-full rounded-2xl bg-accent text-[14px] font-semibold text-white disabled:opacity-45"
      >
        {copy.save}
      </button>
    </Sheet>
  );
}

function DoneView({
  tasks,
  locale,
  onReopen,
  onOpenTask,
}: {
  tasks: Task[];
  locale: AppLocale;
  onReopen: (id: string) => void;
  onOpenTask: (task: Task) => void;
}) {
  const copy = copyFor(locale);
  const weekTasks = doneThisWeek(tasks);
  const clearedMinutes = weekTasks.reduce((sum, task) => sum + (task.estimated_minutes ?? 0), 0);
  const groups: { id: 'today' | 'yesterday' | 'earlier'; label: string; items: Task[] }[] = [
    { id: 'today', label: copy.tabs.today, items: tasks.filter((task) => doneGroup(task) === 'today') },
    { id: 'yesterday', label: copy.yesterday, items: tasks.filter((task) => doneGroup(task) === 'yesterday') },
    { id: 'earlier', label: copy.earlier, items: tasks.filter((task) => doneGroup(task) === 'earlier') },
  ];
  return (
    <div>
      <div className="card card-strong mb-4 p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-accent-text">
            <CheckCircle2 size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-[19px] font-semibold tracking-[-0.01em] text-ink">{copy.workDone}</h2>
            <p className="mt-0.5 text-[13px] text-hint">{copy.completedThisWeek}: {weekTasks.length}</p>
          </div>
          <div className="rounded-2xl bg-[var(--secondary-bg)] px-3 py-2 text-right">
            <p className="tnum text-[15px] font-semibold text-ink">{formatMinutes(clearedMinutes, locale)}</p>
            <p className="text-[11.5px] text-hint">{copy.clearedTime}</p>
          </div>
        </div>
      </div>

      {groups.map((group) => {
        if (group.items.length === 0) return null;
        return (
          <section key={group.id} className="mb-4">
            <div className="mb-2 flex items-center gap-2 px-1">
              <h3 className="text-[14px] font-semibold text-ink">{group.label}</h3>
              <span className="tnum rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">{group.items.length}</span>
            </div>
            <AnimatePresence initial={false}>
              {group.items.map((task) => (
                <motion.div
                  key={task.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.98 }}
                  transition={{ duration: 0.22, ease: 'easeOut' }}
                  className="mb-2.5"
                >
                  <TaskCard
                    task={task}
                    onComplete={() => undefined}
                    onReopen={onReopen}
                    onSnooze={() => undefined}
                    onEdit={onOpenTask}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </section>
        );
      })}
    </div>
  );
}

function EstimateSheet({
  task,
  suggestion,
  locale,
  onClose,
}: {
  task: Task;
  suggestion: EstimateSuggestion;
  locale: AppLocale;
  onClose: () => void;
}) {
  const copy = copyFor(locale);
  const [value, setValue] = useState(suggestion.minutes);
  const patchTask = usePatchTask();
  const decide = useDecideAssistantSuggestion();
  const { show } = useToast();
  const chips = [5, 15, 30, 45, 60, 120];
  const save = () => {
    patchTask.mutate(
      { id: task.id, input: { estimated_minutes: value, estimate_source: 'user' } },
      {
        onSuccess: () => {
          decide.mutate({ id: suggestion.id, accept: false });
          show(copy.estimateSaved, 'success');
          onClose();
        },
        onError: () => show(copy.saveFailed, 'error'),
      },
    );
  };
  const doNotEstimate = () => {
    patchTask.mutate(
      { id: task.id, input: { estimated_minutes: null, estimate_source: 'skipped' } },
      {
        onSuccess: () => {
          decide.mutate({ id: suggestion.id, accept: false });
          show(copy.estimateSaved, 'success');
          onClose();
        },
        onError: () => show(copy.saveFailed, 'error'),
      },
    );
  };
  return (
    <Sheet open onClose={onClose} title={copy.estimateTask} closeLabel={copy.close}>
      <p className="text-[15px] font-semibold text-ink">{task.title}</p>
      <p className="mt-1 text-[13px] text-hint">{suggestion.reason ?? `${copy.suggested}: ${suggestion.minutes} min`}</p>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {chips.map((minutes) => (
          <button
            key={minutes}
            type="button"
            aria-pressed={value === minutes}
            onClick={() => setValue(minutes)}
            className={`h-10 rounded-2xl border text-[13px] font-semibold ${
              value === minutes
                ? 'border-[var(--accent-border)] bg-accent text-white'
                : 'border-hairline bg-[var(--secondary-bg)] text-ink'
            }`}
          >
            {minutes < 60 ? `${minutes}m` : `${minutes / 60}h`}
          </button>
        ))}
      </div>
      <label className="mt-4 block">
        <span className="mb-1.5 block text-[12.5px] font-medium text-hint">{copy.custom}</span>
        <input
          type="number"
          min={1}
          max={1440}
          value={value}
          onChange={(event) => setValue(Math.max(1, Math.min(1440, Number(event.target.value) || 1)))}
          className="tnum h-11 w-full rounded-xl border border-hairline bg-[var(--surface)] px-3.5 text-[15px] text-ink outline-none focus:border-[var(--accent-border)]"
        />
      </label>
      <div className="mt-5 space-y-2">
        <button type="button" onClick={save} className="h-11 w-full rounded-2xl bg-accent text-[14px] font-semibold text-white">
          {copy.save}
        </button>
        <button type="button" onClick={doNotEstimate} className="h-11 w-full rounded-2xl bg-[var(--secondary-bg)] text-[14px] font-semibold text-ink">
          {copy.doNotEstimate}
        </button>
        <button type="button" onClick={onClose} className="h-11 w-full rounded-2xl text-[14px] font-semibold text-hint">
          {copy.close}
        </button>
      </div>
    </Sheet>
  );
}

export default function TasksPage() {
  const locale = useAppLocale();
  const copy = copyFor(locale);
  const tabs: { id: TaskView; label: string }[] = [
    { id: 'today', label: copy.tabs.today },
    { id: 'projects', label: copy.tabs.projects },
    { id: 'review', label: copy.tabs.review },
    { id: 'done', label: copy.tabs.done },
  ];
  const [view, setView] = useState<TaskView>('today');
  const [title, setTitle] = useState('');
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [project, setProject] = useState<string | null>(null);
  const [reviewMode, setReviewMode] = useState<ReviewMode | null>(null);
  const [hiddenSuggestionIds, setHiddenSuggestionIds] = useState<Set<string>>(() => new Set());
  const [hiddenReviewDecisionIds, setHiddenReviewDecisionIds] = useState<Set<string>>(() => new Set());
  const [hiddenDoneTaskIds, setHiddenDoneTaskIds] = useState<Set<string>>(() => new Set());
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [estimateEditing, setEstimateEditing] = useState<{ task: Task; suggestion: EstimateSuggestion } | null>(null);
  const [dateChanging, setDateChanging] = useState<DueDateDecision | null>(null);
  const [projectChanging, setProjectChanging] = useState<ProjectDecision | null>(null);
  const { show } = useToast();

  const taskFilter = viewToTaskFilter(view);
  const tasksQuery = useTasks(taskFilter);
  const projectTasksQuery = useProjectTasks(selectedProject?.id ?? null);
  const projectsQuery = useProjects();
  const suggestionsQuery = useAssistantSuggestions();
  const createTask = useCreateTask(taskFilter);
  const completeTask = useCompleteTask(taskFilter);
  const snoozeTask = useSnoozeTask(taskFilter);
  const patchTask = usePatchTask();
  const decideSuggestion = useDecideAssistantSuggestion();

  const suggestions = suggestionsQuery.data?.items ?? [];
  const estimateSuggestions = useMemo(
    () => suggestions
      .map(parseEstimateSuggestion)
      .filter((item): item is EstimateSuggestion => item !== null && !hiddenSuggestionIds.has(item.id)),
    [hiddenSuggestionIds, suggestions],
  );
  const visibleSuggestions = useMemo(
    () => suggestions.filter((suggestion) => !hiddenSuggestionIds.has(suggestion.id)),
    [hiddenSuggestionIds, suggestions],
  );
  const estimatesByTask = useMemo(() => estimateMap(visibleSuggestions), [visibleSuggestions]);
  const items = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data]);
  const projectItems = projectTasksQuery.data?.items ?? [];
  const searchedItems = useMemo(
    () => items.filter((task) => matchesTask(task, query)),
    [items, query],
  );
  const visible = useMemo(
    () => (project ? searchedItems.filter((task) => task.project === project) : searchedItems),
    [searchedItems, project],
  );
  const visibleDone = useMemo(
    () => visible.filter((task) => !hiddenDoneTaskIds.has(task.id)),
    [hiddenDoneTaskIds, visible],
  );
  const searchedProjectItems = useMemo(
    () => projectItems.filter((task) => matchesTask(task, query)),
    [projectItems, query],
  );
  const projectNames = useMemo(() => {
    const set = new Set<string>();
    for (const task of items) if (task.project) set.add(task.project);
    return [...set].sort((a, b) => a.localeCompare(b, locale === 'ru' ? 'ru' : 'en'));
  }, [items, locale]);
  const projects = useMemo(
    () => (projectsQuery.data?.items ?? []).filter((item) => matchesProject(item, query)),
    [projectsQuery.data, query],
  );
  const allProjects = projectsQuery.data?.items ?? [];
  const dueDateDecisions = useMemo(
    () => buildDueDateDecisions(visible, visibleSuggestions, hiddenReviewDecisionIds),
    [hiddenReviewDecisionIds, visible, visibleSuggestions],
  );
  const projectDecisions = useMemo(
    () => buildProjectDecisions(visible, allProjects, visibleSuggestions, hiddenReviewDecisionIds),
    [allProjects, hiddenReviewDecisionIds, visible, visibleSuggestions],
  );

  const submit = () => {
    const trimmed = title.trim();
    if (!trimmed || createTask.isPending) return;
    haptic('light');
    setTitle('');
    const hashMatch = /#([\wа-яА-ЯёЁ-]+)\s*$/u.exec(trimmed);
    const cleanTitle = hashMatch ? trimmed.slice(0, hashMatch.index).trim() : trimmed;
    createTask.mutate(
      { title: cleanTitle || trimmed, ...(hashMatch ? { project: hashMatch[1] } : {}) },
      {
        onSuccess: () => {
          setCreating(false);
        },
        onError: () => {
          show(copy.createFailed, 'error');
          setTitle(trimmed);
        },
      },
    );
  };

  const handleComplete = (id: string) => completeTask.mutate(id, { onError: () => show(copy.completeFailed, 'error') });
  const handleSnooze = (id: string, preset: SnoozePreset) =>
    snoozeTask.mutate(
      { id, input: { preset } },
      {
        onSuccess: () => show(copy.snoozed, 'success'),
        onError: () => show(copy.snoozeFailed, 'error'),
      },
    );
  const acceptEstimate = (id: string) =>
    {
      setHiddenSuggestionIds((current) => new Set(current).add(id));
      decideSuggestion.mutate(
        { id, accept: true },
        {
          onSuccess: () => show(copy.estimateSaved, 'success'),
          onError: () => {
            setHiddenSuggestionIds((current) => {
              const next = new Set(current);
              next.delete(id);
              return next;
            });
            show(copy.saveFailed, 'error');
          },
        },
      );
    };
  const editEstimate = (task: Task, suggestion: { id: string; minutes: number; reason?: string | null }) =>
    setEstimateEditing({ task, suggestion: { ...suggestion, taskId: task.id } });

  const hideDecision = (id: string) => setHiddenReviewDecisionIds((current) => new Set(current).add(id));
  const restoreDecision = (id: string) => setHiddenReviewDecisionIds((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });
  const hideSuggestion = (id: string) => setHiddenSuggestionIds((current) => new Set(current).add(id));
  const restoreSuggestion = (id: string) => setHiddenSuggestionIds((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });

  const dismissLinkedSuggestion = (suggestionId?: string) => {
    if (!suggestionId) return;
    hideSuggestion(suggestionId);
    decideSuggestion.mutate(
      { id: suggestionId, accept: false },
      { onError: () => restoreSuggestion(suggestionId) },
    );
  };

  const acceptDueDate = (decision: DueDateDecision) => {
    haptic('light');
    hideDecision(decision.id);
    if (decision.suggestionId) {
      hideSuggestion(decision.suggestionId);
      decideSuggestion.mutate(
        { id: decision.suggestionId, accept: true },
        {
          onSuccess: () => show(copy.estimateSaved, 'success'),
          onError: () => {
            restoreDecision(decision.id);
            restoreSuggestion(decision.suggestionId as string);
            show(copy.saveFailed, 'error');
          },
        },
      );
      return;
    }
    if (decision.dueAt) {
      patchTask.mutate(
        { id: decision.task.id, input: { due_at: decision.dueAt, review_skips: { due_date: false } } },
        {
          onSuccess: () => show(copy.estimateSaved, 'success'),
          onError: () => {
            restoreDecision(decision.id);
            show(copy.saveFailed, 'error');
          },
        },
      );
      return;
    }
    patchTask.mutate(
      { id: decision.task.id, input: { review_skips: { due_date: true } } },
      {
        onSuccess: () => show(copy.estimateSaved, 'success'),
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const markNoDeadline = (decision: DueDateDecision) => {
    haptic('light');
    hideDecision(decision.id);
    patchTask.mutate(
      { id: decision.task.id, input: { review_skips: { due_date: true } } },
      {
        onSuccess: () => {
          dismissLinkedSuggestion(decision.suggestionId);
          setDateChanging(null);
          show(copy.estimateSaved, 'success');
        },
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const saveDueDate = (decision: DueDateDecision, dueAt: string) => {
    haptic('light');
    hideDecision(decision.id);
    patchTask.mutate(
      { id: decision.task.id, input: { due_at: dueAt, review_skips: { due_date: false } } },
      {
        onSuccess: () => {
          dismissLinkedSuggestion(decision.suggestionId);
          setDateChanging(null);
          show(copy.estimateSaved, 'success');
        },
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const acceptProjectDecision = (decision: ProjectDecision) => {
    haptic('light');
    hideDecision(decision.id);
    if (decision.suggestionId) {
      hideSuggestion(decision.suggestionId);
      decideSuggestion.mutate(
        { id: decision.suggestionId, accept: true },
        {
          onSuccess: () => show(copy.estimateSaved, 'success'),
          onError: () => {
            restoreDecision(decision.id);
            restoreSuggestion(decision.suggestionId as string);
            show(copy.saveFailed, 'error');
          },
        },
      );
      return;
    }
    patchTask.mutate(
      {
        id: decision.task.id,
        input: decision.projectId
          ? { project_id: decision.projectId, review_skips: { project: false } }
          : { project: decision.projectName, review_skips: { project: false } },
      },
      {
        onSuccess: () => show(copy.estimateSaved, 'success'),
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const keepUnassigned = (decision: ProjectDecision) => {
    haptic('light');
    hideDecision(decision.id);
    patchTask.mutate(
      { id: decision.task.id, input: { review_skips: { project: true } } },
      {
        onSuccess: () => {
          dismissLinkedSuggestion(decision.suggestionId);
          show(copy.estimateSaved, 'success');
        },
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const saveProjectDecision = (decision: ProjectDecision, target: { id?: string | null; name: string }) => {
    haptic('light');
    hideDecision(decision.id);
    patchTask.mutate(
      {
        id: decision.task.id,
        input: target.id
          ? { project_id: target.id, review_skips: { project: false } }
          : { project: target.name, review_skips: { project: false } },
      },
      {
        onSuccess: () => {
          dismissLinkedSuggestion(decision.suggestionId);
          setProjectChanging(null);
          show(copy.estimateSaved, 'success');
        },
        onError: () => {
          restoreDecision(decision.id);
          show(copy.saveFailed, 'error');
        },
      },
    );
  };

  const reopenTask = (id: string) => {
    haptic('light');
    setHiddenDoneTaskIds((current) => new Set(current).add(id));
    patchTask.mutate(
      { id, input: { status: 'active' } },
      {
        onSuccess: () => show(copy.reopened, 'success'),
        onError: () => {
          setHiddenDoneTaskIds((current) => {
            const next = new Set(current);
            next.delete(id);
            return next;
          });
          show(copy.reopenFailed, 'error');
        },
      },
    );
  };

  const renderTaskList = (tasks: Task[]) => (
    <AnimatePresence initial={false}>
      {tasks.map((task) => (
        <motion.div
          key={task.id}
          layout
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="mb-2.5"
        >
          <TaskCard
            task={task}
            onComplete={handleComplete}
            onSnooze={handleSnooze}
            onEdit={setEditing}
            estimateSuggestion={estimatesByTask.get(task.id)}
            onAcceptEstimate={acceptEstimate}
            onEditEstimate={editEstimate}
          />
        </motion.div>
      ))}
    </AnimatePresence>
  );

  const loading = tasksQuery.isPending || (view === 'projects' && projectsQuery.isPending);
  const errored = tasksQuery.isError || (view === 'projects' && projectsQuery.isError);
  const empty = {
    today: copy.emptyToday,
    projects: copy.emptyProjects,
    review: copy.emptyReview,
    done: copy.emptyDone,
  } satisfies Record<TaskView, readonly string[]>;

  return (
    <Stagger>
      <Rise>
        <div className="card card-strong flex h-12 items-center gap-2.5 px-4">
          <Search size={18} className="shrink-0 text-accent-text" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={copy.searchTasks}
            aria-label={copy.searchTasks}
            className="h-full min-w-0 flex-1 bg-transparent text-[14.5px] text-ink outline-none"
          />
        </div>
      </Rise>

      <Rise>
        <div className="mt-4 grid grid-cols-4 rounded-2xl border border-hairline bg-[var(--secondary-bg)] p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setView(tab.id);
                setSelectedProject(null);
                setReviewMode(null);
              }}
              className={`h-9 rounded-xl text-[13px] font-semibold transition-colors ${
                view === tab.id ? 'bg-[var(--surface-strong)] text-accent-text shadow-sm' : 'text-hint'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </Rise>

      {view !== 'projects' && view !== 'review' && projectNames.length > 0 && (
        <Rise>
          <div className="no-scrollbar -mx-4 mt-2 flex gap-2 overflow-x-auto px-4 py-1">
            {projectNames.map((name) => (
              <Chip key={name} label={name} active={project === name} onClick={() => setProject(project === name ? null : name)} />
            ))}
          </div>
        </Rise>
      )}

      <Rise className="mt-4">
        {loading ? (
          <SkeletonList count={4} lines={1} />
        ) : errored ? (
          <ErrorState message={copy.loadError} onRetry={() => {
            void tasksQuery.refetch();
            void projectsQuery.refetch();
          }} />
        ) : view === 'projects' && selectedProject ? (
          <ProjectDetail
            project={selectedProject}
            tasks={searchedProjectItems}
            locale={locale}
            onBack={() => setSelectedProject(null)}
            onOpenTask={setEditing}
            renderTaskList={renderTaskList}
          />
        ) : view === 'projects' ? (
          projects.length === 0 ? (
            <EmptyState icon={CheckCircle2} title={empty.projects[0]} hint={empty.projects[1]} />
          ) : (
            <ProjectList projects={projects} locale={locale} onOpen={setSelectedProject} />
          )
        ) : view === 'review' ? (
          <ReviewHub
            suggestions={estimateSuggestions}
            dueDateDecisions={dueDateDecisions}
            projectDecisions={projectDecisions}
            locale={locale}
            onOpenReview={setReviewMode}
          />
        ) : view === 'done' ? (
          visibleDone.length === 0 ? (
            <EmptyState icon={CheckCircle2} title={empty.done[0]} hint={empty.done[1]} />
          ) : (
            <DoneView tasks={visibleDone} locale={locale} onReopen={reopenTask} onOpenTask={setEditing} />
          )
        ) : visible.length === 0 ? (
          <EmptyState icon={CheckCircle2} title={empty[view][0]} hint={empty[view][1]} />
        ) : (
          renderTaskList(visible)
        )}
      </Rise>

      <button
        type="button"
        aria-label={copy.addTask}
        onClick={() => {
          haptic('light');
          setCreating(true);
        }}
        className="fixed z-[55] flex h-14 w-14 items-center justify-center rounded-full bg-accent text-white shadow-card active:scale-95"
        style={{
          right: 'max(20px, calc((100vw - 860px) / 2 + 20px))',
          bottom: 'calc(env(safe-area-inset-bottom) + 96px)',
        }}
      >
        <Plus size={24} strokeWidth={2.2} />
      </button>

      <TaskEditSheet task={editing} onClose={() => setEditing(null)} />
      {creating && (
        <NewTaskSheet
          title={title}
          setTitle={setTitle}
          locale={locale}
          onClose={() => setCreating(false)}
          onSubmit={submit}
          isPending={createTask.isPending}
        />
      )}
      {reviewMode === 'estimates' && (
        <EstimateReviewSheet
          tasks={visible}
          suggestions={estimateSuggestions}
          locale={locale}
          onClose={() => setReviewMode(null)}
          onAcceptEstimate={acceptEstimate}
          onEditEstimate={editEstimate}
        />
      )}
      {reviewMode === 'due_dates' && (
        <PlanDatesSheet
          decisions={dueDateDecisions}
          locale={locale}
          onClose={() => setReviewMode(null)}
          onAccept={acceptDueDate}
          onChange={setDateChanging}
          onNoDeadline={markNoDeadline}
        />
      )}
      {reviewMode === 'projects' && (
        <SortProjectsSheet
          decisions={projectDecisions}
          locale={locale}
          onClose={() => setReviewMode(null)}
          onAccept={acceptProjectDecision}
          onChange={setProjectChanging}
          onKeepUnassigned={keepUnassigned}
        />
      )}
      {dateChanging && (
        <DateChangeSheet
          decision={dateChanging}
          locale={locale}
          onClose={() => setDateChanging(null)}
          onSave={saveDueDate}
          onNoDeadline={markNoDeadline}
        />
      )}
      {projectChanging && (
        <ProjectChangeSheet
          decision={projectChanging}
          projects={allProjects}
          locale={locale}
          onClose={() => setProjectChanging(null)}
          onSave={saveProjectDecision}
        />
      )}
      {estimateEditing && (
        <EstimateSheet
          task={estimateEditing.task}
          suggestion={estimateEditing.suggestion}
          locale={locale}
          onClose={() => setEstimateEditing(null)}
        />
      )}
    </Stagger>
  );
}
