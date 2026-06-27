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
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';

const COPY = {
  en: {
    fillTopic: 'Fill in title and search query',
    topicAdded: 'Topic added',
    addTopicFailed: 'Could not add topic',
    newTopic: 'New topic',
    title: 'Title',
    titlePlaceholder: 'AI agents',
    searchQuery: 'Search query',
    addTopic: 'Add topic',
    digestReady: 'Digest ready',
    buildDigest: 'Build digest',
    topics: 'Topics',
    topicsLoadFailed: 'Could not load topics.',
    noTopics: 'No topics yet',
    noTopicsHint: 'Add a topic. Lumi will use it for the morning digest.',
    topicToggle: (title: string) => `Topic "${title}"`,
    topicUpdateFailed: 'Could not update topic',
    digests: 'Digests',
    digestsLoadFailed: 'Could not load digests.',
    noDigests: 'No digests yet',
    noDigestsHint: 'Tap "Build digest". Lumi will scan topics and collect the highlights.',
  },
  ru: {
    fillTopic: 'Заполни название и поисковый запрос',
    topicAdded: 'Тема добавлена',
    addTopicFailed: 'Не удалось добавить тему',
    newTopic: 'Новая тема',
    title: 'Название',
    titlePlaceholder: 'AI-агенты',
    searchQuery: 'Поисковый запрос',
    addTopic: 'Добавить тему',
    digestReady: 'Дайджест готов',
    buildDigest: 'Собрать дайджест',
    topics: 'Темы',
    topicsLoadFailed: 'Не удалось загрузить темы.',
    noTopics: 'Пока нет тем',
    noTopicsHint: 'Добавь тему — Lumi будет собирать по ней утренний дайджест.',
    topicToggle: (title: string) => `Тема «${title}»`,
    topicUpdateFailed: 'Не удалось обновить тему',
    digests: 'Дайджесты',
    digestsLoadFailed: 'Не удалось загрузить дайджесты.',
    noDigests: 'Дайджестов ещё нет',
    noDigestsHint: 'Нажми «Собрать дайджест» — Lumi пройдётся по темам и соберёт главное.',
  },
} satisfies Record<AppLocale, Record<string, unknown>>;

function AddTopicSheet({ open, onClose, locale }: { open: boolean; onClose: () => void; locale: AppLocale }) {
  const copy = COPY[locale];
  const [title, setTitle] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createTopic = useCreateNewsTopic();
  const { show } = useToast();

  const submit = () => {
    const t = title.trim();
    const q = query.trim();
    if (!t || !q) {
      setError(copy.fillTopic as string);
      return;
    }
    setError(null);
    createTopic.mutate(
      { title: t, query: q },
      {
        onSuccess: () => {
          show(copy.topicAdded as string, 'success');
          setTitle('');
          setQuery('');
          onClose();
        },
        onError: () => show(copy.addTopicFailed as string, 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.newTopic as string}>
      <label className="block">
        <FieldLabel>{copy.title as string}</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder={copy.titlePlaceholder as string} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.searchQuery as string}</FieldLabel>
        <Input value={query} onChange={setQuery} placeholder="AI agents OR LLM orchestration" />
      </label>
      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createTopic.isPending} onClick={submit}>
        {copy.addTopic as string}
      </Button>
    </Sheet>
  );
}

export default function NewsPage() {
  const locale = useAppLocale();
  const timeDisplay = useTimeDisplay();
  const copy = COPY[locale];
  const topicsQuery = useNewsTopics();
  const digestsQuery = useNewsDigests();
  const patchTopic = usePatchNewsTopic();
  const [sheetOpen, setSheetOpen] = useState(false);
  const { show } = useToast();

  const digestAction = useAgentRunAction({
    start: () => api.runNewsDigest(),
    invalidate: [qk.digests],
    successMessage: copy.digestReady as string,
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
            {copy.buildDigest as string}
          </Button>
          <Button variant="ghost" icon={<Plus size={15} />} onClick={() => setSheetOpen(true)}>
            {copy.addTopic as string}
          </Button>
        </div>
      </Rise>

      {/* Topics */}
      <Rise>
        <SectionHeader title={copy.topics as string} />
        {topicsQuery.isPending ? (
          <SkeletonList count={2} lines={1} />
        ) : topicsQuery.isError ? (
          <ErrorState message={copy.topicsLoadFailed as string} onRetry={() => void topicsQuery.refetch()} />
        ) : (topicsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Newspaper}
            title={copy.noTopics as string}
            hint={copy.noTopicsHint as string}
            action={
              <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setSheetOpen(true)}>
                {copy.addTopic as string}
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
                  aria-label={(copy.topicToggle as (title: string) => string)(topic.title)}
                  disabled={patchTopic.isPending}
                  onChange={(enabled) =>
                    patchTopic.mutate(
                      { id: topic.id, input: { enabled } },
                      { onError: () => show(copy.topicUpdateFailed as string, 'error') },
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
        <SectionHeader title={copy.digests as string} />
        {digestsQuery.isPending ? (
          <SkeletonList count={2} lines={4} />
        ) : digestsQuery.isError ? (
          <ErrorState message={copy.digestsLoadFailed as string} onRetry={() => void digestsQuery.refetch()} />
        ) : (digestsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Newspaper}
            title={copy.noDigests as string}
            hint={copy.noDigestsHint as string}
          />
        ) : (
          <div className="flex flex-col gap-3">
            {digestsQuery.data.items.map((digest, index) => (
              <Card key={digest.id} className={`px-5 py-4 ${index === 0 ? 'card-strong' : ''}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="min-w-0 truncate text-[15px] font-semibold text-ink">{digest.title}</h3>
                  <span className="tnum shrink-0 text-[12px] text-hint">{formatRelative(digest.created_at, timeDisplay)}</span>
                </div>
                <p className="mt-2.5 whitespace-pre-wrap text-[13.5px] leading-[1.65] text-ink">{digest.digest_text}</p>
              </Card>
            ))}
          </div>
        )}
      </Rise>

      <AddTopicSheet open={sheetOpen} onClose={() => setSheetOpen(false)} locale={locale} />
    </Stagger>
  );
}
