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
    overtime: 'over plan',
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
    streak: 'streak',
    analytics: 'Analytics',
    week: 'Week',
    month: 'Month',
    forWeek: 'this week',
    forMonth: 'this month',
    projectsEmpty: 'Projects appear after completed sessions.',
    history: 'History',
    details: 'Details',
    historyEmpty: 'Completed sessions appear here.',
    historyDetails: 'Session history',
    days: 'Days',
    projects: 'Projects',
    recentSessions: 'Recent sessions',
    noSessionsForDay: 'No sessions for this day.',
    startAt: 'Start',
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
    overtime: 'сверх плана',
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
    streak: 'стрик',
    analytics: 'Аналитика',
    week: 'Неделя',
    month: 'Месяц',
    forWeek: 'за неделю',
    forMonth: 'за месяц',
    projectsEmpty: 'Проекты появятся после завершенных сессий.',
    history: 'История',
    details: 'Детали',
    historyEmpty: 'Завершенные сессии появятся здесь.',
    historyDetails: 'История сессий',
    days: 'Дни',
    projects: 'Проекты',
    recentSessions: 'Последние сессии',
    noSessionsForDay: 'В этот день сессий нет.',
    startAt: 'Начало',
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
  locale: AppLocale;
  onSelect: (task: Task | null) => void;
}

function TaskPickerSheet({ open, onClose, tasks, selectedTaskId, locale, onSelect }: TaskPickerSheetProps) {
  const copy = COPY[locale];
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
    <Sheet open={open} onClose={onClose} title={copy.taskPicker}>
      <div className="space-y-3">
        <label>
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
        <div className="overflow-hidden rounded-2xl border border-hairline">
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
                <span className="block truncate text-[12.5px] text-hint">
                  {task.project ?? copy.noProject} · {task.status === 'active' ? copy.taskStatusActive : copy.taskStatusInbox}
                </span>
              </span>
              {selectedTaskId === task.id && <Check size={16} className="shrink-0 text-accent-text" />}
            </button>
          ))}
          {visible.length === 0 && <p className="border-t border-hairline px-4 py-4 text-[13px] text-hint">{copy.nothingFound}</p>}
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

function StartSheet({ open, onClose, locale }: { open: boolean; onClose: () => void; locale: AppLocale }) {
  const copy = COPY[locale];
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
          <label>
            <FieldLabel>{copy.project}</FieldLabel>
            <Input value={project} onChange={setProject} placeholder="Lumi" />
          </label>
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
        <Button fullWidth busy={finish.isPending} onClick={submit} icon={<Check size={16} />}>
          {copy.saveSession}
        </Button>
      </div>
    </Sheet>
  );
}

function ManualLogSheet({ open, onClose, locale }: { open: boolean; onClose: () => void; locale: AppLocale }) {
  const copy = COPY[locale];
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
    const text = intention.trim() || selectedTask?.title || project.trim() || copy.defaultIntention;
    if (logFocus.isPending) return;
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
          <label>
            <FieldLabel>{copy.startAt}</FieldLabel>
            <input
              aria-label={copy.startAt}
              type="datetime-local"
              value={loggedAt}
              onChange={(event) => setLoggedAt(event.target.value)}
              className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            />
          </label>
          <MinuteInput value={duration} onChange={setDuration} label={copy.durationMinutes} />
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
          <label>
            <FieldLabel>{copy.project}</FieldLabel>
            <Input value={project} onChange={setProject} placeholder={copy.optionalProject} />
          </label>
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
    </>
  );
}

function FloatingDial({ session, now, locale }: { session: FocusSession; now: number; locale: AppLocale }) {
  const copy = COPY[locale];
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
      <svg aria-label={copy.progressLabel} viewBox="0 0 260 260" className="absolute inset-0 h-full w-full">
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
        <p className="mt-2 text-[12.5px] font-medium text-hint">{overtime > 0 ? copy.overtime : copy.remaining}</p>
        <p className="tnum mt-1 text-[12px] text-hint">{secondsLabel(total, locale)} {copy.plan}</p>
      </div>
    </div>
  );
}

function ActiveSessionCard({ session, locale }: { session: FocusSession; locale: AppLocale }) {
  const copy = COPY[locale];
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
              {session.project ?? copy.noProject}
            </span>
            <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${overtime ? 'text-success' : 'text-hint'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${overtime ? 'bg-success' : 'bg-accent'}`} />
              {overtime ? copy.overtime : copy.active}
            </span>
          </div>
          <h2 className="mt-5 text-[24px] font-semibold leading-tight tracking-normal text-ink">{session.intention}</h2>
          <FloatingDial session={session} now={now} locale={locale} />
          <p className="tnum text-center text-[12.5px] text-hint">
            {formatTime(session.started_at)} — {formatTime(session.target_end_at)}
            {session.task ? ` · ${session.task.title}` : ''}
          </p>
          <div className="mt-5 grid grid-cols-2 gap-2.5">
            <Button onClick={() => setReflectionOpen(true)} icon={<Check size={16} />}>
              {copy.finish}
            </Button>
            <Button variant="secondary" busy={abandon.isPending} onClick={() => abandon.mutate(session.id)} icon={<X size={16} />}>
              {copy.cancel}
            </Button>
          </div>
        </div>
      </Card>
      <ReflectionSheet session={session} open={reflectionOpen} onClose={() => setReflectionOpen(false)} locale={locale} />
    </>
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

function ActivityStrip({
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
  const max = Math.max(1, ...items.map((item) => item.focus_seconds));
  return (
    <div className="flex h-16 items-end gap-2 rounded-2xl border border-hairline px-3 py-3">
      {items.map((item) => {
        const hasWork = item.focus_seconds > 0;
        const selected = selectedDate === item.date;
        const height = hasWork ? 10 + Math.round((item.focus_seconds / max) * 32) : 6;
        return (
          <button
            key={item.date}
            type="button"
            onClick={() => onSelectDate?.(item.date)}
            className="flex min-w-0 flex-1 flex-col items-center gap-1.5 rounded-xl outline-none focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            aria-label={`${item.date}: ${secondsLabel(item.focus_seconds, locale)}`}
          >
            <div
              className={`w-full rounded-full transition-colors ${
                selected
                  ? 'bg-accent'
                  : hasWork
                    ? 'bg-[var(--accent-soft)]'
                    : 'bg-[var(--hairline)] opacity-60'
              }`}
              style={{ height }}
              title={`${item.date}: ${secondsLabel(item.focus_seconds, locale)}`}
            />
            <span className={`tnum text-[10px] ${selected || hasWork ? 'text-ink' : 'text-hint'}`}>{new Date(item.date).getDate()}</span>
          </button>
        );
      })}
    </div>
  );
}

function HistoryDetailsSheet({
  open,
  onClose,
  locale,
  summary,
  sessions,
}: {
  open: boolean;
  onClose: () => void;
  locale: AppLocale;
  summary: FocusSummaryResponse | undefined;
  sessions: FocusSession[];
}) {
  const copy = COPY[locale];
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const daily = summary?.daily_activity ?? [];
  const activeDate = selectedDate ?? [...daily].reverse().find((item) => item.focus_seconds > 0)?.date ?? daily[daily.length - 1]?.date ?? null;
  const sessionsForDay = activeDate ? sessions.filter((item) => sessionDateKey(item) === activeDate) : sessions;
  const maxProjectSeconds = Math.max(1, ...(summary?.project_breakdown ?? []).map((item) => item.focus_seconds));

  useEffect(() => {
    if (open) setSelectedDate(null);
  }, [open]);

  return (
    <Sheet open={open} onClose={onClose} title={copy.historyDetails}>
      <div className="space-y-5">
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-ink">{copy.days}</h3>
            <span className="tnum text-[12px] text-hint">{activeDate ?? '—'}</span>
          </div>
          <ActivityStrip items={daily} locale={locale} selectedDate={activeDate} onSelectDate={setSelectedDate} />
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
            {sessionsForDay.length > 0 ? (
              sessionsForDay.map((item) => (
                <div key={item.id} className="border-b border-hairline px-4 py-3 last:border-b-0">
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

export default function FocusPage() {
  const locale = useAppLocale();
  const copy = COPY[locale];
  const [startOpen, setStartOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [period, setPeriod] = useState<'week' | 'month'>('week');
  const state = useFocusState();
  const summary = useFocusSummary(period);
  const active = state.data?.active_session ?? null;
  const today = state.data?.today;
  const daily = summary.data?.daily_activity ?? [];
  const activeDate = selectedDate ?? [...daily].reverse().find((item) => item.focus_seconds > 0)?.date ?? null;

  return (
    <Stagger className={!active ? 'pb-24' : ''}>
      {state.isPending ? (
        <SkeletonList count={4} lines={2} />
      ) : active ? (
        <Rise>
          <ActiveSessionCard session={active} locale={locale} />
        </Rise>
      ) : (
        <Rise>
          <EmptyFocusCard onStart={() => setStartOpen(true)} onLog={() => setLogOpen(true)} locale={locale} />
        </Rise>
      )}

      <Rise>
        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{secondsLabel(today?.focus_seconds ?? 0, locale)}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">{copy.today}</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{today?.completed_sessions ?? 0}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">{copy.countSessions}</p>
          </Card>
          <Card className="px-3 py-3 text-center" strong>
            <p className="tnum text-[16px] font-semibold text-ink">{today?.streak_days ?? 0}</p>
            <p className="mt-0.5 text-[11.5px] text-hint">{copy.streak}</p>
          </Card>
        </div>
      </Rise>

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
              <p><span className="tnum font-semibold text-ink">{summary.data?.total_sessions ?? 0}</span> {copy.countSessions}</p>
              <p><span className="tnum font-semibold text-ink">{summary.data?.average_focus_score ?? '—'}</span> {copy.score.toLowerCase()}</p>
            </div>
          </div>
          <div className="mt-4">
            <ActivityStrip items={daily} locale={locale} selectedDate={activeDate} onSelectDate={(date) => {
              setSelectedDate(date);
              setHistoryOpen(true);
            }} />
          </div>
          {summary.data?.project_breakdown.length ? (
            <div className="mt-4 divide-y divide-hairline">
              {summary.data.project_breakdown.map((item) => (
                <div key={item.project} className="flex items-center justify-between py-2.5">
                  <span className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
                    <CircleDot size={14} className="text-accent-text" />
                    {item.project}
                  </span>
                  <span className="tnum text-[13px] text-hint">{secondsLabel(item.focus_seconds, locale)}</span>
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
              {copy.details}
            </button>
          }
        />
        <Card className="divide-y divide-hairline overflow-hidden !p-0" strong>
          {(state.data?.recent_sessions ?? []).length > 0 ? (
            state.data?.recent_sessions.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setSelectedDate(sessionDateKey(item));
                  setHistoryOpen(true);
                }}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink">{item.intention}</p>
                  <p className="truncate text-[12.5px] text-hint">{item.project ?? copy.noProject}{item.task ? ` · ${item.task.title}` : ''}</p>
                </div>
                <span className="tnum shrink-0 text-[13px] font-medium text-ink">{secondsLabel(item.duration_seconds ?? 0, locale)}</span>
              </button>
            ))
          ) : (
            <p className="px-4 py-4 text-[13px] text-hint">{copy.historyEmpty}</p>
          )}
        </Card>
      </Rise>

      {!active && (
        <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+88px)] left-1/2 z-40 grid w-[calc(100%-32px)] max-w-[420px] -translate-x-1/2 grid-cols-2 gap-2">
          <Button fullWidth onClick={() => setStartOpen(true)} icon={<Timer size={16} />}>
            {copy.session}
          </Button>
          <Button fullWidth variant="secondary" onClick={() => setLogOpen(true)} icon={<ListChecks size={16} />}>
            {copy.logShort}
          </Button>
        </div>
      )}

      <StartSheet open={startOpen} onClose={() => setStartOpen(false)} locale={locale} />
      <ManualLogSheet open={logOpen} onClose={() => setLogOpen(false)} locale={locale} />
      <HistoryDetailsSheet
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        locale={locale}
        summary={summary.data}
        sessions={state.data?.recent_sessions ?? []}
      />
    </Stagger>
  );
}
