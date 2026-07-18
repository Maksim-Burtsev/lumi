import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type PropsWithChildren } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from './client';
import { ToastProvider } from '../components/ui/Toast';
import { normalizeTaskListQuery, qk, useAgentRunAction, useInfiniteTasks } from './hooks';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('task query keys', () => {
  it('include every server-side list parameter', () => {
    const base = qk.tasks({ filter: 'this_week', q: 'plan', limit: 20, offset: 0 });

    expect(base).not.toEqual(qk.tasks({ filter: 'later', q: 'plan', limit: 20, offset: 0 }));
    expect(base).not.toEqual(qk.tasks({ filter: 'this_week', q: 'notes', limit: 20, offset: 0 }));
    expect(base).not.toEqual(qk.tasks({ filter: 'this_week', q: 'plan', limit: 10, offset: 0 }));
    expect(base).not.toEqual(qk.tasks({ filter: 'this_week', q: 'plan', limit: 20, offset: 20 }));
    expect(base).not.toEqual(qk.tasks({
      filter: 'this_week',
      q: 'plan',
      limit: 20,
      offset: 0,
      project_id: 'project-1',
    }));
    expect(qk.projectTasks('project-1')).toEqual(qk.tasks({
      filter: 'all',
      limit: 100,
      project_id: 'project-1',
    }));
  });

  it('normalizes defaults and whitespace', () => {
    expect(normalizeTaskListQuery({ q: '  weekly   plan  ' })).toEqual({
      filter: 'all',
      q: 'weekly plan',
      limit: 100,
      offset: 0,
      project_id: undefined,
    });
  });

  it('keeps paged tasks in a separate cache with normalized search', () => {
    const query = { filter: 'later' as const, q: '  weekly   plan  ', limit: 20 };

    expect(qk.taskPages(query)).toEqual([
      'tasks',
      'pages',
      {
        filter: 'later',
        q: 'weekly plan',
        limit: 20,
        offset: 0,
        project_id: undefined,
      },
    ]);
    expect(qk.taskPages(query)).not.toEqual(qk.tasks(query));
  });

  it('continues from the server next offset', async () => {
    const listTasks = vi.spyOn(api, 'listTasks')
      .mockResolvedValueOnce({ items: [], has_more: true, next_offset: 20 })
      .mockResolvedValueOnce({ items: [], has_more: false, next_offset: null });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
    const { result } = renderHook(
      () => useInfiniteTasks({ filter: 'later', q: '  weekly   plan  ', limit: 20 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listTasks).toHaveBeenNthCalledWith(1, {
      filter: 'later',
      q: 'weekly plan',
      limit: 20,
      offset: 0,
      project_id: undefined,
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(listTasks).toHaveBeenNthCalledWith(2, {
      filter: 'later',
      q: 'weekly plan',
      limit: 20,
      offset: 20,
      project_id: undefined,
    });
  });
});

describe('agent run actions', () => {
  it('uses the configured start callback when React passes a click event', () => {
    const start = vi.fn(() => new Promise<never>(() => undefined));
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(ToastProvider, null, children),
    );
    const { result } = renderHook(
      () => useAgentRunAction({ start }),
      { wrapper },
    );

    act(() => {
      (result.current.trigger as (event: unknown) => void)({ type: 'click' });
    });

    expect(start).toHaveBeenCalledOnce();
  });
});
