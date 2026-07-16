import { useEffect, useMemo, useRef, useState } from 'react';
import type { PatchTaskInput, Project, Task, TaskBucket, TaskPriority } from '../../api/types';
import { usePatchTask } from '../../api/hooks';
import { dateTimeInputParts, localPartsToDate } from '../../lib/focusTime';
import { useAppLocale } from '../../lib/useAppLocale';
import { useTimeDisplay } from '../../lib/useTimeDisplay';
import { Button } from '../ui/Button';
import { FieldLabel, Input, Select, Textarea } from '../ui/Field';
import { Sheet } from '../ui/Sheet';
import { useToast } from '../ui/Toast';

const COPY = {
  en: {
    task: 'Task details',
    title: 'Title',
    note: 'Note',
    notePlaceholder: 'Details, links...',
    location: 'List',
    inbox: 'Inbox',
    thisWeek: 'This week',
    later: 'Later',
    priority: 'Priority',
    project: 'Project',
    noProject: 'No project',
    unavailableProject: 'current',
    estimate: 'Estimate (minutes)',
    estimatePlaceholder: '30',
    hardDeadline: 'Hard deadline',
    remind: 'Remind at this time',
    save: 'Save changes',
    close: 'Close',
    saved: 'Task updated',
    saveFailed: 'Could not save task',
    undoCompletion: 'Undo completion',
    reopened: 'Task reopened',
    reopenFailed: 'Could not reopen task',
    priorities: { low: 'Low', medium: 'Medium', high: 'High', urgent: 'Urgent' },
  },
  ru: {
    task: 'Детали задачи',
    title: 'Название',
    note: 'Заметка',
    notePlaceholder: 'Детали, ссылки...',
    location: 'Список',
    inbox: 'Входящие',
    thisWeek: 'На этой неделе',
    later: 'Позже',
    priority: 'Приоритет',
    project: 'Проект',
    noProject: 'Без проекта',
    unavailableProject: 'текущий',
    estimate: 'Оценка (минуты)',
    estimatePlaceholder: '30',
    hardDeadline: 'Жёсткий срок',
    remind: 'Напомнить в это время',
    save: 'Сохранить',
    close: 'Закрыть',
    saved: 'Задача обновлена',
    saveFailed: 'Не удалось сохранить задачу',
    undoCompletion: 'Вернуть задачу',
    reopened: 'Задача возвращена',
    reopenFailed: 'Не удалось вернуть задачу',
    priorities: { low: 'Низкий', medium: 'Средний', high: 'Высокий', urgent: 'Срочно' },
  },
};

function toLocalInput(ts: string | null, timezone?: string | null): string {
  if (!ts) return '';
  const parts = dateTimeInputParts(new Date(ts), timezone);
  return `${parts.date}T${parts.time}`;
}

function defaultThisWeekPlan(): string {
  return new Date().toISOString();
}

function openBucket(task: Task): Exclude<TaskBucket, 'done'> {
  if (task.bucket === 'inbox' || task.bucket === 'this_week' || task.bucket === 'later') return task.bucket;
  return task.planned_for ? 'this_week' : 'later';
}

export function TaskEditSheet({
  task,
  projects,
  onClose,
}: {
  task: Task | null;
  projects: Project[];
  onClose: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [bucket, setBucket] = useState<Exclude<TaskBucket, 'done'>>('inbox');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [projectValue, setProjectValue] = useState('');
  const [estimate, setEstimate] = useState('');
  const [due, setDue] = useState('');
  const [remind, setRemind] = useState(true);
  const dueTouched = useRef(false);
  const patchTask = usePatchTask();
  const { show } = useToast();
  const locale = useAppLocale();
  const timeDisplay = useTimeDisplay();
  const copy = COPY[locale];

  useEffect(() => {
    if (!task) return;
    dueTouched.current = false;
    setTitle(task.title);
    setDescription(task.description ?? '');
    setBucket(openBucket(task));
    setPriority(task.priority);
    setProjectValue(task.project_id ?? (task.project ? `legacy:${task.project}` : ''));
    setEstimate(task.estimated_minutes === null ? '' : String(task.estimated_minutes));
    setDue(toLocalInput(task.due_at));
    setRemind(task.reminder_at !== null);
  }, [task]);

  useEffect(() => {
    if (!task || dueTouched.current) return;
    setDue(toLocalInput(task.due_at, timeDisplay.timezone));
  }, [task, timeDisplay.timezone]);

  const projectOptions = useMemo(() => {
    const options = [{ value: '', label: copy.noProject }];
    for (const project of projects.filter((item) => item.status === 'active')) {
      options.push({ value: project.id, label: project.name });
    }
    if (task?.project_id && !projects.some((project) => project.id === task.project_id)) {
      options.push({ value: task.project_id, label: `${task.project ?? copy.project} (${copy.unavailableProject})` });
    }
    if (task?.project && !task.project_id) options.push({ value: `legacy:${task.project}`, label: task.project });
    return options;
  }, [copy.noProject, copy.project, copy.unavailableProject, projects, task]);

  if (task === null) return null;

  const save = () => {
    const [dueDate = '', dueTime = ''] = due.split('T');
    const parsedDue = due ? localPartsToDate(dueDate, dueTime, timeDisplay.timezone) : null;
    if (parsedDue && Number.isNaN(parsedDue.getTime())) {
      show(copy.saveFailed, 'error');
      return;
    }
    const dueIso = parsedDue?.toISOString() ?? null;
    const parsedEstimate = estimate.trim() === '' ? null : Number.parseInt(estimate, 10);
    const normalizedEstimate = parsedEstimate === null || Number.isNaN(parsedEstimate)
      ? null
      : Math.max(1, Math.min(1440, parsedEstimate));
    const project = projects.find((item) => item.id === projectValue);
    const projectInput: PatchTaskInput = project
      ? { project_id: project.id }
      : projectValue === task.project_id
        ? {}
        : projectValue.startsWith('legacy:')
          ? { project: projectValue.slice(7) }
          : { project_id: null, project: null };
    const input: PatchTaskInput = {
      title: title.trim() || task.title,
      description: description.trim() || null,
      priority,
      estimated_minutes: normalizedEstimate,
      due_at: dueIso,
      reminder_at: remind && dueIso ? dueIso : null,
      ...projectInput,
    };

    if (task.status !== 'done') {
      if (bucket === 'inbox') Object.assign(input, { status: 'inbox', planned_for: null });
      if (bucket === 'this_week') Object.assign(input, {
        status: 'active',
        planned_for: task.bucket === 'this_week' && task.planned_for ? task.planned_for : defaultThisWeekPlan(),
      });
      if (bucket === 'later') Object.assign(input, {
        status: 'active',
        planned_for: task.bucket === 'later' ? task.planned_for : null,
      });
    }

    patchTask.mutate(
      { id: task.id, input },
      {
        onSuccess: () => {
          show(copy.saved, 'success');
          onClose();
        },
        onError: () => show(copy.saveFailed, 'error'),
      },
    );
  };

  const undoCompletion = () => {
    patchTask.mutate(
      { id: task.id, input: { status: 'active' } },
      {
        onSuccess: () => {
          show(copy.reopened, 'success');
          onClose();
        },
        onError: () => show(copy.reopenFailed, 'error'),
      },
    );
  };

  const bucketOptions = [
    { value: 'inbox', label: copy.inbox },
    { value: 'this_week', label: copy.thisWeek },
    { value: 'later', label: copy.later },
  ];
  const priorityOptions = [
    { value: 'low', label: copy.priorities.low },
    { value: 'medium', label: copy.priorities.medium },
    { value: 'high', label: copy.priorities.high },
    { value: 'urgent', label: copy.priorities.urgent },
  ];

  return (
    <Sheet open onClose={onClose} title={copy.task} closeLabel={copy.close}>
      <label className="block">
        <FieldLabel>{copy.title}</FieldLabel>
        <Input value={title} onChange={setTitle} autoFocus />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.note}</FieldLabel>
        <Textarea value={description} onChange={setDescription} rows={3} placeholder={copy.notePlaceholder} />
      </label>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {task.status !== 'done' && (
          <label className="block">
            <FieldLabel>{copy.location}</FieldLabel>
            <Select value={bucket} onChange={(value) => setBucket(value as Exclude<TaskBucket, 'done'>)} options={bucketOptions} />
          </label>
        )}
        <label className="block">
          <FieldLabel>{copy.project}</FieldLabel>
          <Select value={projectValue} onChange={setProjectValue} options={projectOptions} />
        </label>
        <label className="block">
          <FieldLabel>{copy.estimate}</FieldLabel>
          <Input value={estimate} onChange={setEstimate} type="number" placeholder={copy.estimatePlaceholder} />
        </label>
        <label className="block">
          <FieldLabel>{copy.priority}</FieldLabel>
          <Select value={priority} onChange={(value) => setPriority(value as TaskPriority)} options={priorityOptions} />
        </label>
      </div>

      <label className="mt-4 block">
        <FieldLabel>{copy.hardDeadline}</FieldLabel>
        <input
          type="datetime-local"
          value={due}
          onChange={(event) => {
            dueTouched.current = true;
            setDue(event.target.value);
          }}
          className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
        />
      </label>
      {due !== '' && (
        <label className="mt-2.5 flex min-h-11 items-center gap-2 text-[13px] text-ink">
          <input
            type="checkbox"
            checked={remind}
            onChange={(event) => setRemind(event.target.checked)}
            className="h-4 w-4 accent-[var(--accent)]"
          />
          {copy.remind}
        </label>
      )}

      <Button fullWidth className="mt-5" busy={patchTask.isPending} onClick={save}>
        {copy.save}
      </Button>
      {task.status === 'done' && (
        <Button fullWidth variant="secondary" className="mt-2" busy={patchTask.isPending} onClick={undoCompletion}>
          {copy.undoCompletion}
        </Button>
      )}
    </Sheet>
  );
}
