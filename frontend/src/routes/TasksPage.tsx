import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Archive,
  CalendarRange,
  CheckCircle2,
  Inbox,
  Layers3,
  Loader2,
  Plus,
  RotateCcw,
  Search,
  SearchX,
} from 'lucide-react';
import {
  useCompleteTask,
  useCreateTask,
  useInfiniteTasks,
  usePatchTask,
  useProjects,
} from '../api/hooks';
import type { Project, Task } from '../api/types';
import { TaskCard } from '../components/task/TaskCard';
import { TaskEditSheet } from '../components/task/TaskEditSheet';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { useAppLocale } from '../lib/useAppLocale';
import { haptic } from '../telegram/webapp';

type TaskView = 'open' | 'done';

const PAGE_SIZE = 20;

const COPY = {
  en: {
    quickAdd: 'Add a task to Inbox',
    add: 'Add task',
    createFailed: 'Could not create task',
    search: 'Search tasks',
    allProjects: 'All projects',
    filterProject: 'Filter by project',
    open: 'Open',
    done: 'Done',
    inbox: 'Inbox',
    thisWeek: 'This week',
    later: 'Later',
    doneArchive: 'Done archive',
    noTasks: 'No open tasks',
    noTasksHint: 'Capture the next thing above. It will land in Inbox.',
    noDone: 'No completed tasks yet',
    noDoneHint: 'Completed tasks stay here and can be reopened.',
    noMatches: 'No matching tasks',
    noMatchesHint: 'Try another search or project filter.',
    sectionEmpty: 'Nothing here',
    loadFailed: 'Could not load this list.',
    retry: 'Retry',
    loadMore: 'Load more',
    estimated: 'estimated',
    completeFailed: 'Could not complete task',
    reopened: 'Task reopened',
    reopenFailed: 'Could not reopen task',
    completed: 'Task completed',
    undo: 'Undo',
  },
  ru: {
    quickAdd: 'Добавить задачу во Входящие',
    add: 'Добавить задачу',
    createFailed: 'Не удалось создать задачу',
    search: 'Поиск задач',
    allProjects: 'Все проекты',
    filterProject: 'Фильтр по проекту',
    open: 'Открытые',
    done: 'Готово',
    inbox: 'Входящие',
    thisWeek: 'На этой неделе',
    later: 'Позже',
    doneArchive: 'Архив готовых',
    noTasks: 'Открытых задач нет',
    noTasksHint: 'Добавь следующий шаг сверху. Он попадёт во Входящие.',
    noDone: 'Выполненных задач пока нет',
    noDoneHint: 'Готовые задачи остаются здесь, их можно вернуть.',
    noMatches: 'Ничего не найдено',
    noMatchesHint: 'Попробуй другой запрос или проект.',
    sectionEmpty: 'Здесь пусто',
    loadFailed: 'Не удалось загрузить список.',
    retry: 'Повторить',
    loadMore: 'Загрузить ещё',
    estimated: 'оценка',
    completeFailed: 'Не удалось выполнить задачу',
    reopened: 'Задача возвращена',
    reopenFailed: 'Не удалось вернуть задачу',
    completed: 'Задача выполнена',
    undo: 'Вернуть',
  },
};

function useDebouncedValue(value: string, delay = 250): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timeout);
  }, [delay, value]);
  return debounced;
}

function flattenPages(data: { pages: { items: Task[] }[] } | undefined): Task[] {
  return data?.pages.flatMap((page) => page.items) ?? [];
}

function capacityLabel(minutes: number, locale: 'en' | 'ru', incomplete: boolean): string {
  const suffix = incomplete ? '+' : '';
  if (minutes < 60) return `${minutes}${suffix} ${locale === 'ru' ? 'мин' : 'min'}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const value = rest === 0
    ? `${hours} ${locale === 'ru' ? 'ч' : 'h'}`
    : `${hours} ${locale === 'ru' ? 'ч' : 'h'} ${rest} ${locale === 'ru' ? 'мин' : 'min'}`;
  return `${value}${suffix}`;
}

interface TaskSectionProps {
  title: string;
  icon: typeof Inbox;
  tasks: Task[];
  meta?: string;
  pending: boolean;
  error: boolean;
  fetchingMore: boolean;
  hasMore: boolean;
  emptyLabel: string;
  loadFailed: string;
  retryLabel: string;
  loadMoreLabel: string;
  onRetry: () => void;
  onLoadMore: () => void;
  onComplete: (task: Task) => void;
  onReopen?: (task: Task) => void;
  onEdit: (task: Task) => void;
}

function TaskSection({
  title,
  icon: Icon,
  tasks,
  meta,
  pending,
  error,
  fetchingMore,
  hasMore,
  emptyLabel,
  loadFailed,
  retryLabel,
  loadMoreLabel,
  onRetry,
  onLoadMore,
  onComplete,
  onReopen,
  onEdit,
}: TaskSectionProps) {
  return (
    <section aria-labelledby={`task-section-${title.replace(/\s+/g, '-').toLowerCase()}`}>
      <header className="mb-2 flex min-h-8 items-center gap-2 px-1">
        <Icon size={16} strokeWidth={1.9} className="text-accent-text" />
        <h2 id={`task-section-${title.replace(/\s+/g, '-').toLowerCase()}`} className="text-[13px] font-semibold text-ink">
          {title}
        </h2>
        {!pending && !error && <span className="tnum text-[12px] text-hint">{tasks.length}</span>}
        {meta && <span className="tnum ml-auto text-[12px] font-medium text-hint">{meta}</span>}
      </header>

      <div className="card card-strong overflow-hidden">
        {pending ? (
          <div className="divide-y divide-hairline px-4">
            {[0, 1].map((item) => (
              <div key={item} className="flex min-h-[64px] items-center gap-3">
                <Skeleton className="h-6 w-6 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1">
                  <Skeleton className="h-4 w-3/5" />
                  <Skeleton className="mt-2 h-3 w-2/5" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="flex min-h-[96px] flex-col items-center justify-center gap-2 px-4 py-4 text-center">
            <p className="text-[13px] text-hint">{loadFailed}</p>
            <Button size="sm" variant="ghost" onClick={onRetry} icon={<RotateCcw size={14} />}>
              {retryLabel}
            </Button>
          </div>
        ) : tasks.length === 0 ? (
          <p className="px-4 py-5 text-center text-[13px] text-hint">{emptyLabel}</p>
        ) : (
          <>
            <AnimatePresence initial={false}>
              {tasks.map((task, index) => (
                <motion.div
                  key={task.id}
                  layout
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ duration: 0.18, ease: 'easeOut' }}
                  className={index === 0 ? '' : 'border-t border-hairline'}
                >
                  <TaskCard task={task} onComplete={onComplete} onReopen={onReopen} onEdit={onEdit} />
                </motion.div>
              ))}
            </AnimatePresence>
            {hasMore && (
              <div className="border-t border-hairline p-2.5 text-center">
                <Button size="sm" variant="secondary" busy={fetchingMore} onClick={onLoadMore}>
                  {loadMoreLabel}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export default function TasksPage() {
  const locale = useAppLocale();
  const copy = COPY[locale];
  const [view, setView] = useState<TaskView>('open');
  const [title, setTitle] = useState('');
  const [search, setSearch] = useState('');
  const [projectId, setProjectId] = useState('');
  const [editing, setEditing] = useState<Task | null>(null);
  const [hiddenOpenTaskIds, setHiddenOpenTaskIds] = useState<Set<string>>(() => new Set());
  const [hiddenDoneTaskIds, setHiddenDoneTaskIds] = useState<Set<string>>(() => new Set());
  const [lastCompleted, setLastCompleted] = useState<Task | null>(null);
  const quickAddRef = useRef<HTMLInputElement>(null);
  const debouncedSearch = useDebouncedValue(search.trim());
  const { show } = useToast();

  const commonQuery = {
    q: debouncedSearch || undefined,
    project_id: projectId || undefined,
    limit: PAGE_SIZE,
  };
  const inboxQuery = useInfiniteTasks({ ...commonQuery, filter: 'inbox' }, view === 'open');
  const weekQuery = useInfiniteTasks({ ...commonQuery, filter: 'this_week' }, view === 'open');
  const laterQuery = useInfiniteTasks({ ...commonQuery, filter: 'later' }, view === 'open');
  const doneQuery = useInfiniteTasks({ ...commonQuery, filter: 'done' }, view === 'done');
  const projectsQuery = useProjects();
  const createTask = useCreateTask('inbox');
  const completeTask = useCompleteTask('all');
  const patchTask = usePatchTask();

  const projects = useMemo(
    () => (projectsQuery.data?.items ?? []).filter((project) => project.status === 'active'),
    [projectsQuery.data],
  );
  const inboxItems = useMemo(() => flattenPages(inboxQuery.data), [inboxQuery.data]);
  const weekItems = useMemo(() => flattenPages(weekQuery.data), [weekQuery.data]);
  const laterItems = useMemo(() => flattenPages(laterQuery.data), [laterQuery.data]);
  const doneItems = useMemo(() => flattenPages(doneQuery.data), [doneQuery.data]);
  const inboxTasks = inboxItems.filter((task) => !hiddenOpenTaskIds.has(task.id));
  const weekTasks = weekItems.filter((task) => !hiddenOpenTaskIds.has(task.id));
  const laterTasks = laterItems.filter((task) => !hiddenOpenTaskIds.has(task.id));
  const doneTasks = doneItems.filter((task) => !hiddenDoneTaskIds.has(task.id));
  const weekMinutes = weekTasks.reduce((total, task) => total + (task.estimated_minutes ?? 0), 0);
  const weekCapacity = `${capacityLabel(weekMinutes, locale, weekQuery.hasNextPage)} ${copy.estimated}`;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || createTask.isPending) return;
    haptic('light');
    createTask.mutate(
      { title: trimmed, ...(projectId ? { project_id: projectId } : {}) },
      {
        onSuccess: () => {
          setTitle('');
          quickAddRef.current?.focus();
        },
        onError: () => show(copy.createFailed, 'error'),
      },
    );
  };

  const hideOpenTask = (id: string) => setHiddenOpenTaskIds((current) => new Set(current).add(id));
  const restoreOpenTask = (id: string) => setHiddenOpenTaskIds((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });
  const hideDoneTask = (id: string) => setHiddenDoneTaskIds((current) => new Set(current).add(id));
  const restoreDoneTask = (id: string) => setHiddenDoneTaskIds((current) => {
    const next = new Set(current);
    next.delete(id);
    return next;
  });

  const handleComplete = (task: Task) => {
    hideOpenTask(task.id);
    void (async () => {
      try {
        await completeTask.mutateAsync(task.id);
      } catch {
        restoreOpenTask(task.id);
        show(copy.completeFailed, 'error');
        return;
      }
      restoreDoneTask(task.id);
      setLastCompleted(task);
      try {
        await Promise.all([inboxQuery.refetch(), weekQuery.refetch(), laterQuery.refetch()]);
      } catch {
        // The section-level error state handles failed refetches.
      } finally {
        restoreOpenTask(task.id);
      }
    })();
  };

  const handleReopen = (task: Task) => {
    hideDoneTask(task.id);
    void (async () => {
      try {
        await patchTask.mutateAsync({ id: task.id, input: { status: 'active' } });
      } catch {
        restoreDoneTask(task.id);
        show(copy.reopenFailed, 'error');
        return;
      }
      restoreOpenTask(task.id);
      show(copy.reopened, 'success');
      try {
        await doneQuery.refetch();
      } catch {
        // The section-level error state handles failed refetches.
      } finally {
        restoreDoneTask(task.id);
      }
    })();
  };

  const undoLastCompletion = () => {
    if (!lastCompleted) return;
    const task = lastCompleted;
    void (async () => {
      try {
        await patchTask.mutateAsync({ id: task.id, input: { status: 'active' } });
      } catch {
        show(copy.reopenFailed, 'error');
        return;
      }
      restoreOpenTask(task.id);
      hideDoneTask(task.id);
      setLastCompleted(null);
      show(copy.reopened, 'success');
      try {
        await doneQuery.refetch();
      } catch {
        // The section-level error state handles failed refetches.
      } finally {
        restoreDoneTask(task.id);
      }
    })();
  };

  const openQueries = [inboxQuery, weekQuery, laterQuery];
  const openPending = openQueries.some((query) => query.isPending);
  const openError = openQueries.some((query) => query.isError);
  const openCount = inboxTasks.length + weekTasks.length + laterTasks.length;
  const activeQueryEmpty = view === 'open'
    ? !openPending && !openError && openCount === 0
    : !doneQuery.isPending && !doneQuery.isError && doneTasks.length === 0;
  const filtered = Boolean(debouncedSearch || projectId);

  const sectionCommon = {
    emptyLabel: copy.sectionEmpty,
    loadFailed: copy.loadFailed,
    retryLabel: copy.retry,
    loadMoreLabel: copy.loadMore,
    onComplete: handleComplete,
    onEdit: setEditing,
  };

  return (
    <Stagger className="pb-4">
      <Rise>
        <form onSubmit={submit} className="card card-strong flex min-h-14 items-center gap-2 p-1.5 pl-4">
          <Plus size={18} className="shrink-0 text-accent-text" strokeWidth={2} />
          <input
            ref={quickAddRef}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={copy.quickAdd}
            aria-label={copy.quickAdd}
            className="h-11 min-w-0 flex-1 bg-transparent text-[14.5px] text-ink outline-none"
          />
          <button
            type="submit"
            aria-label={copy.add}
            disabled={title.trim() === '' || createTask.isPending}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent text-[var(--accent-foreground)] transition-opacity disabled:opacity-40"
          >
            {createTask.isPending ? <Loader2 size={18} className="animate-spin" /> : <Plus size={19} />}
          </button>
        </form>
      </Rise>

      <Rise className="mt-3">
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_190px]">
          <label className="card flex h-11 items-center gap-2.5 px-3.5 focus-within:border-[var(--accent-border)]">
            <Search size={17} className="shrink-0 text-hint" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={copy.search}
              aria-label={copy.search}
              className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none"
            />
          </label>
          <label className="card relative flex h-11 items-center px-3.5">
            <select
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              aria-label={copy.filterProject}
              className="h-full w-full appearance-none bg-transparent pr-7 text-[13.5px] text-ink outline-none"
            >
              <option value="">{copy.allProjects}</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
            <Layers3 size={15} className="pointer-events-none absolute right-3.5 text-hint" />
          </label>
        </div>
      </Rise>

      <Rise className="mt-3">
        <div className="inline-grid grid-cols-2 rounded-2xl border border-hairline bg-[var(--secondary-bg)] p-1">
          {(['open', 'done'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => setView(option)}
              className={`h-11 min-w-[104px] rounded-xl px-4 text-[13px] font-semibold transition-colors ${
                view === option ? 'bg-[var(--surface-strong)] text-accent-text shadow-sm' : 'text-hint'
              }`}
            >
              {option === 'open' ? copy.open : copy.done}
            </button>
          ))}
        </div>
      </Rise>

      <AnimatePresence initial={false}>
        {lastCompleted && (
          <motion.div
            role="status"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="mt-3 flex min-h-12 items-center gap-3 rounded-2xl border border-[var(--accent-border)] bg-[var(--accent-soft)] px-4"
          >
            <CheckCircle2 size={17} className="shrink-0 text-accent-text" />
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{copy.completed}: {lastCompleted.title}</span>
            <button
              type="button"
              onClick={undoLastCompletion}
              disabled={patchTask.isPending}
              className="min-h-11 shrink-0 text-[13px] font-semibold text-accent-text disabled:opacity-50"
            >
              {copy.undo}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <Rise className="mt-5">
        {activeQueryEmpty ? (
          <EmptyState
            icon={filtered ? SearchX : CheckCircle2}
            title={filtered ? copy.noMatches : view === 'open' ? copy.noTasks : copy.noDone}
            hint={filtered ? copy.noMatchesHint : view === 'open' ? copy.noTasksHint : copy.noDoneHint}
          />
        ) : view === 'open' ? (
          <div className="space-y-5">
            <TaskSection
              {...sectionCommon}
              title={copy.inbox}
              icon={Inbox}
              tasks={inboxTasks}
              pending={inboxQuery.isPending}
              error={inboxQuery.isError}
              fetchingMore={inboxQuery.isFetchingNextPage}
              hasMore={inboxQuery.hasNextPage}
              onRetry={() => void inboxQuery.refetch()}
              onLoadMore={() => void inboxQuery.fetchNextPage()}
            />
            <TaskSection
              {...sectionCommon}
              title={copy.thisWeek}
              icon={CalendarRange}
              tasks={weekTasks}
              meta={weekCapacity}
              pending={weekQuery.isPending}
              error={weekQuery.isError}
              fetchingMore={weekQuery.isFetchingNextPage}
              hasMore={weekQuery.hasNextPage}
              onRetry={() => void weekQuery.refetch()}
              onLoadMore={() => void weekQuery.fetchNextPage()}
            />
            <TaskSection
              {...sectionCommon}
              title={copy.later}
              icon={Layers3}
              tasks={laterTasks}
              pending={laterQuery.isPending}
              error={laterQuery.isError}
              fetchingMore={laterQuery.isFetchingNextPage}
              hasMore={laterQuery.hasNextPage}
              onRetry={() => void laterQuery.refetch()}
              onLoadMore={() => void laterQuery.fetchNextPage()}
            />
          </div>
        ) : (
          <TaskSection
            {...sectionCommon}
            title={copy.doneArchive}
            icon={Archive}
            tasks={doneTasks}
            pending={doneQuery.isPending}
            error={doneQuery.isError}
            fetchingMore={doneQuery.isFetchingNextPage}
            hasMore={doneQuery.hasNextPage}
            onRetry={() => void doneQuery.refetch()}
            onLoadMore={() => void doneQuery.fetchNextPage()}
            onReopen={handleReopen}
          />
        )}
      </Rise>

      <TaskEditSheet task={editing} projects={projects as Project[]} onClose={() => setEditing(null)} />
    </Stagger>
  );
}
