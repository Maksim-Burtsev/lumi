import { motion, useReducedMotion } from 'framer-motion';
import type { Task } from '../../api/types';
import { formatDueLabel } from '../../lib/format';
import { useTimeDisplay } from '../../lib/useTimeDisplay';
import { haptic } from '../../telegram/webapp';

interface TaskCardProps {
  task: Task;
  onComplete: (task: Task) => void;
  onReopen?: (task: Task) => void;
  onEdit: (task: Task) => void;
}

function estimateLabel(minutes: number, locale: 'en' | 'ru'): string {
  if (minutes < 60) return `${minutes} ${locale === 'ru' ? 'мин' : 'min'}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} ${locale === 'ru' ? 'ч' : 'h'}` : `${hours} ${locale === 'ru' ? 'ч' : 'h'} ${rest} ${locale === 'ru' ? 'мин' : 'min'}`;
}

export function TaskCard({ task, onComplete, onReopen, onEdit }: TaskCardProps) {
  const reduceMotion = useReducedMotion();
  const timeDisplay = useTimeDisplay();
  const locale = timeDisplay.locale ?? 'en';
  const done = task.status === 'done';
  const overdue = !done && task.due_at !== null && new Date(task.due_at).getTime() < Date.now();
  const toggle = () => {
    haptic(done ? 'light' : 'success');
    if (done) onReopen?.(task);
    else onComplete(task);
  };
  const copy = locale === 'ru'
    ? {
        complete: `Выполнить: ${task.title}`,
        reopen: `Вернуть: ${task.title}`,
        details: `Открыть детали: ${task.title}`,
        deadline: 'Срок',
      }
    : {
        complete: `Complete: ${task.title}`,
        reopen: `Reopen: ${task.title}`,
        details: `Open details: ${task.title}`,
        deadline: 'Due',
      };

  const meta = [
    task.project,
    task.estimated_minutes === null ? null : estimateLabel(task.estimated_minutes, locale),
  ].filter((value): value is string => Boolean(value));
  const dueLabel = task.due_at ? `${copy.deadline} ${formatDueLabel(task.due_at, timeDisplay)}` : null;
  const detailsLabel = [copy.details, ...meta, dueLabel].filter(Boolean).join('. ');

  return (
    <div className="flex min-h-[64px] items-stretch gap-1 px-2 sm:px-3">
      <motion.button
        type="button"
        aria-label={done ? copy.reopen : copy.complete}
        disabled={done && !onReopen}
        onClick={toggle}
        whileTap={reduceMotion || (done && !onReopen) ? undefined : { scale: 0.86 }}
        transition={{ type: 'spring', stiffness: 420, damping: 22 }}
        className="flex w-11 shrink-0 items-center justify-center disabled:cursor-default"
      >
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full border-[1.5px] transition-colors ${
            done ? 'border-[var(--accent)] bg-accent' : 'border-[var(--hint)] bg-transparent'
          }`}
        >
          <motion.svg
            width="12"
            height="12"
            viewBox="0 0 14 14"
            fill="none"
            initial={false}
            animate={{ opacity: done ? 1 : 0, scale: done ? 1 : 0.5 }}
          >
            <path
              d="M2.5 7.5 5.5 10.5 11.5 3.5"
              stroke="var(--accent-foreground)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </motion.svg>
        </span>
      </motion.button>

      <button
        type="button"
        aria-label={detailsLabel}
        onClick={() => {
          haptic('light');
          onEdit(task);
        }}
        className="min-w-0 flex-1 py-3 text-left outline-none focus-visible:rounded-xl focus-visible:shadow-[0_0_0_3px_var(--accent-soft)]"
      >
        <p className={`text-[14.5px] leading-snug ${done ? 'text-hint line-through' : 'font-medium text-ink'}`}>
          {task.title}
        </p>
        {(meta.length > 0 || task.due_at) && (
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-hint">
            {meta.map((value, index) => (
              <span key={`${value}-${index}`} className="inline-flex min-w-0 max-w-full items-center gap-2">
                {index > 0 && <span aria-hidden className="text-[10px] opacity-60">•</span>}
                <span className="min-w-0 max-w-full truncate">{value}</span>
              </span>
            ))}
            {task.due_at && (
              <span className={`tnum inline-flex items-center gap-1 ${overdue ? 'font-medium text-danger' : ''}`}>
                {(meta.length > 0) && <span aria-hidden className="text-[10px] opacity-60">•</span>}
                <span>{dueLabel}</span>
              </span>
            )}
          </div>
        )}
      </button>
    </div>
  );
}
