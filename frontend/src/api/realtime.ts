import type { QueryKey } from '@tanstack/react-query';
import { getInitData } from '../telegram/webapp';
import { ApiError, markUnauthorizedResponse } from './client';

export interface RealtimeEvent {
  id?: number;
  topics: string[];
  event_type: string;
  payload: Record<string, unknown>;
}

export interface DecodedSseEvent {
  id?: number;
  event: string;
  data: unknown;
}

export class SseDecoder {
  private buffer = '';

  push(chunk: string): DecodedSseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n');
    const events: DecodedSseEvent[] = [];
    let boundary = this.buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const parsed = this.parse(raw);
      if (parsed) events.push(parsed);
      boundary = this.buffer.indexOf('\n\n');
    }
    return events;
  }

  private parse(raw: string): DecodedSseEvent | null {
    let id: number | undefined;
    let event = 'message';
    const dataLines: string[] = [];

    for (const line of raw.split('\n')) {
      if (!line || line.startsWith(':')) continue;
      const sep = line.indexOf(':');
      const field = sep === -1 ? line : line.slice(0, sep);
      const value = sep === -1 ? '' : line.slice(sep + 1).replace(/^ /, '');
      if (field === 'id') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) id = parsed;
      } else if (field === 'event') {
        event = value;
      } else if (field === 'data') {
        dataLines.push(value);
      }
    }

    if (dataLines.length === 0) return null;
    const dataText = dataLines.join('\n');
    let data: unknown = dataText;
    try {
      data = JSON.parse(dataText);
    } catch {
      /* plain text data */
    }
    return { id, event, data };
  }
}

export function toRealtimeEvent(decoded: DecodedSseEvent): RealtimeEvent | null {
  if (decoded.event === 'resync') {
    return { topics: ['*'], event_type: 'resync', payload: {} };
  }
  if (decoded.event !== 'ui_event' || typeof decoded.data !== 'object' || decoded.data === null) {
    return null;
  }
  const data = decoded.data as Record<string, unknown>;
  const topics = Array.isArray(data.topics) ? data.topics.filter((topic): topic is string => typeof topic === 'string') : [];
  const payload = typeof data.payload === 'object' && data.payload !== null
    ? data.payload as Record<string, unknown>
    : {};
  const id = typeof data.id === 'number' ? data.id : decoded.id;
  return {
    ...(id !== undefined ? { id } : {}),
    topics,
    event_type: typeof data.event_type === 'string' ? data.event_type : 'ui.changed',
    payload,
  };
}

const ALL_KEYS: QueryKey[] = [
  ['today'],
  ['tasks'],
  ['projects'],
  ['assistant-suggestions'],
  ['focus'],
  ['focus-summary'],
  ['focus-sessions'],
  ['focus-session'],
  ['calendar-events'],
  ['free-slots'],
  ['inbox-summary'],
  ['news-topics'],
  ['news-digests'],
  ['automations'],
  ['memories'],
  ['agent-runs'],
  ['settings'],
];

export function getRealtimeInvalidationKeys(event: RealtimeEvent): QueryKey[] {
  if (event.event_type === 'resync' || event.topics.includes('*')) return ALL_KEYS;

  const keys: QueryKey[] = [];
  const add = (key: QueryKey) => {
    if (!keys.some((existing) => JSON.stringify(existing) === JSON.stringify(key))) keys.push(key);
  };

  for (const topic of event.topics) {
    if (topic === 'tasks') {
      add(['tasks']);
      add(['projects']);
      add(['assistant-suggestions']);
      add(['today']);
    } else if (topic === 'projects') {
      add(['projects']);
      add(['tasks']);
    } else if (topic === 'suggestions') {
      add(['assistant-suggestions']);
      add(['today']);
    } else if (topic === 'confirmations') {
      add(['today']);
    } else if (topic === 'focus') {
      add(['focus']);
      add(['focus-summary']);
      add(['focus-sessions']);
      add(['focus-session']);
      add(['today']);
    } else if (topic === 'calendar') {
      add(['calendar-events']);
      add(['free-slots']);
      add(['today']);
    } else if (topic === 'runs') {
      add(['agent-runs']);
      add(['today']);
      if (typeof event.payload.run_id === 'string') add(['agent-run', event.payload.run_id]);
    } else if (topic === 'inbox') {
      add(['inbox-summary']);
      add(['today']);
    } else if (topic === 'news') {
      add(['news-topics']);
      add(['news-digests']);
    } else if (topic === 'automations') {
      add(['automations']);
      add(['today']);
    } else if (topic === 'memories') {
      add(['memories']);
      add(['today']);
    } else if (topic === 'settings') {
      add(['settings']);
      add(['today']);
      add(['focus']);
      add(['focus-summary']);
      add(['focus-sessions']);
      add(['focus-session']);
    }
  }

  return keys;
}

export async function consumeRealtimeEvents({
  after,
  signal,
  onEvent,
}: {
  after: number;
  signal: AbortSignal;
  onEvent: (event: RealtimeEvent) => void;
}): Promise<void> {
  const headers: Record<string, string> = {};
  const initData = getInitData();
  if (initData) headers['X-Telegram-Init-Data'] = initData;

  const response = await fetch(`/api/realtime?after=${after}`, {
    method: 'GET',
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  });

  if (response.status === 401) {
    markUnauthorizedResponse();
    throw new ApiError(401, 'unauthorized', null);
  }
  if (!response.ok) throw new ApiError(response.status, 'realtime_error', null);
  if (!response.body) throw new ApiError(0, 'realtime_stream_missing', null);

  const reader = response.body.getReader();
  const text = new TextDecoder();
  const sse = new SseDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const decoded of sse.push(text.decode(value, { stream: true }))) {
      const event = toRealtimeEvent(decoded);
      if (event) onEvent(event);
    }
  }
}
