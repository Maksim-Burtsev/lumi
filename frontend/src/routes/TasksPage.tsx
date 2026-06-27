import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, Plus } from 'lucide-react';
import { useCompleteTask, useCreateTask, useSnoozeTask, useTasks } from '../api/hooks';
import type { SnoozePreset, Task, TaskFilter } from '../api/types';
import { TaskCard } from '../components/task/TaskCard';
import { TaskEditSheet } from '../components/task/TaskEditSheet';
import { Chip } from '../components/ui/Chip';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { haptic } from '../telegram/webapp';
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';

const FILTERS: { id: TaskFilter; label: Record<AppLocale, string> }[] = [
  { id: 'today', label: { en: 'Today', ru: 'Сегодня' } },
  { id: 'upcoming', label: { en: 'Upcoming', ru: 'Предстоящие' } },
  { id: 'inbox', label: { en: 'Inbox', ru: 'Инбокс' } },
  { id: 'done', label: { en: 'Done', ru: 'Готово' } },
];

const EMPTY_HINTS: Record<AppLocale, Record<TaskFilter, { title: string; hint: string }>> = {
  en: {
    today: {
      title: 'No active tasks yet',
      hint: 'Write to Lumi in chat: "Remind me tomorrow..." and the task will appear here.',
    },
    upcoming: {
      title: 'Nothing upcoming yet',
      hint: 'Tasks with future dates will collect in this list.',
    },
    inbox: {
      title: 'No active tasks yet',
      hint: 'Write to Lumi in chat: "Remind me tomorrow..." and the task will appear here.',
    },
    done: {
      title: 'Completed tasks will appear here',
      hint: 'Mark tasks with the circle on the left. Lumi will keep the history.',
    },
    all: {
      title: 'No tasks yet',
      hint: 'Write to Lumi in chat: "Remind me tomorrow..." and the task will appear here.',
    },
  },
  ru: {
    today: {
      title: 'На сегодня всё чисто',
      hint: 'Напиши Lumi в чате: «Напомни завтра…» — и задача появится здесь.',
    },
    upcoming: {
      title: 'Впереди пока пусто',
      hint: 'Задачи с датами на будущее соберутся в этом списке.',
    },
    inbox: {
      title: 'Пока нет активных задач',
      hint: 'Напиши Lumi в чате: «Напомни завтра…» — и задача появится здесь.',
    },
    done: {
      title: 'Здесь появятся выполненные задачи',
      hint: 'Отмечай задачи кружком слева — Lumi сохранит историю.',
    },
    all: {
      title: 'Пока нет задач',
      hint: 'Напиши Lumi в чате: «Напомни завтра…» — и задача появится здесь.',
    },
  },
};

export default function TasksPage() {
  const [filter, setFilter] = useState<TaskFilter>('today');
  const [title, setTitle] = useState('');
  const [project, setProject] = useState<string | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const { show } = useToast();
  const locale = useAppLocale();
  const copy = locale === 'en'
    ? {
        createFailed: 'Could not create task',
        loadFailed: 'Could not load tasks.',
        noProject: 'No project',
        completeFailed: 'Could not complete',
        snoozed: 'Task snoozed',
        snoozeFailed: 'Could not snooze',
        placeholder: 'New task... (Enter to create)',
        inputLabel: 'New task',
        overdue: 'Overdue',
        today: 'Today',
      }
    : {
        createFailed: 'Не удалось создать задачу',
        loadFailed: 'Не удалось загрузить задачи.',
        noProject: 'Без проекта',
        completeFailed: 'Не удалось выполнить',
        snoozed: 'Задача отложена',
        snoozeFailed: 'Не удалось отложить',
        placeholder: 'Новая задача… (Enter — создать)',
        inputLabel: 'Новая задача',
        overdue: 'Просроченные',
        today: 'Сегодня',
      };

  const tasksQuery = useTasks(filter);
  const createTask = useCreateTask(filter);
  const completeTask = useCompleteTask(filter);
  const snoozeTask = useSnoozeTask(filter);

  const submit = () => {
    const trimmed = title.trim();
    if (!trimmed || createTask.isPending) return;
    haptic('light');
    setTitle('');
    // «Название #проект» — привязка к проекту прямо из быстрого ввода
    const hashMatch = /#([\wа-яА-ЯёЁ-]+)\s*$/u.exec(trimmed);
    const cleanTitle = hashMatch ? trimmed.slice(0, hashMatch.index).trim() : trimmed;
    createTask.mutate(
      { title: cleanTitle || trimmed, ...(hashMatch ? { project: hashMatch[1] } : {}) },
      {
        onError: () => {
          show(copy.createFailed, 'error');
          setTitle(trimmed);
        },
      },
    );
  };

  const items = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data]);

  const projects = useMemo(() => {
    const set = new Set<string>();
    for (const task of items) if (task.project) set.add(task.project);
    return [...set];
  }, [items]);

  const visible = useMemo(
    () => (project ? items.filter((t) => t.project === project) : items),
    [items, project],
  );

  const { overdue, rest } = useMemo(() => {
    if (filter !== 'today') return { overdue: [] as Task[], rest: visible };
    const now = Date.now();
    const over: Task[] = [];
    const others: Task[] = [];
    for (const task of visible) {
      if (task.status !== 'done' && task.due_at !== null && new Date(task.due_at).getTime() < now) over.push(task);
      else others.push(task);
    }
    return { overdue: over, rest: others };
  }, [visible, filter]);

  const projectGroups = useMemo(() => {
    if (project !== null) return null; // фильтр по одному проекту — плоский список
    const map = new Map<string, Task[]>();
    for (const task of rest) {
      const key = task.project ?? '';
      const list = map.get(key) ?? [];
      list.push(task);
      map.set(key, list);
    }
    if (map.size <= 1) return null; // одна группа — заголовки не нужны
    const head = ['личное', 'работа'];
    const keys = [...map.keys()].sort((a, b) => {
      if (a === '') return 1;
      if (b === '') return -1;
      const ai = head.indexOf(a.toLowerCase());
      const bi = head.indexOf(b.toLowerCase());
      if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      return a.localeCompare(b, 'ru');
    });
    return keys.map((key) => ({ name: key || copy.noProject, tasks: map.get(key)! }));
  }, [rest, project, copy.noProject]);

  const handleComplete = (id: string) => completeTask.mutate(id, { onError: () => show(copy.completeFailed, 'error') });
  const handleSnooze = (id: string, preset: SnoozePreset) =>
    snoozeTask.mutate(
      { id, input: { preset } },
      {
        onSuccess: () => show(copy.snoozed, 'success'),
        onError: () => show(copy.snoozeFailed, 'error'),
      },
    );

  const renderList = (tasks: Task[]) => (
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
          <TaskCard task={task} onComplete={handleComplete} onSnooze={handleSnooze} onEdit={setEditing} />
        </motion.div>
      ))}
    </AnimatePresence>
  );

  return (
    <Stagger>
      {/* Quick add */}
      <Rise>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="card card-strong flex h-12 items-center gap-2.5 px-4"
        >
          <Plus size={18} className="shrink-0 text-hint" />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={copy.placeholder}
            aria-label={copy.inputLabel}
            className="h-full min-w-0 flex-1 bg-transparent text-[14.5px] text-ink outline-none"
          />
        </form>
      </Rise>

      {/* Filters */}
      <Rise>
        <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 py-1">
          {FILTERS.map((f) => (
            <Chip key={f.id} label={f.label[locale]} active={filter === f.id} onClick={() => setFilter(f.id)} />
          ))}
        </div>
      </Rise>

      {/* Project chips */}
      {projects.length > 0 && (
        <Rise>
          <div className="no-scrollbar -mx-4 mt-1 flex gap-2 overflow-x-auto px-4 py-1">
            {projects.map((p) => (
              <Chip key={p} label={p} active={project === p} onClick={() => setProject(project === p ? null : p)} />
            ))}
          </div>
        </Rise>
      )}

      <Rise className="mt-3">
        {tasksQuery.isPending ? (
          <SkeletonList count={4} lines={1} />
        ) : tasksQuery.isError ? (
          <ErrorState message={copy.loadFailed} onRetry={() => void tasksQuery.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState icon={CheckCircle2} title={EMPTY_HINTS[locale][filter].title} hint={EMPTY_HINTS[locale][filter].hint} />
        ) : (
          <div>
            {overdue.length > 0 && (
              <>
                <p className="mb-2 mt-1 px-1 text-[12.5px] font-semibold uppercase tracking-wide text-danger">
                  {copy.overdue}
                </p>
                {renderList(overdue)}
                {rest.length > 0 && (
                  <p className="mb-2 mt-4 px-1 text-[12.5px] font-semibold uppercase tracking-wide text-hint">
                    {copy.today}
                  </p>
                )}
              </>
            )}
            {projectGroups ? (
              projectGroups.map((group) => (
                <div key={group.name}>
                  <p className="mb-2 mt-4 px-1 text-[12.5px] font-semibold uppercase tracking-wide text-hint first:mt-1">
                    {group.name}
                    <span className="tnum ml-1.5 font-normal normal-case text-hint/70">{group.tasks.length}</span>
                  </p>
                  {renderList(group.tasks)}
                </div>
              ))
            ) : (
              renderList(rest)
            )}
          </div>
        )}
      </Rise>
      <TaskEditSheet task={editing} onClose={() => setEditing(null)} />
    </Stagger>
  );
}
