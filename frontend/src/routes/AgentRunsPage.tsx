import { useState } from 'react';
import { Activity } from 'lucide-react';
import { useAgentRunDetail, useAgentRuns } from '../api/hooks';
import type { LlmCall, ToolCall } from '../api/types';
import { RunStatusBadge, RunStatusDot, runTypeIcon } from '../components/runs/RunBadge';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Sheet } from '../components/ui/Sheet';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { Rise, Stagger } from '../components/ui/motion';
import { formatDuration, formatRelative, formatTime } from '../lib/format';
import { runTypeLabel } from '../lib/labels';
import { useTimeDisplay } from '../lib/useTimeDisplay';

function safeJson(value: unknown): string {
  try {
    const text = JSON.stringify(value, null, 2) ?? 'null';
    return text.length > 2000 ? `${text.slice(0, 2000)}\n…` : text;
  } catch {
    return String(value);
  }
}

function ToolCallRow({ call }: { call: ToolCall }) {
  const timeDisplay = useTimeDisplay();
  return (
    <details className="border-b border-hairline px-1 py-2 last:border-b-0">
      <summary className="flex cursor-pointer select-none items-center gap-2.5 text-[13px]">
        <RunStatusDot status={call.status === 'success' || call.status === 'ok' ? 'completed' : call.status} />
        <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-ink">{call.tool_name}</span>
        <span className="tnum shrink-0 text-[11.5px] text-hint">{formatTime(call.created_at, timeDisplay)}</span>
      </summary>
      <div className="mt-2 flex flex-col gap-2 pl-5">
        {call.error_message && <p className="text-[12px] text-danger">{call.error_message}</p>}
        {call.args_json !== null && call.args_json !== undefined && (
          <pre className="overflow-x-auto rounded-lg bg-[var(--secondary-bg)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-hint">
            {safeJson(call.args_json)}
          </pre>
        )}
        {call.result_json !== null && call.result_json !== undefined && (
          <pre className="overflow-x-auto rounded-lg bg-[var(--secondary-bg)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-hint">
            {safeJson(call.result_json)}
          </pre>
        )}
      </div>
    </details>
  );
}

function LlmCallRow({ call }: { call: LlmCall }) {
  return (
    <div className="flex items-center gap-2.5 border-b border-hairline px-1 py-2 text-[12.5px] last:border-b-0">
      <RunStatusDot status={call.status === 'success' || call.status === 'ok' ? 'completed' : call.status} />
      <span className="min-w-0 flex-1 truncate font-mono text-ink">{call.model}</span>
      <span className="shrink-0 text-hint">{call.request_kind}</span>
      <span className="tnum shrink-0 font-mono text-[11.5px] text-hint">
        {call.latency_ms !== null ? `${call.latency_ms} мс` : '—'}
      </span>
      <span className="tnum shrink-0 font-mono text-[11.5px] text-hint">
        {call.input_char_count ?? '—'}→{call.output_char_count ?? '—'}
      </span>
    </div>
  );
}

function RunDetailSheet({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const detailQuery = useAgentRunDetail(runId);
  const detail = detailQuery.data;

  return (
    <Sheet open={runId !== null} onClose={onClose} title={detail ? runTypeLabel(detail.run.type) : 'Запуск'}>
      {detailQuery.isPending ? (
        <div aria-hidden className="flex flex-col gap-3 pb-4">
          <Skeleton className="h-6 w-28 !rounded-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : detailQuery.isError || !detail ? (
        <ErrorState message="Не удалось загрузить запуск." onRetry={() => void detailQuery.refetch()} />
      ) : (
        <div className="pb-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <RunStatusBadge status={detail.run.status} />
            <span className="tnum text-[12.5px] text-hint">{formatRelative(detail.run.created_at)}</span>
            <span className="tnum text-[12.5px] text-hint">{formatDuration(detail.run.duration_ms)}</span>
          </div>

          {detail.run.trigger && (
            <p className="mt-3 text-[12.5px] text-hint">
              Триггер: <span className="text-ink">{detail.run.trigger}</span>
            </p>
          )}
          {detail.run.input_summary && (
            <div className="mt-3 rounded-xl bg-[var(--secondary-bg)] px-3.5 py-2.5">
              <p className="text-[11.5px] font-medium uppercase tracking-wide text-hint">Вход</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink">{detail.run.input_summary}</p>
            </div>
          )}
          {detail.run.result_summary && (
            <div className="mt-3 rounded-xl bg-[var(--success-soft)] px-3.5 py-2.5">
              <p className="text-[11.5px] font-medium uppercase tracking-wide text-success">Результат</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink">{detail.run.result_summary}</p>
            </div>
          )}
          {detail.run.error_message && (
            <div className="mt-3 rounded-xl bg-[var(--danger-soft)] px-3.5 py-2.5">
              <p className="text-[11.5px] font-medium uppercase tracking-wide text-danger">Ошибка</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink">{detail.run.error_message}</p>
            </div>
          )}

          {detail.tool_calls.length > 0 && (
            <>
              <p className="mb-1 mt-5 text-[13px] font-semibold text-ink">
                Вызовы инструментов <span className="tnum text-hint">({detail.tool_calls.length})</span>
              </p>
              <div>
                {detail.tool_calls.map((call) => (
                  <ToolCallRow key={call.id} call={call} />
                ))}
              </div>
            </>
          )}

          {detail.llm_calls.length > 0 && (
            <>
              <p className="mb-1 mt-5 text-[13px] font-semibold text-ink">
                LLM-вызовы <span className="tnum text-hint">({detail.llm_calls.length})</span>
              </p>
              <div>
                {detail.llm_calls.map((call) => (
                  <LlmCallRow key={call.id} call={call} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Sheet>
  );
}

export default function AgentRunsPage() {
  const runsQuery = useAgentRuns();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <Stagger>
      <Rise>
        {runsQuery.isPending ? (
          <SkeletonList count={5} lines={1} />
        ) : runsQuery.isError ? (
          <ErrorState message="Не удалось загрузить запуски." onRetry={() => void runsQuery.refetch()} />
        ) : (runsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={Activity}
            title="Запусков пока не было"
            hint="Нажми «Собрать план» на главной — здесь появится журнал работы агента."
          />
        ) : (
          <div className="flex flex-col gap-2.5">
            {runsQuery.data.items.map((run) => {
              const Icon = runTypeIcon(run.type);
              return (
                <Card key={run.id} className="card-strong px-4 py-3" onClick={() => setSelectedId(run.id)}>
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--secondary-bg)]">
                      <Icon size={16} className="text-hint" strokeWidth={1.9} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-medium text-ink">{runTypeLabel(run.type)}</p>
                      <p className="truncate text-[12px] text-hint">
                        {run.result_summary ?? run.input_summary ?? run.trigger}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <RunStatusBadge status={run.status} />
                      <span className="tnum text-[11.5px] text-hint">
                        {formatRelative(run.created_at)}
                        {run.duration_ms !== null ? ` · ${formatDuration(run.duration_ms)}` : ''}
                      </span>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </Rise>

      <RunDetailSheet runId={selectedId} onClose={() => setSelectedId(null)} />
    </Stagger>
  );
}
