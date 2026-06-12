import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Archive, Brain, Trash2 } from 'lucide-react';
import { useArchiveMemory, useDeleteMemory, useMemories } from '../api/hooks';
import type { Memory } from '../api/types';
import { Chip } from '../components/ui/Chip';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ProgressDots } from '../components/ui/ProgressDots';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatRelative } from '../lib/format';
import { memoryKindLabel, MEMORY_SOURCE_LABELS } from '../lib/labels';
import { haptic } from '../telegram/webapp';

const KIND_FILTERS: { id: string | null; label: string }[] = [
  { id: null, label: 'Все' },
  { id: 'preference', label: 'Предпочтения' },
  { id: 'fact', label: 'Факты' },
  { id: 'project', label: 'Проекты' },
  { id: 'instruction', label: 'Инструкции' },
  { id: 'other', label: 'Другое' },
];

const OTHER_KINDS = new Set(['contact', 'workflow', 'other']);

function MemoryCard({
  memory,
  onArchive,
  onDelete,
}: {
  memory: Memory;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  const sourceLine = [
    memory.source ? MEMORY_SOURCE_LABELS[memory.source] : null,
    memory.last_accessed_at ? `использовано ${formatRelative(memory.last_accessed_at)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="card card-strong px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-0.5 text-[11.5px] font-medium text-accent-text">
          {memoryKindLabel(memory.kind)}
        </span>
        <ProgressDots value={memory.importance} title={`Важность ${memory.importance} из 5`} />
      </div>
      <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink">{memory.text}</p>
      {sourceLine && <p className="mt-1.5 text-[12px] text-hint">{sourceLine}</p>}

      <div className="mt-3 flex items-center justify-end gap-2 border-t border-hairline pt-2.5">
        {confirming ? (
          <>
            <span className="mr-auto text-[13px] text-danger">Удалить навсегда?</span>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="relative rounded-full px-3 py-1.5 text-[13px] font-medium text-hint after:absolute after:-inset-1.5 after:content-['']"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={() => {
                haptic('medium');
                onDelete(memory.id);
              }}
              className="relative rounded-full bg-[var(--danger-soft)] px-3 py-1.5 text-[13px] font-medium text-danger after:absolute after:-inset-1.5 after:content-['']"
            >
              Удалить
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => {
                haptic('light');
                onArchive(memory.id);
              }}
              className="relative flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium text-hint after:absolute after:-inset-1.5 after:content-['']"
            >
              <Archive size={14} />
              В архив
            </button>
            <button
              type="button"
              aria-label="Удалить запись"
              onClick={() => setConfirming(true)}
              className="relative flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium text-hint after:absolute after:-inset-1.5 after:content-['']"
            >
              <Trash2 size={14} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function MemoryPage() {
  const memoriesQuery = useMemories();
  const archiveMemory = useArchiveMemory();
  const deleteMemory = useDeleteMemory();
  const [kind, setKind] = useState<string | null>(null);
  const { show } = useToast();

  const visible = useMemo(() => {
    const items = memoriesQuery.data?.items ?? [];
    if (kind === null) return items;
    if (kind === 'other') return items.filter((m) => OTHER_KINDS.has(m.kind));
    return items.filter((m) => m.kind === kind);
  }, [memoriesQuery.data, kind]);

  const handleArchive = (id: string) =>
    archiveMemory.mutate(id, {
      onSuccess: () => show('Перенесено в архив', 'success'),
      onError: () => show('Не удалось архивировать', 'error'),
    });

  const handleDelete = (id: string) =>
    deleteMemory.mutate(id, {
      onSuccess: () => show('Запись удалена', 'success'),
      onError: () => show('Не удалось удалить', 'error'),
    });

  return (
    <Stagger>
      <Rise>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-1">
          {KIND_FILTERS.map((f) => (
            <Chip key={f.label} label={f.label} active={kind === f.id} onClick={() => setKind(f.id)} />
          ))}
        </div>
      </Rise>

      <Rise className="mt-3">
        {memoriesQuery.isPending ? (
          <SkeletonList count={3} lines={2} />
        ) : memoriesQuery.isError ? (
          <ErrorState message="Не удалось загрузить память." onRetry={() => void memoriesQuery.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Brain}
            title={kind === null ? 'Lumi пока ничего не запомнил' : 'В этой категории пусто'}
            hint="Напиши в чате: «Запомни: рабочие задачи группировать по проектам» — и запись появится здесь."
          />
        ) : (
          <AnimatePresence initial={false}>
            {visible.map((memory) => (
              <motion.div
                key={memory.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97 }}
                transition={{ duration: 0.22, ease: 'easeOut' }}
                className="mb-3"
              >
                <MemoryCard memory={memory} onArchive={handleArchive} onDelete={handleDelete} />
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </Rise>
    </Stagger>
  );
}
