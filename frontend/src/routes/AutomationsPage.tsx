import { useState } from 'react';
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
import { CRON_PRESETS, humanizeCron } from '../lib/cron';
import { formatRelative } from '../lib/format';
import { automationTypeLabel, AUTOMATION_TYPE_LABELS } from '../lib/labels';

function AutomationCard({ automation }: { automation: Automation }) {
  const patchAutomation = usePatchAutomation();
  const { show } = useToast();
  const Icon = runTypeIcon(automation.type);

  const runAction = useAgentRunAction({
    start: () => api.runAutomation(automation.id),
    invalidate: [qk.automations],
    successMessage: `«${automation.title}» — готово`,
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
            {humanizeCron(automation.cron_expression)} · {automationTypeLabel(automation.type)}
          </p>
        </div>
        <Switch
          checked={automation.enabled}
          aria-label={`Автоматизация «${automation.title}»`}
          disabled={patchAutomation.isPending}
          onChange={(enabled) =>
            patchAutomation.mutate(
              { id: automation.id, input: { enabled } },
              { onError: () => show('Не удалось обновить автоматизацию', 'error') },
            )
          }
        />
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-hairline pt-3">
        <div className="tnum min-w-0 text-[12px] leading-relaxed text-hint">
          <p className="truncate">
            Последний запуск: {automation.last_run_at ? formatRelative(automation.last_run_at) : '—'}
          </p>
          <p className="truncate">
            Следующий: {automation.next_run_at ? formatRelative(automation.next_run_at) : '—'}
          </p>
        </div>
        <Button size="sm" variant="secondary" icon={<Play size={13} />} busy={runAction.isRunning} onClick={runAction.trigger}>
          Запустить
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

const TYPE_OPTIONS: { value: AutomationType; label: string }[] = (
  Object.entries(AUTOMATION_TYPE_LABELS) as [AutomationType, string][]
).map(([value, label]) => ({ value, label }));

function CreateAutomationSheet({
  open,
  onClose,
  defaultTimezone,
}: {
  open: boolean;
  onClose: () => void;
  defaultTimezone?: string;
}) {
  const [type, setType] = useState<AutomationType>('news_digest');
  const [title, setTitle] = useState('');
  const [presetId, setPresetId] = useState<string>(CRON_PRESETS[0].id);
  const [customCron, setCustomCron] = useState('');
  const [configText, setConfigText] = useState('');
  const [prompt, setPrompt] = useState('');
  const [format, setFormat] = useState<'text' | 'md' | 'html'>('text');
  const [scheduleMode, setScheduleMode] = useState<'cron' | 'once'>('cron');
  const [runAt, setRunAt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createAutomation = useCreateAutomation();
  const { show } = useToast();

  const preset = CRON_PRESETS.find((p) => p.id === presetId) ?? CRON_PRESETS[0];
  const cronExpression = preset.expression ?? customCron.trim();

  const submit = () => {
    const t = title.trim();
    if (!t) {
      setError('Дай автоматизации название');
      return;
    }
    if (type === 'custom_prompt' && !prompt.trim()) {
      setError('Напиши промпт — что Lumi должна сделать');
      return;
    }
    if (scheduleMode === 'once') {
      if (!runAt) {
        setError('Выбери дату и время запуска');
        return;
      }
    } else if (!cronExpression || cronExpression.split(/\s+/).length !== 5) {
      setError('Cron-строка должна состоять из 5 полей, например «30 8 * * 1-5»');
      return;
    }
    let config: Record<string, unknown> | undefined;
    if (configText.trim()) {
      try {
        const parsed: unknown = JSON.parse(configText);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setError('Config должен быть JSON-объектом');
          return;
        }
        config = parsed as Record<string, unknown>;
      } catch {
        setError('Config: некорректный JSON');
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
          show('Автоматизация создана', 'success');
          setTitle('');
          setConfigText('');
          onClose();
        },
        onError: () => show('Не удалось создать автоматизацию', 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title="Новая автоматизация">
      <label className="block">
        <FieldLabel>Тип</FieldLabel>
        <Select value={type} onChange={(v) => setType(v as AutomationType)} options={TYPE_OPTIONS} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Название</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder={automationTypeLabel(type)} />
      </label>

      {type === 'custom_prompt' && (
        <>
          <label className="mt-4 block">
            <FieldLabel>Промпт — что сделать</FieldLabel>
            <Textarea
              value={prompt}
              onChange={setPrompt}
              rows={4}
              placeholder="Собери сводку по рынку AI-ассистентов: ключевые игроки, последние раунды, тренды"
            />
          </label>
          <label className="mt-4 block">
            <FieldLabel>Формат результата</FieldLabel>
            <Select
              value={format}
              onChange={(v) => setFormat(v as 'text' | 'md' | 'html')}
              options={[
                { value: 'text', label: 'Сообщение в чат' },
                { value: 'md', label: 'Markdown-файл' },
                { value: 'html', label: 'HTML-документ' },
              ]}
            />
          </label>
        </>
      )}

      <div className="mt-4">
        <FieldLabel>Когда запускать</FieldLabel>
        <div className="mb-2.5 flex gap-1.5">
          {([['cron', 'По расписанию'], ['once', 'Один раз']] as const).map(([mode, label]) => (
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
          {CRON_PRESETS.map((p) => (
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
              <p className="mt-1.5 text-[12px] text-hint">→ {humanizeCron(customCron.trim())}</p>
            )}
          </div>
        )}
        </>
        )}
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer select-none text-[13px] font-medium text-hint">
          Расширенные настройки (JSON)
        </summary>
        <div className="mt-2.5">
          <Textarea value={configText} onChange={setConfigText} rows={4} mono placeholder='{ "limit": 10 }' />
        </div>
      </details>

      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createAutomation.isPending} onClick={submit}>
        Создать
      </Button>
    </Sheet>
  );
}

export default function AutomationsPage() {
  const automationsQuery = useAutomations();
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <Stagger>
      <Rise>
        <Button variant="ghost" icon={<Plus size={15} />} onClick={() => setSheetOpen(true)}>
          Новая автоматизация
        </Button>
      </Rise>

      <Rise className="mt-4">
        {automationsQuery.isPending ? (
          <SkeletonList count={3} lines={2} />
        ) : automationsQuery.isError ? (
          <ErrorState message="Не удалось загрузить автоматизации." onRetry={() => void automationsQuery.refetch()} />
        ) : (automationsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Zap}
            title="Автоматизаций пока нет"
            hint="Создай сценарий — например, утренний дайджест новостей по будням в 08:30."
            action={
              <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setSheetOpen(true)}>
                Создать
              </Button>
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {automationsQuery.data.items.map((automation) => (
              <AutomationCard key={automation.id} automation={automation} />
            ))}
          </div>
        )}
      </Rise>

      <CreateAutomationSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        defaultTimezone={Intl.DateTimeFormat().resolvedOptions().timeZone}
      />
    </Stagger>
  );
}
