import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Clock } from 'lucide-react';
import type { Task, SnoozePreset, TaskPriority } from '../../api/types';
import { formatDueLabel } from '../../lib/format';
import { haptic } from '../../telegram/webapp';

interface TaskCardProps {
  task: Task;
  onComplete: (id: string) => void;
  onSnooze: (id: string, preset: SnoozePreset) => void;
  onEdit?: (task: Task) => void;
}

const PRIORITY_DOTS: Record<TaskPriority, { className: string; label: string }> = {
  low: { className: 'bg-[#7d8896]', label: 'низкий приоритет' },
  medium: { className: 'bg-[rgba(46,99,231,0.55)]', label: 'средний приоритет' },
  high: { className: 'bg-[#d97a2b]', label: 'высокий приоритет' },
  urgent: { className: 'bg-[#c2553f]', label: 'срочно' },
};

const SNOOZE_PRESETS: { preset: SnoozePreset; label: string }[] = [
  { preset: '1h', label: '1 ч' },
  { preset: '3h', label: '3 ч' },
  { preset: 'tomorrow', label: 'Завтра' },
  { preset: 'next_week', label: 'След. неделя' },
];

export function TaskCard({ task, onComplete, onSnooze, onEdit }: TaskCardProps) {
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const reduceMotion = useReducedMotion();
  const done = task.status === 'done';
  const overdue = !done && task.due_at !== null && new Date(task.due_at).getTime() < Date.now();
  const priority = PRIORITY_DOTS[task.priority];

  return (
    <div className="card card-strong px-4 py-3">
      <div className="flex items-start gap-3">
        {/* Complete checkbox: 26px visual, ≥44px tap target */}
        <motion.button
          type="button"
          aria-label={done ? 'Задача выполнена' : 'Выполнить задачу'}
          disabled={done}
          whileTap={reduceMotion || done ? undefined : { scale: 0.85 }}
          transition={{ type: 'spring', stiffness: 420, damping: 22 }}
          onClick={() => {
            haptic('success');
            onComplete(task.id);
          }}
          className="relative -m-2 mt-[-5px] shrink-0 p-2"
        >
          <span
            className={`flex h-[26px] w-[26px] items-center justify-center rounded-full border-[1.5px] transition-colors duration-200 ${
              done ? 'border-[var(--accent)] bg-accent' : 'border-[var(--hint)] bg-transparent'
            }`}
          >
            <motion.svg
              width="13"
              height="13"
              viewBox="0 0 14 14"
              fill="none"
              initial={false}
              animate={{ opacity: done ? 1 : 0, scale: done ? 1 : 0.4 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <motion.path
                d="M2.5 7.5 L5.5 10.5 L11.5 3.5"
                stroke="#221903"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={false}
                animate={{ pathLength: done ? 1 : 0 }}
                transition={{ duration: 0.3, ease: 'easeOut' }}
              />
            </motion.svg>
          </span>
        </motion.button>

        <div
          className="min-w-0 flex-1"
          role={onEdit ? 'button' : undefined}
          onClick={onEdit ? () => onEdit(task) : undefined}
        >
          <p
            className={`text-[14.5px] leading-snug transition-colors ${
              done ? 'text-hint line-through' : 'font-medium text-ink'
            }`}
          >
            {task.title}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span
              aria-label={priority.label}
              title={priority.label}
              className={`h-[6px] w-[6px] shrink-0 rounded-full ${priority.className}`}
            />
            {task.due_at && (
              <span className={`tnum text-[12.5px] ${overdue ? 'font-medium text-danger' : 'text-hint'}`}>
                {formatDueLabel(task.due_at)}
              </span>
            )}
            {task.project && (
              <span className="rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">
                {task.project}
              </span>
            )}
            {task.tags.slice(0, 2).map((tag) => (
              <span key={tag} className="text-[11.5px] text-hint">
                #{tag}
              </span>
            ))}
          </div>
        </div>

        {!done && (
          <button
            type="button"
            aria-label="Отложить задачу"
            onClick={() => {
              haptic('light');
              setSnoozeOpen((v) => !v);
            }}
            className={`relative -m-2 mt-[-5px] shrink-0 p-2 transition-colors ${
              snoozeOpen ? 'text-accent-text' : 'text-hint'
            }`}
          >
            <Clock size={18} strokeWidth={1.8} />
          </button>
        )}
      </div>

      <AnimatePresence initial={false}>
        {snoozeOpen && !done && (
          <motion.div
            initial={reduceMotion ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="mt-2.5 flex items-center gap-1.5 border-t border-hairline pt-2.5">
              <span className="mr-1 text-[12px] text-hint">Отложить:</span>
              {SNOOZE_PRESETS.map(({ preset, label }) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setSnoozeOpen(false);
                    onSnooze(task.id, preset);
                  }}
                  className="relative rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 text-[12px] font-medium text-ink after:absolute after:-inset-1.5 after:content-['']"
                >
                  {label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
