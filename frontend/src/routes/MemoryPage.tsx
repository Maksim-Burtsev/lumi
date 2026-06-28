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
import type { AppLocale } from '../lib/i18n';
import { memoryKindLabel, memorySourceLabel } from '../lib/labels';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';
import { haptic } from '../telegram/webapp';

const KIND_FILTERS: { id: string | null; label: Record<AppLocale, string> }[] = [
  { id: null, label: { en: 'All', ru: 'Все' } },
  { id: 'preference', label: { en: 'Preferences', ru: 'Предпочтения' } },
  { id: 'fact', label: { en: 'Facts', ru: 'Факты' } },
  { id: 'project', label: { en: 'Projects', ru: 'Проекты' } },
  { id: 'instruction', label: { en: 'Instructions', ru: 'Инструкции' } },
  { id: 'other', label: { en: 'Other', ru: 'Другое' } },
];

const COPY: Record<AppLocale, {
  used: string;
  importance: (value: number) => string;
  deleteForever: string;
  cancel: string;
  delete: string;
  archive: string;
  deleteRecord: string;
  archived: string;
  archiveFailed: string;
  deleted: string;
  deleteFailed: string;
  loadFailed: string;
  emptyTitle: string;
  emptyCategory: string;
  emptyHint: string;
}> = {
  en: {
    used: 'used',
    importance: (value) => `Importance ${value} of 5`,
    deleteForever: 'Delete forever?',
    cancel: 'Cancel',
    delete: 'Delete',
    archive: 'Archive',
    deleteRecord: 'Delete memory',
    archived: 'Archived',
    archiveFailed: 'Could not archive',
    deleted: 'Memory deleted',
    deleteFailed: 'Could not delete',
    loadFailed: 'Could not load memory.',
    emptyTitle: 'Lumi has not remembered anything yet',
    emptyCategory: 'This category is empty',
    emptyHint: 'Write in chat: "Remember: group work tasks by project" and it will appear here.',
  },
  ru: {
    used: 'использовано',
    importance: (value) => `Важность ${value} из 5`,
    deleteForever: 'Удалить навсегда?',
    cancel: 'Отмена',
    delete: 'Удалить',
    archive: 'В архив',
    deleteRecord: 'Удалить запись',
    archived: 'Перенесено в архив',
    archiveFailed: 'Не удалось архивировать',
    deleted: 'Запись удалена',
    deleteFailed: 'Не удалось удалить',
    loadFailed: 'Не удалось загрузить память.',
    emptyTitle: 'Lumi пока ничего не запомнил',
    emptyCategory: 'В этой категории пусто',
    emptyHint: 'Напиши в чате: «Запомни: рабочие задачи группировать по проектам» — и запись появится здесь.',
  },
};

const OTHER_KINDS = new Set(['contact', 'workflow', 'other']);

function MemoryCard({
  memory,
  onArchive,
  onDelete,
  locale,
}: {
  memory: Memory;
  onArchive: (id: string) => void;
  onDelete: (id: string) => void;
  locale: AppLocale;
}) {
  const [confirming, setConfirming] = useState(false);
  const timeDisplay = useTimeDisplay();
  const copy = COPY[locale];

  const sourceLine = [
    memory.source ? memorySourceLabel(memory.source, locale) : null,
    memory.last_accessed_at ? `${copy.used} ${formatRelative(memory.last_accessed_at, timeDisplay)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="card card-strong px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-0.5 text-[11.5px] font-medium text-accent-text">
          {memoryKindLabel(memory.kind, locale)}
        </span>
        <ProgressDots value={memory.importance} title={copy.importance(memory.importance)} />
      </div>
      <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink">{memory.text}</p>
      {sourceLine && <p className="mt-1.5 text-[12px] text-hint">{sourceLine}</p>}

      <div className="mt-3 flex items-center justify-end gap-2 border-t border-hairline pt-2.5">
        {confirming ? (
          <>
            <span className="mr-auto text-[13px] text-danger">{copy.deleteForever}</span>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="relative rounded-full px-3 py-1.5 text-[13px] font-medium text-hint after:absolute after:-inset-1.5 after:content-['']"
            >
              {copy.cancel}
            </button>
            <button
              type="button"
              onClick={() => {
                haptic('medium');
                onDelete(memory.id);
              }}
              className="relative rounded-full bg-[var(--danger-soft)] px-3 py-1.5 text-[13px] font-medium text-danger after:absolute after:-inset-1.5 after:content-['']"
            >
              {copy.delete}
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
              {copy.archive}
            </button>
            <button
              type="button"
              aria-label={copy.deleteRecord}
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
  const locale = useAppLocale();
  const copy = COPY[locale];

  const visible = useMemo(() => {
    const items = memoriesQuery.data?.items ?? [];
    if (kind === null) return items;
    if (kind === 'other') return items.filter((m) => OTHER_KINDS.has(m.kind));
    return items.filter((m) => m.kind === kind);
  }, [memoriesQuery.data, kind]);

  const handleArchive = (id: string) =>
    archiveMemory.mutate(id, {
      onSuccess: () => show(copy.archived, 'success'),
      onError: () => show(copy.archiveFailed, 'error'),
    });

  const handleDelete = (id: string) =>
    deleteMemory.mutate(id, {
      onSuccess: () => show(copy.deleted, 'success'),
      onError: () => show(copy.deleteFailed, 'error'),
    });

  return (
    <Stagger>
      <Rise>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-1">
          {KIND_FILTERS.map((f) => (
            <Chip key={f.id ?? 'all'} label={f.label[locale]} active={kind === f.id} onClick={() => setKind(f.id)} />
          ))}
        </div>
      </Rise>

      <Rise className="mt-3">
        {memoriesQuery.isPending ? (
          <SkeletonList count={3} lines={2} />
        ) : memoriesQuery.isError ? (
          <ErrorState message={copy.loadFailed} onRetry={() => void memoriesQuery.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Brain}
            title={kind === null ? copy.emptyTitle : copy.emptyCategory}
            hint={copy.emptyHint}
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
                <MemoryCard memory={memory} onArchive={handleArchive} onDelete={handleDelete} locale={locale} />
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </Rise>
    </Stagger>
  );
}
