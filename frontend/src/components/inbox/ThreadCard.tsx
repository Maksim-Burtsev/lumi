import { Check, Plus, Sparkles } from 'lucide-react';
import type { EmailThread } from '../../api/types';
import { formatRelative } from '../../lib/format';
import { inboxCategoryLabel } from '../../lib/labels';
import { useAppLocale } from '../../lib/useAppLocale';
import { useTimeDisplay } from '../../lib/useTimeDisplay';
import { ProgressDots } from '../ui/ProgressDots';
import { Button } from '../ui/Button';

interface ThreadCardProps {
  thread: EmailThread;
  onCreateTask: (id: string) => void;
  creating?: boolean;
  created?: boolean;
}

export function ThreadCard({ thread, onCreateTask, creating = false, created = false }: ThreadCardProps) {
  const locale = useAppLocale();
  const timeDisplay = useTimeDisplay();
  const preview = thread.summary ?? thread.snippet;
  const copy = locale === 'en'
    ? {
        unknownSender: 'No sender',
        importance: `Importance ${thread.importance} of 5`,
        created: 'Created',
        createTask: 'Create task',
        task: 'Task',
      }
    : {
        unknownSender: 'Без отправителя',
        importance: `Важность ${thread.importance} из 5`,
        created: 'Создана',
        createTask: 'Создать задачу',
        task: 'Задача',
      };

  return (
    <div className="card card-strong px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 truncate text-[14px] font-semibold text-ink">{thread.sender ?? copy.unknownSender}</p>
        <span className="tnum shrink-0 text-[12px] text-hint">{formatRelative(thread.last_message_at, timeDisplay)}</span>
      </div>
      {thread.subject && <p className="mt-0.5 truncate text-[13.5px] text-ink">{thread.subject}</p>}
      {preview && <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-hint">{preview}</p>}

      {thread.suggested_action && (
        <p className="mt-2 flex items-start gap-1.5 text-[12.5px] leading-snug text-accent-text">
          <Sparkles size={13} className="mt-0.5 shrink-0" />
          <span>{thread.suggested_action}</span>
        </p>
      )}

      <div className="mt-3 flex items-center gap-2.5">
        <ProgressDots value={thread.importance} title={copy.importance} />
        <span className="rounded-full bg-[var(--secondary-bg)] px-2 py-px text-[11.5px] text-hint">
          {inboxCategoryLabel(thread.category, locale)}
        </span>
        <span className="flex-1" />
        <Button
          size="sm"
          variant={created ? 'ghost' : 'secondary'}
          busy={creating}
          disabled={created}
          icon={created ? <Check size={14} className="text-success" /> : <Plus size={14} />}
          onClick={() => onCreateTask(thread.id)}
        >
          {created ? copy.created : copy.createTask}
        </Button>
      </div>

      {thread.task_candidate && !created && (
        <p className="mt-2 text-[12px] text-hint">
          {copy.task}: <span className="text-ink">{thread.task_candidate.title}</span>
        </p>
      )}
    </div>
  );
}
