import { useEffect, useState } from 'react';
import type { Task, TaskPriority } from '../../api/types';
import { usePatchTask } from '../../api/hooks';
import { useAppLocale } from '../../lib/useAppLocale';
import { Button } from '../ui/Button';
import { FieldLabel, Input, Select, Textarea } from '../ui/Field';
import { Sheet } from '../ui/Sheet';
import { useToast } from '../ui/Toast';

/** Full task editor: title, priority, project, due date with quick chips. */

const COPY = {
  en: {
    task: 'Task',
    title: 'Title',
    note: 'Note',
    notePlaceholder: 'Details, links...',
    priority: 'Priority',
    project: 'Project',
    due: 'Due date',
    remind: 'Remind at this time',
    save: 'Save',
    close: 'Close',
    saved: 'Saved',
    saveFailed: 'Could not save',
    undoCompletion: 'Undo completion',
    reopened: 'Task reopened',
    reopenFailed: 'Could not reopen task',
    todayEvening: 'Today 18:00',
    tomorrowMorning: 'Tomorrow 09:00',
    saturday: 'Saturday',
    noDue: 'No due date',
    priorities: { low: 'Low', medium: 'Medium', high: 'High', urgent: 'Urgent' },
  },
  ru: {
    task: 'Задача',
    title: 'Название',
    note: 'Заметка',
    notePlaceholder: 'Детали, ссылки...',
    priority: 'Приоритет',
    project: 'Проект',
    due: 'Срок',
    remind: 'Напомнить в это время',
    save: 'Сохранить',
    close: 'Закрыть',
    saved: 'Сохранено',
    saveFailed: 'Не удалось сохранить',
    undoCompletion: 'Вернуть задачу',
    reopened: 'Задача возвращена',
    reopenFailed: 'Не удалось вернуть задачу',
    todayEvening: 'Сегодня 18:00',
    tomorrowMorning: 'Завтра 09:00',
    saturday: 'Суббота',
    noDue: 'Без срока',
    priorities: { low: 'Низкий', medium: 'Средний', high: 'Высокий', urgent: 'Срочно' },
  },
};

function toLocalInput(ts: string | null): string {
  if (!ts) return '';
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function quickDate(kind: 'today-evening' | 'tomorrow-morning' | 'weekend'): string {
  const d = new Date();
  if (kind === 'today-evening') {
    d.setHours(18, 0, 0, 0);
  } else if (kind === 'tomorrow-morning') {
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
  } else {
    const day = d.getDay();
    const toSaturday = (6 - day + 7) % 7 || 7;
    d.setDate(d.getDate() + toSaturday);
    d.setHours(11, 0, 0, 0);
  }
  return toLocalInput(d.toISOString());
}

export function TaskEditSheet({
  task,
  onClose,
}: {
  task: Task | null;
  onClose: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [project, setProject] = useState('');
  const [due, setDue] = useState('');
  const [remind, setRemind] = useState(true);
  const patchTask = usePatchTask();
  const { show } = useToast();
  const locale = useAppLocale();
  const copy = COPY[locale];

  useEffect(() => {
    if (task) {
      setTitle(task.title);
      setDescription(task.description ?? '');
      setPriority(task.priority);
      setProject(task.project ?? '');
      setDue(toLocalInput(task.due_at));
      setRemind(task.reminder_at !== null);
    }
  }, [task]);

  if (task === null) return null;

  const save = () => {
    const dueIso = due ? new Date(due).toISOString() : null;
    patchTask.mutate(
      {
        id: task.id,
        input: {
          title: title.trim() || task.title,
          description: description.trim() || null,
          priority,
          project: project.trim() || null,
          due_at: dueIso,
          reminder_at: remind && dueIso ? dueIso : null,
        },
      },
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

  const CHIPS: { label: string; value: string }[] = [
    { label: copy.todayEvening, value: quickDate('today-evening') },
    { label: copy.tomorrowMorning, value: quickDate('tomorrow-morning') },
    { label: copy.saturday, value: quickDate('weekend') },
    { label: copy.noDue, value: '' },
  ];
  const priorityOptions: { value: TaskPriority; label: string }[] = [
    { value: 'low', label: copy.priorities.low },
    { value: 'medium', label: copy.priorities.medium },
    { value: 'high', label: copy.priorities.high },
    { value: 'urgent', label: copy.priorities.urgent },
  ];

  return (
    <Sheet open onClose={onClose} title={copy.task} closeLabel={copy.close}>
      <label className="block">
        <FieldLabel>{copy.title}</FieldLabel>
        <Input value={title} onChange={setTitle} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.note}</FieldLabel>
        <Textarea value={description} onChange={setDescription} rows={2} placeholder={copy.notePlaceholder} />
      </label>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <FieldLabel>{copy.priority}</FieldLabel>
          <Select
            value={priority}
            onChange={(v) => setPriority(v as TaskPriority)}
            options={priorityOptions}
          />
        </label>
        <label className="block">
          <FieldLabel>{copy.project}</FieldLabel>
          <Input value={project} onChange={setProject} placeholder="lumi" />
        </label>
      </div>
      <div className="mt-4">
        <FieldLabel>{copy.due}</FieldLabel>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {CHIPS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => setDue(chip.value)}
              className={`min-h-[34px] rounded-full border px-3 text-[12.5px] transition-colors ${
                due === chip.value && (chip.value !== '' || due === '')
                  ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-ink'
                  : 'border-hairline text-hint'
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>
        <input
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none"
        />
        {due !== '' && (
          <label className="mt-2.5 flex items-center gap-2 text-[13px] text-ink">
            <input
              type="checkbox"
              checked={remind}
              onChange={(e) => setRemind(e.target.checked)}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            {copy.remind}
          </label>
        )}
      </div>
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
