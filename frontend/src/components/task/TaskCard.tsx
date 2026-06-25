import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ChevronRight, Clock, RotateCcw } from 'lucide-react';
import type { Task, SnoozePreset, TaskPriority } from '../../api/types';
import { formatDueLabel } from '../../lib/format';
import { useTimeDisplay } from '../../lib/useTimeDisplay';
import { haptic } from '../../telegram/webapp';

interface TaskCardProps {
  task: Task;
  onComplete: (id: string) => void;
  onReopen?: (id: string) => void;
  onSnooze: (id: string, preset: SnoozePreset) => void;
  onEdit?: (task: Task) => void;
  estimateSuggestion?: { id: string; minutes: number; reason?: string | null };
  onAcceptEstimate?: (suggestionId: string) => void;
  onEditEstimate?: (task: Task, suggestion: { id: string; minutes: number; reason?: string | null }) => void;
}

const PRIORITY_DOTS: Record<TaskPriority, { className: string; label: { en: string; ru: string } }> = {
  low: { className: 'bg-[#7d8896]', label: { en: 'low priority', ru: 'низкий приоритет' } },
  medium: { className: 'bg-[rgba(46,99,231,0.55)]', label: { en: 'medium priority', ru: 'средний приоритет' } },
  high: { className: 'bg-[#d97a2b]', label: { en: 'high priority', ru: 'высокий приоритет' } },
  urgent: { className: 'bg-[#c2553f]', label: { en: 'urgent', ru: 'срочно' } },
};

const SNOOZE_PRESETS: { preset: SnoozePreset; label: { en: string; ru: string } }[] = [
  { preset: '1h', label: { en: '1 hr', ru: '1 ч' } },
  { preset: '3h', label: { en: '3 hrs', ru: '3 ч' } },
  { preset: 'tomorrow', label: { en: 'Tomorrow', ru: 'Завтра' } },
  { preset: 'next_week', label: { en: 'Next week', ru: 'След. неделя' } },
];

export function TaskCard({
  task,
  onComplete,
  onReopen,
  onSnooze,
  onEdit,
  estimateSuggestion,
  onAcceptEstimate,
  onEditEstimate,
}: TaskCardProps) {
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const reduceMotion = useReducedMotion();
  const timeDisplay = useTimeDisplay();
  const locale = timeDisplay.locale === 'ru' ? 'ru' : 'en';
  const done = task.status === 'done';
  const overdue = !done && task.due_at !== null && new Date(task.due_at).getTime() < Date.now();
  const priority = PRIORITY_DOTS[task.priority];
  const complete = () => {
    if (done) {
      if (!onReopen) return;
      haptic('light');
      onReopen(task.id);
      return;
    }
    haptic('success');
    onComplete(task.id);
  };

  return (
    <div className="card card-strong px-4 py-3">
      <div className="flex items-start gap-3">
        {/* Complete checkbox: 26px visual, ≥44px tap target */}
        <motion.button
          type="button"
          aria-label={done ? (onReopen ? (locale === 'en' ? 'Reopen task' : 'Вернуть задачу') : (locale === 'en' ? 'Task completed' : 'Задача выполнена')) : (locale === 'en' ? 'Complete task' : 'Выполнить задачу')}
          disabled={done && !onReopen}
          whileTap={reduceMotion || (done && !onReopen) ? undefined : { scale: 0.85 }}
          transition={{ type: 'spring', stiffness: 420, damping: 22 }}
          onClick={complete}
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

        <button
          type="button"
          disabled={done}
          onClick={complete}
          className="min-w-0 flex-1 text-left disabled:cursor-default"
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
              aria-label={priority.label[locale]}
              title={priority.label[locale]}
              className={`h-[6px] w-[6px] shrink-0 rounded-full ${priority.className}`}
            />
            {task.due_at && (
              <span className={`tnum text-[12.5px] ${overdue ? 'font-medium text-danger' : 'text-hint'}`}>
                {formatDueLabel(task.due_at, timeDisplay)}
              </span>
            )}
            {task.estimated_minutes !== null && (
              <span className="tnum rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">
                {task.estimated_minutes} {locale === 'en' ? 'min' : 'мин'}
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
        </button>

        {onEdit && (
          <button
            type="button"
            aria-label={locale === 'en' ? 'Open task details' : 'Открыть детали задачи'}
            onClick={() => {
              haptic('light');
              onEdit(task);
            }}
            className="relative -m-2 mt-[-5px] shrink-0 p-2 text-hint transition-colors active:text-accent-text"
          >
            <ChevronRight size={18} strokeWidth={1.8} />
          </button>
        )}

        {done && onReopen && (
          <button
            type="button"
            aria-label={`${locale === 'en' ? 'Undo completion for' : 'Вернуть задачу'} ${task.title}`}
            onClick={() => {
              haptic('light');
              onReopen(task.id);
            }}
            className="relative -m-2 mt-[-7px] inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-[var(--secondary-bg)] px-3 text-[12px] font-semibold text-ink"
          >
            <RotateCcw size={14} strokeWidth={1.9} />
            {locale === 'en' ? 'Undo' : 'Вернуть'}
          </button>
        )}

        {!done && (
          <button
            type="button"
            aria-label={locale === 'en' ? 'Snooze task' : 'Отложить задачу'}
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

      {estimateSuggestion && !done && (
        <div className="mt-3 rounded-2xl border border-[var(--accent-border)] bg-[var(--accent-soft)] px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span className="tnum min-w-0 flex-1 text-[12.5px] font-semibold text-accent-text">
              {locale === 'en' ? 'Estimate' : 'Оценка'}: {estimateSuggestion.minutes} {locale === 'en' ? 'min' : 'мин'}
            </span>
            <button
              type="button"
              aria-label={`${locale === 'en' ? 'Accept estimate for' : 'Принять оценку для'} ${task.title}`}
              onClick={() => onAcceptEstimate?.(estimateSuggestion.id)}
              className="h-8 rounded-full bg-accent px-3 text-[12px] font-semibold text-white"
            >
              {locale === 'en' ? 'Accept' : 'Принять'}
            </button>
            <button
              type="button"
              aria-label={`${locale === 'en' ? 'Edit estimate for' : 'Изменить оценку для'} ${task.title}`}
              onClick={() => onEditEstimate?.(task, estimateSuggestion)}
              className="h-8 rounded-full bg-[var(--surface-strong)] px-3 text-[12px] font-semibold text-ink"
            >
              {locale === 'en' ? 'Edit' : 'Изменить'}
            </button>
          </div>
          {estimateSuggestion.reason && (
            <p className="mt-1 truncate text-[12px] text-hint">{estimateSuggestion.reason}</p>
          )}
        </div>
      )}

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
              <span className="mr-1 text-[12px] text-hint">{locale === 'en' ? 'Snooze:' : 'Отложить:'}</span>
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
                  {label[locale]}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
