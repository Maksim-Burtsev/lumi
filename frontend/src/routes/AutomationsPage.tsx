import { useMemo, useState } from 'react';
import { AlertCircle, Play, Plus, Zap } from 'lucide-react';
import { api } from '../api/client';
import { qk, useAgentRunAction, useAutomations, useCreateAutomation, usePatchAutomation } from '../api/hooks';
import type { Automation, AutomationType } from '../api/types';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { FieldLabel, Input, Select, Textarea } from '../components/ui/Field';
import { Sheet } from '../components/ui/Sheet';
import { SkeletonList } from '../components/ui/Skeleton';
import { Switch } from '../components/ui/Switch';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { runTypeIcon } from '../components/runs/RunBadge';
import { cronPresets, humanizeCron } from '../lib/cron';
import { formatRelative } from '../lib/format';
import type { AppLocale } from '../lib/i18n';
import { automationTypeLabel } from '../lib/labels';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';

const AUTOMATION_TYPES: AutomationType[] = [
  'morning_brief',
  'news_digest',
  'email_triage',
  'daily_planning',
  'calendar_sync',
  'task_review',
  'custom_prompt',
];

const COPY: Record<AppLocale, {
  runSuccess: (title: string) => string;
  updateFailed: string;
  toggle: (title: string) => string;
  lastRun: string;
  nextRun: string;
  run: string;
  nameRequired: string;
  promptRequired: string;
  dateRequired: string;
  cronInvalid: string;
  configObject: string;
  configInvalid: string;
  created: string;
  createFailed: string;
  newAutomation: string;
  type: string;
  title: string;
  prompt: string;
  promptPlaceholder: string;
  resultFormat: string;
  formatText: string;
  formatMarkdown: string;
  formatHtml: string;
  whenToRun: string;
  scheduled: string;
  once: string;
  advanced: string;
  create: string;
  loadFailed: string;
  emptyTitle: string;
  emptyHint: string;
}> = {
  en: {
    runSuccess: (title) => `"${title}" is done`,
    updateFailed: 'Could not update automation',
    toggle: (title) => `Automation "${title}"`,
    lastRun: 'Last run',
    nextRun: 'Next',
    run: 'Run',
    nameRequired: 'Give the automation a name',
    promptRequired: 'Write a prompt: what Lumi should do',
    dateRequired: 'Choose run date and time',
    cronInvalid: 'Cron must have 5 fields, for example "30 8 * * 1-5"',
    configObject: 'Config must be a JSON object',
    configInvalid: 'Config: invalid JSON',
    created: 'Automation created',
    createFailed: 'Could not create automation',
    newAutomation: 'New automation',
    type: 'Type',
    title: 'Title',
    prompt: 'Prompt: what to do',
    promptPlaceholder: 'Summarize the AI assistant market: key players, recent funding rounds, trends',
    resultFormat: 'Result format',
    formatText: 'Message in chat',
    formatMarkdown: 'Markdown file',
    formatHtml: 'HTML document',
    whenToRun: 'When to run',
    scheduled: 'Scheduled',
    once: 'Once',
    advanced: 'Advanced settings (JSON)',
    create: 'Create',
    loadFailed: 'Could not load automations.',
    emptyTitle: 'No automations yet',
    emptyHint: 'Create a workflow, for example a weekday morning news digest at 08:30.',
  },
  ru: {
    runSuccess: (title) => `«${title}» — готово`,
    updateFailed: 'Не удалось обновить автоматизацию',
    toggle: (title) => `Автоматизация «${title}»`,
    lastRun: 'Последний запуск',
    nextRun: 'Следующий',
    run: 'Запустить',
    nameRequired: 'Дай автоматизации название',
    promptRequired: 'Напиши промпт — что Lumi должна сделать',
    dateRequired: 'Выбери дату и время запуска',
    cronInvalid: 'Cron-строка должна состоять из 5 полей, например «30 8 * * 1-5»',
    configObject: 'Config должен быть JSON-объектом',
    configInvalid: 'Config: некорректный JSON',
    created: 'Автоматизация создана',
    createFailed: 'Не удалось создать автоматизацию',
    newAutomation: 'Новая автоматизация',
    type: 'Тип',
    title: 'Название',
    prompt: 'Промпт — что сделать',
    promptPlaceholder: 'Собери сводку по рынку AI-ассистентов: ключевые игроки, последние раунды, тренды',
    resultFormat: 'Формат результата',
    formatText: 'Сообщение в чат',
    formatMarkdown: 'Markdown-файл',
    formatHtml: 'HTML-документ',
    whenToRun: 'Когда запускать',
    scheduled: 'По расписанию',
    once: 'Один раз',
    advanced: 'Расширенные настройки (JSON)',
    create: 'Создать',
    loadFailed: 'Не удалось загрузить автоматизации.',
    emptyTitle: 'Автоматизаций пока нет',
    emptyHint: 'Создай сценарий — например, утренний дайджест новостей по будням в 08:30.',
  },
};

function AutomationCard({ automation, locale }: { automation: Automation; locale: AppLocale }) {
  const patchAutomation = usePatchAutomation();
  const { show } = useToast();
  const Icon = runTypeIcon(automation.type);
  const timeDisplay = useTimeDisplay();
  const copy = COPY[locale];

  const runAction = useAgentRunAction({
    start: () => api.runAutomation(automation.id),
    invalidate: [qk.automations],
    successMessage: copy.runSuccess(automation.title),
  });

  return (
    <div className="card card-strong px-4 py-3.5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)]">
          <Icon size={16} className="text-accent-text" strokeWidth={1.9} />
        </div>
        <div className="min-w-0 flex-1">
          <p className={`text-[14.5px] font-medium leading-snug ${automation.enabled ? 'text-ink' : 'text-hint'}`}>
            {automation.title}
          </p>
          <p className="tnum mt-0.5 text-[12.5px] text-hint">
            {humanizeCron(automation.cron_expression, locale)} · {automationTypeLabel(automation.type, locale)}
          </p>
        </div>
        <Switch
          checked={automation.enabled}
          aria-label={copy.toggle(automation.title)}
          disabled={patchAutomation.isPending}
          onChange={(enabled) =>
            patchAutomation.mutate(
              { id: automation.id, input: { enabled } },
              { onError: () => show(copy.updateFailed, 'error') },
            )
          }
        />
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-hairline pt-3">
        <div className="tnum min-w-0 text-[12px] leading-relaxed text-hint">
          <p className="truncate">
            {copy.lastRun}: {automation.last_run_at ? formatRelative(automation.last_run_at, timeDisplay) : '—'}
          </p>
          <p className="truncate">
            {copy.nextRun}: {automation.next_run_at ? formatRelative(automation.next_run_at, timeDisplay) : '—'}
          </p>
        </div>
        <Button size="sm" variant="secondary" icon={<Play size={13} />} busy={runAction.isRunning} onClick={runAction.trigger}>
          {copy.run}
        </Button>
      </div>

      {automation.failure_count > 0 && automation.last_error && (
        <p className="mt-2.5 flex items-start gap-1.5 text-[12px] leading-snug text-danger">
          <AlertCircle size={13} className="mt-0.5 shrink-0" />
          <span className="min-w-0">{automation.last_error}</span>
        </p>
      )}
    </div>
  );
}

function CreateAutomationSheet({
  open,
  onClose,
  defaultTimezone,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  defaultTimezone?: string;
  locale: AppLocale;
}) {
  const [type, setType] = useState<AutomationType>('news_digest');
  const [title, setTitle] = useState('');
  const [presetId, setPresetId] = useState<string>('morning-8');
  const [customCron, setCustomCron] = useState('');
  const [configText, setConfigText] = useState('');
  const [prompt, setPrompt] = useState('');
  const [format, setFormat] = useState<'text' | 'md' | 'html'>('text');
  const [scheduleMode, setScheduleMode] = useState<'cron' | 'once'>('cron');
  const [runAt, setRunAt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createAutomation = useCreateAutomation();
  const { show } = useToast();
  const copy = COPY[locale];
  const presets = useMemo(() => cronPresets(locale), [locale]);
  const typeOptions = useMemo(
    () => AUTOMATION_TYPES.map((value) => ({ value, label: automationTypeLabel(value, locale) })),
    [locale],
  );

  const preset = presets.find((p) => p.id === presetId) ?? presets[0];
  const cronExpression = preset.expression ?? customCron.trim();

  const submit = () => {
    const t = title.trim();
    if (!t) {
      setError(copy.nameRequired);
      return;
    }
    if (type === 'custom_prompt' && !prompt.trim()) {
      setError(copy.promptRequired);
      return;
    }
    if (scheduleMode === 'once') {
      if (!runAt) {
        setError(copy.dateRequired);
        return;
      }
    } else if (!cronExpression || cronExpression.split(/\s+/).length !== 5) {
      setError(copy.cronInvalid);
      return;
    }
    let config: Record<string, unknown> | undefined;
    if (configText.trim()) {
      try {
        const parsed: unknown = JSON.parse(configText);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setError(copy.configObject);
          return;
        }
        config = parsed as Record<string, unknown>;
      } catch {
        setError(copy.configInvalid);
        return;
      }
    }
    setError(null);
    const mergedConfig: Record<string, unknown> = { ...(config ?? {}) };
    if (type === 'custom_prompt') {
      mergedConfig.prompt = prompt.trim();
      mergedConfig.format = format;
      mergedConfig.title = t;
    }
    createAutomation.mutate(
      {
        type,
        title: t,
        cron_expression: scheduleMode === 'once' ? '' : cronExpression,
        ...(scheduleMode === 'once' ? { run_at: new Date(runAt).toISOString() } : {}),
        ...(defaultTimezone ? { timezone: defaultTimezone } : {}),
        ...(Object.keys(mergedConfig).length ? { config: mergedConfig } : {}),
        enabled: true,
      },
      {
        onSuccess: () => {
          show(copy.created, 'success');
          setTitle('');
          setConfigText('');
          onClose();
        },
        onError: () => show(copy.createFailed, 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.newAutomation}>
      <label className="block">
        <FieldLabel>{copy.type}</FieldLabel>
        <Select value={type} onChange={(v) => setType(v as AutomationType)} options={typeOptions} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.title}</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder={automationTypeLabel(type, locale)} />
      </label>

      {type === 'custom_prompt' && (
        <>
          <label className="mt-4 block">
            <FieldLabel>{copy.prompt}</FieldLabel>
            <Textarea
              value={prompt}
              onChange={setPrompt}
              rows={4}
              placeholder={copy.promptPlaceholder}
            />
          </label>
          <label className="mt-4 block">
            <FieldLabel>{copy.resultFormat}</FieldLabel>
            <Select
              value={format}
              onChange={(v) => setFormat(v as 'text' | 'md' | 'html')}
              options={[
                { value: 'text', label: copy.formatText },
                { value: 'md', label: copy.formatMarkdown },
                { value: 'html', label: copy.formatHtml },
              ]}
            />
          </label>
        </>
      )}

      <div className="mt-4">
        <FieldLabel>{copy.whenToRun}</FieldLabel>
        <div className="mb-2.5 flex gap-1.5">
          {([['cron', copy.scheduled], ['once', copy.once]] as const).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setScheduleMode(mode)}
              className={`min-h-[40px] flex-1 rounded-xl border px-3 text-[13.5px] transition-colors ${
                scheduleMode === mode
                  ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] font-medium text-ink'
                  : 'border-hairline text-hint'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {scheduleMode === 'once' ? (
          <input
            type="datetime-local"
            value={runAt}
            onChange={(e) => setRunAt(e.target.value)}
            className="h-11 w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none"
          />
        ) : (
          <>
            <div className="flex flex-col gap-1.5">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPresetId(p.id)}
                  className={`flex min-h-[44px] items-center justify-between rounded-xl border px-3.5 py-2 text-left text-[13.5px] transition-colors ${
                    presetId === p.id
                      ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-ink'
                      : 'border-hairline bg-transparent text-hint'
                  }`}
                >
                  <span>{p.label}</span>
                  {p.expression && <span className="tnum font-mono text-[11.5px] text-hint">{p.expression}</span>}
                </button>
              ))}
            </div>
            {preset.expression === null && (
              <div className="mt-2.5">
                <Input value={customCron} onChange={setCustomCron} placeholder="30 8 * * 1-5" />
                {customCron.trim() && (
                  <p className="mt-1.5 text-[12px] text-hint">→ {humanizeCron(customCron.trim(), locale)}</p>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer select-none text-[13px] font-medium text-hint">
          {copy.advanced}
        </summary>
        <div className="mt-2.5">
          <Textarea value={configText} onChange={setConfigText} rows={4} mono placeholder='{ "limit": 10 }' />
        </div>
      </details>

      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createAutomation.isPending} onClick={submit}>
        {copy.create}
      </Button>
    </Sheet>
  );
}

export default function AutomationsPage() {
  const automationsQuery = useAutomations();
  const [sheetOpen, setSheetOpen] = useState(false);
  const locale = useAppLocale();
  const copy = COPY[locale];

  return (
    <Stagger>
      <Rise>
        <Button variant="ghost" icon={<Plus size={15} />} onClick={() => setSheetOpen(true)}>
          {copy.newAutomation}
        </Button>
      </Rise>

      <Rise className="mt-4">
        {automationsQuery.isPending ? (
          <SkeletonList count={3} lines={2} />
        ) : automationsQuery.isError ? (
          <ErrorState message={copy.loadFailed} onRetry={() => void automationsQuery.refetch()} />
        ) : (automationsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Zap}
            title={copy.emptyTitle}
            hint={copy.emptyHint}
            action={
              <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setSheetOpen(true)}>
                {copy.create}
              </Button>
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {automationsQuery.data.items.map((automation) => (
              <AutomationCard key={automation.id} automation={automation} locale={locale} />
            ))}
          </div>
        )}
      </Rise>

      <CreateAutomationSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        defaultTimezone={Intl.DateTimeFormat().resolvedOptions().timeZone}
        locale={locale}
      />
    </Stagger>
  );
}
