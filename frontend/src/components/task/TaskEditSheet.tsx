import { useEffect, useState } from 'react';
import type { Task, TaskPriority } from '../../api/types';
import { usePatchTask } from '../../api/hooks';
import { Button } from '../ui/Button';
import { FieldLabel, Input, Select, Textarea } from '../ui/Field';
import { Sheet } from '../ui/Sheet';
import { useToast } from '../ui/Toast';

/** Full task editor: title, priority, project, due date with quick chips. */

const PRIORITY_OPTIONS: { value: TaskPriority; label: string }[] = [
  { value: 'low', label: 'Низкий' },
  { value: 'medium', label: 'Средний' },
  { value: 'high', label: 'Высокий' },
  { value: 'urgent', label: 'Срочно' },
];

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
          show('Сохранено', 'success');
          onClose();
        },
        onError: () => show('Не удалось сохранить', 'error'),
      },
    );
  };

  const CHIPS: { label: string; value: string }[] = [
    { label: 'Сегодня 18:00', value: quickDate('today-evening') },
    { label: 'Завтра 09:00', value: quickDate('tomorrow-morning') },
    { label: 'Суббота', value: quickDate('weekend') },
    { label: 'Без срока', value: '' },
  ];

  return (
    <Sheet open onClose={onClose} title="Задача">
      <label className="block">
        <FieldLabel>Название</FieldLabel>
        <Input value={title} onChange={setTitle} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Заметка</FieldLabel>
        <Textarea value={description} onChange={setDescription} rows={2} placeholder="Детали, ссылки…" />
      </label>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <FieldLabel>Приоритет</FieldLabel>
          <Select
            value={priority}
            onChange={(v) => setPriority(v as TaskPriority)}
            options={PRIORITY_OPTIONS}
          />
        </label>
        <label className="block">
          <FieldLabel>Проект</FieldLabel>
          <Input value={project} onChange={setProject} placeholder="lumi" />
        </label>
      </div>
      <div className="mt-4">
        <FieldLabel>Срок</FieldLabel>
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
            Напомнить в это время
          </label>
        )}
      </div>
      <Button fullWidth className="mt-5" busy={patchTask.isPending} onClick={save}>
        Сохранить
      </Button>
    </Sheet>
  );
}
