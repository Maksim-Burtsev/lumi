import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  Check,
  CircleDot,
  ClipboardPenLine,
  ListChecks,
  Plus,
  Search,
  Timer,
  X,
} from 'lucide-react';
import {
  useAbandonFocusSession,
  useFinishFocusSession,
  useFocusState,
  useFocusSummary,
  useLogFocusSession,
  useStartFocusSession,
  useTasks,
} from '../api/hooks';
import type { FocusSession, Task } from '../api/types';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Sheet } from '../components/ui/Sheet';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatTime } from '../lib/format';
import { haptic } from '../telegram/webapp';

const DURATIONS = [25, 45, 60];
const DEFAULT_DURATION = 45;

function secondsLabel(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  if (hours > 0) return `${hours}ч ${String(minutes).padStart(2, '0')}м`;
  return `${minutes}м`;
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

function datetimeInputValue(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function datetimeInputToIso(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? new Date().toISOString() : parsed.toISOString();
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

interface TaskPickerSheetProps {
  open: boolean;
  onClose: () => void;
  tasks: Task[];
  selectedTaskId: string;
  onSelect: (task: Task | null) => void;
}

function TaskPickerSheet({ open, onClose, tasks, selectedTaskId, onSelect }: TaskPickerSheetProps) {
  const [query, setQuery] = useState('');
  const visible = useMemo(() => tasks.filter((task) => matchesTask(task, query)), [query, tasks]);

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const choose = (task: Task | null) => {
    onSelect(task);
    onClose();
  };

  return (
    <Sheet open={open} onClose={onClose} title="Выбор задачи">
      <div className="space-y-3">
        <label>
          <FieldLabel>Поиск</FieldLabel>
          <div className="relative">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hint" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск задач"
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] pl-9 pr-3 text-[15px] text-ink outline-none focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </div>
        </label>
        <div className="overflow-hidden rounded-2xl border border-hairline">
          <button
            type="button"
            onClick={() => choose(null)}
            className={`flex w-full items-center justify-between px-4 py-3 text-left ${selectedTaskId === '' ? 'bg-[var(--accent-soft)]' : 'bg-transparent'}`}
          >
            <span>
              <span className="block text-[14.5px] font-medium text-ink">Без задачи</span>
              <span className="block text-[12.5px] text-hint">Только намерение и проект</span>
            </span>
            {selectedTaskId === '' && <Check size={16} className="text-accent-text" />}
          </button>
          {visible.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => choose(task)}
              className={`flex w-full items-center justify-between border-t border-hairline px-4 py-3 text-left ${
                selectedTaskId === task.id ? 'bg-[var(--accent-soft)]' : 'bg-transparent'
              }`}
            >
              <span className="min-w-0">
                <span className="block truncate text-[14.5px] font-medium text-ink">{task.title}</span>
                <span className="block truncate text-[12.5px] text-hint">{task.project ?? 'Без проекта'} · {task.status}</span>
              </span>
              {selectedTaskId === task.id && <Check size={16} className="shrink-0 text-accent-text" />}
            </button>
          ))}
          {visible.length === 0 && <p className="border-t border-hairline px-4 py-4 text-[13px] text-hint">Ничего не найдено.</p>}
        </div>
      </div>
    </Sheet>
  );
}

function DurationControl({ value, onChange, label }: { value: number; onChange: (value: number) => void; label: string }) {
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
      <FieldLabel>Длительность</FieldLabel>
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

function MinuteInput({ value, onChange, label }: { value: number; onChange: (value: number) => void; label: string }) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const update = (next: string) => {
    setDraft(next);
    if (next.trim() !== '') onChange(clampMinutes(next));
  };

  return (
    <label>
      <FieldLabel>{label}</FieldLabel>
      <input
        aria-label={label}
        type="number"
        min={1}
        max={240}
        value={draft}
        onBlur={() => setDraft(String(clampMinutes(draft)))}
        onChange={(event) => update(event.target.value)}
        className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
      />
    </label>
  );
}

function StartSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const tasksQuery = useTasks('all');
  const start = useStartFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [taskId, setTaskId] = useState('');
  const [project, setProject] = useState('');

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;

  useEffect(() => {
    if (selectedTask?.project) setProject(selectedTask.project);
  }, [selectedTask]);

  const submit = () => {
    const text = intention.trim();
    if (!text || start.isPending) return;
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
        onError: () => show('Не удалось начать сессию', 'error'),
      },
    );
  };

  return (
    <>
      <Sheet open={open} onClose={onClose} title="Новая сессия">
        <div className="space-y-4">
          <label>
            <FieldLabel>Намерение</FieldLabel>
            <Input value={intention} onChange={setIntention} placeholder="Над чем будешь работать?" />
          </label>
          <DurationControl value={duration} onChange={setDuration} label="Своя длительность" />
          <div>
            <FieldLabel>Задача</FieldLabel>
            <button
              type="button"
              onClick={() => setTaskPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{selectedTask ? selectedTask.title : 'Без задачи'}</span>
              <span className="text-[12px] text-hint">Выбрать задачу</span>
            </button>
          </div>
          <label>
            <FieldLabel>Проект</FieldLabel>
            <Input value={project} onChange={setProject} placeholder="Lumi" />
          </label>
          <Button fullWidth busy={start.isPending} onClick={submit} icon={<Timer size={16} />}>
            Старт {duration} мин
          </Button>
        </div>
      </Sheet>
      <TaskPickerSheet
        open={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        tasks={tasks}
        selectedTaskId={taskId}
        onSelect={(task) => {
          setTaskId(task?.id ?? '');
          setProject(task?.project ?? project);
        }}
      />
    </>
  );
}

function ScorePicker({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div>
      <FieldLabel>Фокус</FieldLabel>
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

function ReflectionSheet({ session, open, onClose }: { session: FocusSession | null; open: boolean; onClose: () => void }) {
  const finish = useFinishFocusSession();
  const { show } = useToast();
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState(4);

  useEffect(() => {
    if (open) {
      setAccomplished('');
      setDistraction('');
      setNextStep('');
      setScore(4);
    }
  }, [open]);

  if (!session) return null;

  const submit = () => {
    finish.mutate(
      {
        id: session.id,
        input: {
          ended_at: new Date().toISOString(),
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
        onError: () => show('Не удалось сохранить сессию', 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title="Итог сессии">
      <div className="space-y-4">
        <div className="rounded-2xl bg-[var(--accent-soft)] px-4 py-3">
          <p className="text-[13px] font-medium text-ink">{session.project ?? 'Без проекта'}</p>
          <p className="mt-0.5 text-[12.5px] text-hint">{session.intention}</p>
        </div>
        <label>
          <FieldLabel>Что сделал?</FieldLabel>
          <Textarea value={accomplished} onChange={setAccomplished} rows={3} placeholder="Коротко зафиксируй результат" />
        </label>
        <label>
          <FieldLabel>Что мешало?</FieldLabel>
          <Textarea value={distraction} onChange={setDistraction} rows={2} placeholder="Отвлечения, блокеры, контекст" />
        </label>
        <label>
          <FieldLabel>Следующий шаг</FieldLabel>
          <Textarea value={nextStep} onChange={setNextStep} rows={2} placeholder="Что сделать дальше?" />
        </label>
        <ScorePicker value={score} onChange={setScore} />
        <Button fullWidth busy={finish.isPending} onClick={submit} icon={<Check size={16} />}>
          Сохранить сессию
        </Button>
      </div>
    </Sheet>
  );
}

function ManualLogSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const tasksQuery = useTasks('all');
  const logFocus = useLogFocusSession();
  const { show } = useToast();
  const [taskPickerOpen, setTaskPickerOpen] = useState(false);
  const [intention, setIntention] = useState('');
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [taskId, setTaskId] = useState('');
  const [project, setProject] = useState('');
  const [accomplished, setAccomplished] = useState('');
  const [distraction, setDistraction] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [score, setScore] = useState(4);
  const [loggedAt, setLoggedAt] = useState(() => datetimeInputValue(new Date()));

  const tasks = useMemo(() => activeTasks(tasksQuery.data?.items ?? []), [tasksQuery.data]);
  const selectedTask = tasks.find((task) => task.id === taskId) ?? null;

  const submit = () => {
    const text = intention.trim();
    if (!text || logFocus.isPending) return;
    logFocus.mutate(
      {
        task_id: taskId || null,
        project: project.trim() || selectedTask?.project || null,
        intention: text,
        logged_at: datetimeInputToIso(loggedAt),
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
          setLoggedAt(datetimeInputValue(new Date()));
          onClose();
        },
        onError: () => show('Не удалось сохранить блок', 'error'),
      },
    );
  };

  return (
    <>
      <Sheet open={open} onClose={onClose} title="Залогировать блок">
        <div className="space-y-4">
          <label>
            <FieldLabel>Намерение</FieldLabel>
            <Input value={intention} onChange={setIntention} placeholder="Что делал?" />
          </label>
          <label>
            <FieldLabel>Начало</FieldLabel>
            <input
              aria-label="Начало"
              type="datetime-local"
              value={loggedAt}
              onChange={(event) => setLoggedAt(event.target.value)}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </label>
          <MinuteInput value={duration} onChange={setDuration} label="Длительность, минут" />
          <div>
            <FieldLabel>Задача</FieldLabel>
            <button
              type="button"
              onClick={() => setTaskPickerOpen(true)}
              className="flex h-11 w-full items-center justify-between rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-left text-[15px] text-ink"
            >
              <span className="min-w-0 truncate">{selectedTask ? selectedTask.title : 'Без задачи'}</span>
              <span className="text-[12px] text-hint">Выбрать задачу</span>
            </button>
          </div>
          <label>
            <FieldLabel>Проект</FieldLabel>
            <Input value={project} onChange={setProject} placeholder="Опционально" />
          </label>
          <label>
            <FieldLabel>Что сделал?</FieldLabel>
            <Textarea value={accomplished} onChange={setAccomplished} rows={3} placeholder="Итог блока" />
          </label>
          <label>
            <FieldLabel>Что мешало?</FieldLabel>
            <Textarea value={distraction} onChange={setDistraction} rows={2} placeholder="Опционально" />
          </label>
          <label>
            <FieldLabel>Следующий шаг</FieldLabel>
            <Textarea value={nextStep} onChange={setNextStep} rows={2} placeholder="Опционально" />
          </label>
          <ScorePicker value={score} onChange={setScore} />
          <Button fullWidth busy={logFocus.isPending} onClick={submit} icon={<ClipboardPenLine size={16} />}>
            Сохранить блок
          </Button>
        </div>
      </Sheet>
      <TaskPickerSheet
        open={taskPickerOpen}
        onClose={() => setTaskPickerOpen(false)}
        tasks={tasks}
        selectedTaskId={taskId}
        onSelect={(task) => {
          setTaskId(task?.id ?? '');
          setProject(task?.project ?? project);
        }}
      />
    </>
  );
}

function FloatingDial({ session, now }: { session: FocusSession; now: number }) {
  const started = new Date(session.started_at).getTime();
  const target = new Date(session.target_end_at).getTime();
  const { total, remaining, overtime, progress } = getDialMetrics({ started, target, now });
  const radius = 103;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * 0.82;
  const gap = circumference - arcLength;
  const visibleArc = overtime > 0 ? arcLength : Math.max(0, arcLength * (1 - progress));
  const arcStart = Math.PI * 0.59;
  const arcSpan = Math.PI * 1.64;
  const beadAngle = overtime > 0 ? arcStart + arcSpan : arcStart + arcSpan * (1 - progress);
  const beadX = 130 + radius * Math.cos(beadAngle);
  const beadY = 130 + radius * Math.sin(beadAngle);

  return (
    <div className="relative mx-auto mt-5 flex h-[270px] w-[270px] items-center justify-center">
      <svg aria-label="Прогресс фокус-сессии" viewBox="0 0 260 260" className="absolute inset-0 h-full w-full">
        <circle
          cx="130"
          cy="130"
          r={radius}
          fill="none"
          stroke="var(--hairline)"
          strokeWidth="5"
          strokeDasharray={`${arcLength} ${gap}`}
          strokeLinecap="round"
          transform="rotate(122 130 130)"
        />
        <circle
          cx="130"
          cy="130"
          r={radius}
          fill="none"
          stroke={overtime > 0 ? 'var(--success)' : 'var(--accent)'}
          strokeWidth="5"
          strokeDasharray={`${visibleArc} ${circumference - visibleArc}`}
          strokeLinecap="round"
          transform="rotate(122 130 130)"
          className="drop-shadow-[0_0_10px_rgba(46,99,231,0.22)]"
        />
        <circle cx={beadX} cy={beadY} r="5.2" fill={overtime > 0 ? 'var(--success)' : 'var(--accent)'} />
      </svg>
      <div className="text-center">
        <p className={`tnum text-[48px] font-semibold leading-none tracking-normal ${overtime > 0 ? 'text-success' : 'text-ink'}`}>
          {overtime > 0 ? `+${timerLabel(overtime)}` : timerLabel(remaining)}
        </p>
        <p className="mt-2 text-[12.5px] font-medium text-hint">{overtime > 0 ? 'сверх плана' : 'осталось'}</p>
        <p className="tnum mt-1 text-[12px] text-hint">{secondsLabel(total)} план</p>
      </div>
    </div>
  );
}

function ActiveSessionCard({ session }: { session: FocusSession }) {
  const now = useNow();
  const abandon = useAbandonFocusSession();
  const [reflectionOpen, setReflectionOpen] = useState(false);
  const [notifiedFor, setNotifiedFor] = useState<string | null>(null);
  const overtime = now >= new Date(session.target_end_at).getTime();

  useEffect(() => {
    if (overtime && notifiedFor !== session.id) {
      setNotifiedFor(session.id);
      haptic('success');
      playFocusDoneSound();
    }
  }, [notifiedFor, overtime, session.id]);

  return (
    <>
      <Card className="relative overflow-hidden px-5 py-5">
        <div aria-hidden className="dawn-glow opacity-50" />
        <div className="relative">
          <div className="flex items-center justify-between gap-3">
            <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[12px] font-medium text-accent-text">
              {session.project ?? 'Без проекта'}
            </span>
            <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${overtime ? 'text-success' : 'text-hint'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${overtime ? 'bg-success' : 'bg-accent'}`} />
              {overtime ? 'сверх плана' : 'идет сессия'}
            </span>
          </div>
          <h2 className="mt-5 text-[24px] font-semibold leading-tight tracking-normal text-ink">{session.intention}</h2>
          <FloatingDial session={session} now={now} />
          <p className="tnum text-center text-[12.5px] text-hint">
            {formatTime(session.started_at)} — {formatTime(session.target_end_at)}
            {session.task ? ` · ${session.task.title}` : ''}
          </p>
          <div className="mt-5 grid grid-cols-2 gap-2.5">
            <Button onClick={() => setReflectionOpen(true)} icon={<Check size={16} />}>
              Завершить
            </Button>
            <Button variant="secondary" busy={abandon.isPending} onClick={() => abandon.mutate(session.id)} icon={<X size={16} />}>
              Отменить
            </Button>
          </div>
        </div>
      </Card>
      <ReflectionSheet session={session} open={reflectionOpen} onClose={() => setReflectionOpen(false)} />
    </>
  );
}

function EmptyFocusCard({ onStart, onLog }: { onStart: () => void; onLog: () => void }) {
  return (
    <Card className="relative overflow-hidden p-5">
      <div aria-hidden className="dawn-glow" />
      <div className="relative">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-soft)] text-accent-text">
          <Timer size={19} />
        </span>
        <h2 className="mt-4 text-[23px] font-semibold leading-tight text-ink">Готов к фокус-сессии?</h2>
        <p className="mt-2 text-[13.5px] leading-relaxed text-hint">
          Запусти таймер или залогируй блок, который уже сделал в другом месте.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2.5">
          <Button onClick={onStart} icon={<Plus size={16} />}>
            Начать фокус
          </Button>
          <Button variant="secondary" onClick={onLog} icon={<ClipboardPenLine size={16} />}>
            Залогировать
          </Button>
        </div>
      </div>
    </Card>
  );
}

function ActivityStrip({ items }: { items: { date: string; focus_seconds: number }[] }) {
  const max = Math.max(1, ...items.map((item) => item.focus_seconds));
  return (
    <div className="flex h-16 items-end gap-2 rounded-2xl border border-hairline px-3 py-3">
      {items.map((item) => {
        const height = 8 + Math.round((item.focus_seconds / max) * 34);
        return (
          <div key={item.date} className="flex flex-1 flex-col items-center gap-1.5">
            <div
              className="w-full rounded-full bg-[var(--accent-soft)]"
              style={{ height }}
              title={`${item.date}: ${secondsLabel(item.focus_seconds)}`}
            />
            <span className="tnum text-[10px] text-hint">{new Date(item.date).getDate()}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function FocusPage() {
  const [startOpen, setStartOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const state = useFocusState();
  const summary = useFocusSummary(period);
  const active = state.data?.active_session ?? null;
  const today = state.data?.today;

  return (
    <Stagger className={!active ? 'pb-24' : ''}>
      {state.isPending ? (
        <SkeletonList count={4} lines={2} />
      ) : active ? (
        <Rise>
          <ActiveSessionCard session={active} />
        </Rise>
      ) : (
        <Rise>
          <EmptyFocusCard onStart={() => setStartOpen(true)} onLog={() => setLogOpen(true)} />
        </Rise>
      )}

      <Rise>
        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{secondsLabel(today?.focus_seconds ?? 0)}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">сегодня</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{today?.completed_sessions ?? 0}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">сессий</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{today?.streak_days ?? 0}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">стрик</p>
          </Card>
        </div>
      </Rise>

      <Rise>
        <SectionHeader
          title="Аналитика"
          action={
            <div className="flex gap-1.5">
              <Chip label="Неделя" active={period === 'week'} onClick={() => setPeriod('week')} />
              <Chip label="Месяц" active={period === 'month'} onClick={() => setPeriod('month')} />
            </div>
          }
        />
        <Card className="p-4" strong>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="tnum text-[25px] font-semibold text-ink">{secondsLabel(summary.data?.total_focus_seconds ?? 0)}</p>
              <p className="text-[12.5px] text-hint">{period === 'week' ? 'за неделю' : 'за месяц'}</p>
            </div>
            <div className="text-right text-[12.5px] text-hint">
              <p><span className="tnum font-semibold text-ink">{summary.data?.total_sessions ?? 0}</span> сессий</p>
              <p><span className="tnum font-semibold text-ink">{summary.data?.average_focus_score ?? '—'}</span> фокус</p>
            </div>
          </div>
          <div className="mt-4">
            <ActivityStrip items={summary.data?.daily_activity ?? []} />
          </div>
          {summary.data?.project_breakdown.length ? (
            <div className="mt-4 divide-y divide-hairline">
              {summary.data.project_breakdown.map((item) => (
                <div key={item.project} className="flex items-center justify-between py-2.5">
                  <span className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
                    <CircleDot size={14} className="text-accent-text" />
                    {item.project}
                  </span>
                  <span className="tnum text-[13px] text-hint">{secondsLabel(item.focus_seconds)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-[13px] text-hint">Проекты появятся после завершенных сессий.</p>
          )}
        </Card>
      </Rise>

      <Rise>
        <SectionHeader title="История" action={<BarChart3 size={16} className="text-hint" />} />
        <Card className="divide-y divide-hairline overflow-hidden !p-0" strong>
          {(state.data?.recent_sessions ?? []).length > 0 ? (
            state.data?.recent_sessions.map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                  <p className="truncate text-[12.5px] text-hint">{item.project ?? 'Без проекта'}{item.task ? ` · ${item.task.title}` : ''}</p>
                </div>
                <span className="tnum shrink-0 text-[13px] font-medium text-ink">{secondsLabel(item.duration_seconds ?? 0)}</span>
              </div>
            ))
          ) : (
            <p className="px-4 py-4 text-[13px] text-hint">Завершенные сессии появятся здесь.</p>
          )}
        </Card>
      </Rise>

      {!active && (
        <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+88px)] left-1/2 z-40 grid w-[calc(100%-32px)] max-w-[420px] -translate-x-1/2 grid-cols-2 gap-2">
          <Button fullWidth onClick={() => setStartOpen(true)} icon={<Timer size={16} />}>
            Таймер
          </Button>
          <Button fullWidth variant="secondary" onClick={() => setLogOpen(true)} icon={<ListChecks size={16} />}>
            Лог
          </Button>
        </div>
      )}

      <StartSheet open={startOpen} onClose={() => setStartOpen(false)} />
      <ManualLogSheet open={logOpen} onClose={() => setLogOpen(false)} />
    </Stagger>
  );
}
