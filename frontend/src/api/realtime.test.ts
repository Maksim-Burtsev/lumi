import { describe, expect, it, vi } from 'vitest';
import { UNAUTHORIZED_EVENT } from './client';
import { SseDecoder, consumeRealtimeEvents, getRealtimeInvalidationKeys } from './realtime';

describe('SseDecoder', () => {
  it('parses split SSE chunks into realtime events', () => {
    const decoder = new SseDecoder();

    expect(decoder.push('id: 42\nevent: ui_')).toEqual([]);
    const events = decoder.push('event\ndata: {"topics":["tasks"],"payload":{"task_id":"t1"}}\n\n');

    expect(events).toEqual([
      {
        id: 42,
        event: 'ui_event',
        data: {
          topics: ['tasks'],
          payload: { task_id: 't1' },
        },
      },
    ]);
  });
});

describe('getRealtimeInvalidationKeys', () => {
  it('maps topics to React Query keys', () => {
    expect(
      getRealtimeInvalidationKeys({
        id: 7,
        topics: ['tasks', 'calendar', 'runs'],
        event_type: 'run.updated',
        payload: { run_id: 'run-1' },
      }),
    ).toEqual([
      ['tasks'],
      ['today'],
      ['calendar-events'],
      ['free-slots'],
      ['agent-runs'],
      ['agent-run', 'run-1'],
    ]);
  });

  it('maps resync to every UI query family', () => {
    expect(getRealtimeInvalidationKeys({ event_type: 'resync', topics: ['*'], payload: {} })).toEqual([
      ['today'],
      ['tasks'],
      ['calendar-events'],
      ['free-slots'],
      ['inbox-summary'],
      ['news-topics'],
      ['news-digests'],
      ['automations'],
      ['memories'],
      ['agent-runs'],
      ['settings'],
    ]);
  });
});

describe('consumeRealtimeEvents', () => {
  it('dispatches unauthorized state on 401', async () => {
    const unauthorized = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, unauthorized);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })));

    await expect(
      consumeRealtimeEvents({
        after: 0,
        signal: new AbortController().signal,
        onEvent: vi.fn(),
      }),
    ).rejects.toMatchObject({ status: 401, error: 'unauthorized' });

    expect(unauthorized).toHaveBeenCalledOnce();
    window.removeEventListener(UNAUTHORIZED_EVENT, unauthorized);
    vi.unstubAllGlobals();
  });
});
