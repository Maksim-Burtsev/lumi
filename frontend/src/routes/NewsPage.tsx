import { useState } from 'react';
import { Newspaper, Plus, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import {
  qk,
  useAgentRunAction,
  useCreateNewsTopic,
  useNewsDigests,
  useNewsTopics,
  usePatchNewsTopic,
} from '../api/hooks';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { FieldLabel, Input } from '../components/ui/Field';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Sheet } from '../components/ui/Sheet';
import { SkeletonList } from '../components/ui/Skeleton';
import { Switch } from '../components/ui/Switch';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatRelative } from '../lib/format';

function AddTopicSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [title, setTitle] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createTopic = useCreateNewsTopic();
  const { show } = useToast();

  const submit = () => {
    const t = title.trim();
    const q = query.trim();
    if (!t || !q) {
      setError('Заполни название и поисковый запрос');
      return;
    }
    setError(null);
    createTopic.mutate(
      { title: t, query: q },
      {
        onSuccess: () => {
          show('Тема добавлена', 'success');
          setTitle('');
          setQuery('');
          onClose();
        },
        onError: () => show('Не удалось добавить тему', 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title="Новая тема">
      <label className="block">
        <FieldLabel>Название</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder="AI-агенты" />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Поисковый запрос</FieldLabel>
        <Input value={query} onChange={setQuery} placeholder="AI agents OR LLM orchestration" />
      </label>
      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createTopic.isPending} onClick={submit}>
        Добавить тему
      </Button>
    </Sheet>
  );
}

export default function NewsPage() {
  const topicsQuery = useNewsTopics();
  const digestsQuery = useNewsDigests();
  const patchTopic = usePatchNewsTopic();
  const [sheetOpen, setSheetOpen] = useState(false);
  const { show } = useToast();

  const digestAction = useAgentRunAction({
    start: () => api.runNewsDigest(),
    invalidate: [qk.digests],
    successMessage: 'Дайджест готов',
  });

  return (
    <Stagger>
      {/* Run digest */}
      <Rise>
        <div className="flex flex-wrap gap-2.5">
          <Button
            variant="primary"
            icon={<Sparkles size={15} />}
            busy={digestAction.isRunning}
            onClick={digestAction.trigger}
          >
            Собрать дайджест
          </Button>
          <Button variant="ghost" icon={<Plus size={15} />} onClick={() => setSheetOpen(true)}>
            Добавить тему
          </Button>
        </div>
      </Rise>

      {/* Topics */}
      <Rise>
        <SectionHeader title="Темы" />
        {topicsQuery.isPending ? (
          <SkeletonList count={2} lines={1} />
        ) : topicsQuery.isError ? (
          <ErrorState message="Не удалось загрузить темы." onRetry={() => void topicsQuery.refetch()} />
        ) : (topicsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Newspaper}
            title="Пока нет тем"
            hint="Добавь тему — Lumi будет собирать по ней утренний дайджест."
            action={
              <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setSheetOpen(true)}>
                Добавить тему
              </Button>
            }
          />
        ) : (
          <Card className="card-strong divide-y divide-[var(--hairline)] !p-0">
            {topicsQuery.data.items.map((topic) => (
              <div key={topic.id} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-[14.5px] font-medium ${topic.enabled ? 'text-ink' : 'text-hint'}`}>
                    {topic.title}
                  </p>
                  <p className="truncate text-[12px] text-hint">{topic.query}</p>
                </div>
                <Switch
                  checked={topic.enabled}
                  aria-label={`Тема «${topic.title}»`}
                  disabled={patchTopic.isPending}
                  onChange={(enabled) =>
                    patchTopic.mutate(
                      { id: topic.id, input: { enabled } },
                      { onError: () => show('Не удалось обновить тему', 'error') },
                    )
                  }
                />
              </div>
            ))}
          </Card>
        )}
      </Rise>

      {/* Digests */}
      <Rise>
        <SectionHeader title="Дайджесты" />
        {digestsQuery.isPending ? (
          <SkeletonList count={2} lines={4} />
        ) : digestsQuery.isError ? (
          <ErrorState message="Не удалось загрузить дайджесты." onRetry={() => void digestsQuery.refetch()} />
        ) : (digestsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Newspaper}
            title="Дайджестов ещё нет"
            hint="Нажми «Собрать дайджест» — Lumi пройдётся по темам и соберёт главное."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {digestsQuery.data.items.map((digest, index) => (
              <Card key={digest.id} className={`px-5 py-4 ${index === 0 ? 'card-strong' : ''}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="min-w-0 truncate text-[15px] font-semibold text-ink">{digest.title}</h3>
                  <span className="tnum shrink-0 text-[12px] text-hint">{formatRelative(digest.created_at)}</span>
                </div>
                <p className="mt-2.5 whitespace-pre-wrap text-[13.5px] leading-[1.65] text-ink">{digest.digest_text}</p>
              </Card>
            ))}
          </div>
        )}
      </Rise>

      <AddTopicSheet open={sheetOpen} onClose={() => setSheetOpen(false)} />
    </Stagger>
  );
}
