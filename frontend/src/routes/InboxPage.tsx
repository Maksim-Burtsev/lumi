import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Inbox, MailOpen, MailX, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import { qk, useAgentRunAction, useCreateTaskFromThread, useInboxSummary } from '../api/hooks';
import type { InboxCounts } from '../api/types';
import { ThreadCard } from '../components/inbox/ThreadCard';
import { Button } from '../components/ui/Button';
import { Chip } from '../components/ui/Chip';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatRelative } from '../lib/format';
import { inboxCategoryLabel } from '../lib/labels';

const CATEGORY_ORDER: (keyof InboxCounts)[] = [
  'needs_reply',
  'decision_needed',
  'waiting_for_me',
  'fyi',
  'invoice_document',
  'newsletter',
  'ignore',
  'unknown',
];

function InboxSkeleton() {
  return (
    <div aria-hidden>
      <div className="flex gap-2">
        <Skeleton className="h-9 w-24 !rounded-full" />
        <Skeleton className="h-9 w-32 !rounded-full" />
        <Skeleton className="h-9 w-28 !rounded-full" />
      </div>
      <div className="mt-4">
        <SkeletonList count={3} lines={2} />
      </div>
    </div>
  );
}

export default function InboxPage() {
  const inboxQuery = useInboxSummary();
  const createFromThread = useCreateTaskFromThread();
  const [category, setCategory] = useState<string | null>(null);
  const [creatingId, setCreatingId] = useState<string | null>(null);
  const [createdIds, setCreatedIds] = useState<ReadonlySet<string>>(new Set());
  const navigate = useNavigate();
  const { show } = useToast();

  const triageAction = useAgentRunAction({
    start: () => api.runEmailTriage(),
    invalidate: [qk.inbox],
    successMessage: 'Почта разобрана',
    onApiError: (error) => {
      if (error.status === 409 && error.error === 'google_not_connected') {
        show('Google не подключен — загляни в Настройки', 'info');
        return true;
      }
      return false;
    },
  });

  const data = inboxQuery.data;

  const totalCount = useMemo(() => {
    if (!data) return 0;
    return Object.values(data.counts).reduce((sum, n) => sum + n, 0);
  }, [data]);

  const visibleThreads = useMemo(() => {
    const threads = data?.threads ?? [];
    return category ? threads.filter((t) => t.category === category) : threads;
  }, [data, category]);

  const handleCreateTask = (threadId: string) => {
    setCreatingId(threadId);
    createFromThread.mutate(threadId, {
      onSuccess: (result) => {
        setCreatedIds((prev) => new Set(prev).add(threadId));
        show(`Задача создана: ${result.task.title}`, 'success');
      },
      onError: () => show('Не удалось создать задачу', 'error'),
      onSettled: () => setCreatingId(null),
    });
  };

  if (inboxQuery.isPending) return <InboxSkeleton />;
  if (inboxQuery.isError) {
    return <ErrorState message="Не удалось загрузить почту." onRetry={() => void inboxQuery.refetch()} />;
  }

  if (!data || !data.connected) {
    return (
      <Stagger>
        <Rise>
          <EmptyState
            icon={MailX}
            title="Gmail не подключен"
            hint="После подключения Lumi сможет каждое утро показывать, где от тебя ждут ответа."
            action={
              <Button variant="secondary" onClick={() => navigate('/settings')}>
                Открыть настройки
              </Button>
            }
            className="mt-4"
          />
        </Rise>
      </Stagger>
    );
  }

  return (
    <Stagger>
      {/* Run triage */}
      <Rise>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            icon={<Sparkles size={15} />}
            busy={triageAction.isRunning}
            onClick={triageAction.trigger}
          >
            Разобрать почту
          </Button>
          <span className="text-[12.5px] text-hint">
            {data.last_triage_at ? `Последний разбор: ${formatRelative(data.last_triage_at)}` : 'Разбор ещё не запускался'}
          </span>
        </div>
      </Rise>

      {/* Category chips */}
      <Rise>
        <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 py-1">
          <Chip label="Все" count={totalCount} active={category === null} onClick={() => setCategory(null)} />
          {CATEGORY_ORDER.filter((key) => data.counts[key] > 0).map((key) => (
            <Chip
              key={key}
              label={inboxCategoryLabel(key)}
              count={data.counts[key]}
              active={category === key}
              onClick={() => setCategory(category === key ? null : key)}
            />
          ))}
        </div>
      </Rise>

      {/* Threads */}
      <Rise className="mt-3">
        {visibleThreads.length === 0 ? (
          category === null ? (
            <EmptyState
              icon={MailOpen}
              title="Писем для разбора нет"
              hint="Запусти «Разобрать почту» — Lumi посмотрит свежие письма и разложит их по полочкам."
            />
          ) : (
            <EmptyState
              icon={Inbox}
              title="В этой категории пусто"
              hint="Выбери другую категорию или запусти разбор почты."
            />
          )
        ) : (
          <div className="flex flex-col gap-2.5">
            {visibleThreads.map((thread) => (
              <ThreadCard
                key={thread.id}
                thread={thread}
                onCreateTask={handleCreateTask}
                creating={creatingId === thread.id}
                created={createdIds.has(thread.id)}
              />
            ))}
          </div>
        )}
      </Rise>
    </Stagger>
  );
}
