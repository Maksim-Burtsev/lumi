import { useCallback, useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import { api, ApiError } from './client';
import type { FocusPeriod, FocusRangeQuery } from './client';
import { consumeRealtimeEvents, getRealtimeInvalidationKeys } from './realtime';
import type {
  AgentRun,
  AssistantSuggestion,
  CreateAutomationInput,
  CreateEventInput,
  CreateNewsTopicInput,
  CreateTaskInput,
  FinishFocusSessionInput,
  FocusStateResponse,
  LogFocusSessionInput,
  PatchAutomationInput,
  PatchNewsTopicInput,
  PatchSettingsInput,
  PatchTaskInput,
  PrivateNoteInput,
  RunRef,
  SnoozeInput,
  StartFocusSessionInput,
  Task,
  TaskFilter,
  TaskListQuery,
  TasksResponse,
  TimezonesResponse,
  TodayResponse,
  UpdateFocusSessionInput,
} from './types';
import { haptic } from '../telegram/webapp';
import { useToast } from '../components/ui/Toast';

// ------------------------------------------------------------------ keys

export function normalizeTaskListQuery(query: TaskListQuery = {}) {
  return {
    filter: query.filter ?? 'all',
    q: query.q?.trim().replace(/\s+/g, ' ') || undefined,
    limit: query.limit ?? 100,
    offset: query.offset ?? 0,
    project_id: query.project_id,
  };
}

export const qk = {
  health: ['health'] as const,
  settings: ['settings'] as const,
  timezones: ['timezones'] as const,
  today: ['today'] as const,
  tasksAll: ['tasks'] as const,
  tasks: (query: TaskListQuery = {}) => ['tasks', normalizeTaskListQuery(query)] as const,
  projectTasks: (projectId: string) => [
    'tasks',
    normalizeTaskListQuery({ filter: 'all', limit: 100, project_id: projectId }),
  ] as const,
  projects: ['projects'] as const,
  assistantSuggestions: ['assistant-suggestions'] as const,
  focus: ['focus'] as const,
  focusTasks: ['tasks', normalizeTaskListQuery({ filter: 'all', limit: 300 })] as const,
  focusSession: (id: string) => ['focus-session', id] as const,
  focusSummary: (query: FocusRangeQuery) => ['focus-summary', query] as const,
  focusSessions: (query: FocusRangeQuery) => ['focus-sessions', query] as const,
  eventsAll: ['calendar-events'] as const,
  events: (start: string, end: string) => ['calendar-events', start, end] as const,
  freeSlotsAll: ['free-slots'] as const,
  freeSlots: (date: string) => ['free-slots', date] as const,
  inbox: ['inbox-summary'] as const,
  newsTopics: ['news-topics'] as const,
  digests: ['news-digests'] as const,
  automations: ['automations'] as const,
  memories: ['memories'] as const,
  runs: ['agent-runs'] as const,
  runDetail: (id: string) => ['agent-run', id] as const,
};

const REALTIME_LAST_ID_KEY = 'lumi-realtime-last-id';
const REALTIME_BATCH_MS = 250;
const REALTIME_RETRY_INITIAL_MS = 1000;
const REALTIME_RETRY_MAX_MS = 15000;

function readLastRealtimeId(): number {
  const raw = sessionStorage.getItem(REALTIME_LAST_ID_KEY);
  const parsed = raw ? Number(raw) : 0;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function writeLastRealtimeId(id: number): void {
  sessionStorage.setItem(REALTIME_LAST_ID_KEY, String(id));
}

export function useRealtimeInvalidation() {
  const queryClient = useQueryClient();

  useEffect(() => {
    let stopped = false;
    let connected = false;
    let retryMs = REALTIME_RETRY_INITIAL_MS;
    let controller: AbortController | null = null;
    let flushTimer: number | null = null;
    const pending = new Map<string, QueryKey>();
    const lastIdRef = { current: readLastRealtimeId() };

    const flush = () => {
      flushTimer = null;
      const keys = [...pending.values()];
      pending.clear();
      for (const key of keys) void queryClient.invalidateQueries({ queryKey: key });
    };

    const scheduleKeys = (keys: QueryKey[]) => {
      for (const key of keys) pending.set(JSON.stringify(key), key);
      if (pending.size > 0 && flushTimer === null) {
        flushTimer = window.setTimeout(flush, REALTIME_BATCH_MS);
      }
    };

    const scheduleResync = () => {
      scheduleKeys(getRealtimeInvalidationKeys({ topics: ['*'], event_type: 'resync', payload: {} }));
    };

    const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

    const loop = async () => {
      while (!stopped) {
        controller = new AbortController();
        try {
          connected = true;
          await consumeRealtimeEvents({
            after: lastIdRef.current,
            signal: controller.signal,
            onEvent: (event) => {
              if (event.id !== undefined) {
                lastIdRef.current = Math.max(lastIdRef.current, event.id);
                writeLastRealtimeId(lastIdRef.current);
              }
              scheduleKeys(getRealtimeInvalidationKeys(event));
            },
          });
          connected = false;
          retryMs = REALTIME_RETRY_INITIAL_MS;
        } catch (error) {
          if (stopped || (error instanceof DOMException && error.name === 'AbortError')) break;
          if (error instanceof ApiError && error.status === 401) break;
          connected = false;
        }
        if (!stopped) {
          await sleep(retryMs);
          retryMs = Math.min(Math.round(retryMs * 1.7), REALTIME_RETRY_MAX_MS);
        }
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === 'visible' && !connected) scheduleResync();
    };

    void loop();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stopped = true;
      controller?.abort();
      document.removeEventListener('visibilitychange', onVisibility);
      if (flushTimer !== null) window.clearTimeout(flushTimer);
    };
  }, [queryClient]);
}

// ------------------------------------------------------------------ queries

export function useHealth() {
  return useQuery({
    queryKey: qk.health,
    queryFn: () => api.health(),
    staleTime: Infinity,
    retry: false,
  });
}

export function useSettings() {
  return useQuery({ queryKey: qk.settings, queryFn: () => api.getSettings() });
}

export function useTimezones() {
  return useQuery<TimezonesResponse>({
    queryKey: qk.timezones,
    queryFn: () => api.getTimezones(),
    staleTime: Infinity,
  });
}

export function useToday() {
  return useQuery({ queryKey: qk.today, queryFn: () => api.getToday() });
}

export function useTasks(filterOrQuery: TaskFilter | TaskListQuery) {
  const query = normalizeTaskListQuery(
    typeof filterOrQuery === 'string' ? { filter: filterOrQuery } : filterOrQuery,
  );
  return useQuery({ queryKey: qk.tasks(query), queryFn: () => api.listTasks(query) });
}

export function useFocusTasks() {
  return useQuery({
    queryKey: qk.focusTasks,
    queryFn: () => api.listTasks({ filter: 'all', limit: 300 }),
  });
}

export function useProjectTasks(projectId: string | null) {
  return useQuery({
    queryKey: projectId ? qk.projectTasks(projectId) : qk.projectTasks('none'),
    queryFn: () => api.listTasks({ filter: 'all', limit: 100, project_id: projectId as string }),
    enabled: projectId !== null,
  });
}

export function useProjects() {
  return useQuery({ queryKey: qk.projects, queryFn: () => api.listProjects() });
}

export function useAssistantSuggestions(kind?: string) {
  return useQuery({
    queryKey: kind ? [...qk.assistantSuggestions, kind] : qk.assistantSuggestions,
    queryFn: () => api.listAssistantSuggestions(kind),
  });
}

export function useFocusState() {
  return useQuery({
    queryKey: qk.focus,
    queryFn: () => api.getFocusState(),
    refetchOnReconnect: true,
  });
}

export function useFocusSummary(
  period: FocusPeriod,
  options: {
    from_date?: string;
    to_date?: string;
    q?: string;
    project_id?: string;
    enabled?: boolean;
  } = {},
) {
  const query = {
    period,
    from_date: options.from_date,
    to_date: options.to_date,
    q: options.q?.trim() || undefined,
    project_id: options.project_id || undefined,
  };
  return useQuery({
    queryKey: qk.focusSummary(query),
    queryFn: () => api.getFocusSummary(query),
    enabled: options.enabled ?? true,
  });
}

export function useFocusSessions(period: FocusPeriod, range?: { from_date?: string; to_date?: string }) {
  const query = { period, from_date: range?.from_date, to_date: range?.to_date, limit: 100, offset: 0 };
  return useQuery({ queryKey: qk.focusSessions(query), queryFn: () => api.listFocusSessions(query) });
}

export function useInfiniteFocusSessions(
  period: FocusPeriod,
  options: { from_date?: string; to_date?: string; q?: string; project_id?: string; enabled?: boolean } = {},
) {
  const query = {
    period,
    from_date: options.from_date,
    to_date: options.to_date,
    q: options.q?.trim() || undefined,
    project_id: options.project_id || undefined,
    limit: 50,
  };
  return useInfiniteQuery({
    queryKey: qk.focusSessions(query),
    queryFn: ({ pageParam }) => api.listFocusSessions({ ...query, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.has_more ? (lastPage.next_offset ?? undefined) : undefined,
    enabled: options.enabled ?? true,
  });
}

export function useFocusSession(id: string | null) {
  return useQuery({
    queryKey: id ? qk.focusSession(id) : qk.focusSession('none'),
    queryFn: () => api.getFocusSession(id as string),
    enabled: id !== null,
  });
}

export function useCalendarEvents(start: string, end: string) {
  return useQuery({ queryKey: qk.events(start, end), queryFn: () => api.listCalendarEvents(start, end) });
}

export function useFreeSlots(date: string, duration = 60) {
  return useQuery({
    queryKey: qk.freeSlots(date),
    queryFn: () => api.getFreeSlots(date, duration),
    retry: false,
  });
}

export function useInboxSummary() {
  return useQuery({ queryKey: qk.inbox, queryFn: () => api.getInboxSummary() });
}

export function useNewsTopics() {
  return useQuery({ queryKey: qk.newsTopics, queryFn: () => api.listNewsTopics() });
}

export function useNewsDigests(limit = 5) {
  return useQuery({ queryKey: qk.digests, queryFn: () => api.listNewsDigests(limit) });
}

export function useAutomations() {
  return useQuery({ queryKey: qk.automations, queryFn: () => api.listAutomations() });
}

export function useMemories() {
  return useQuery({ queryKey: qk.memories, queryFn: () => api.listMemories({ status: 'active' }) });
}

export function useAgentRuns(limit = 30) {
  return useQuery({ queryKey: qk.runs, queryFn: () => api.listAgentRuns(limit) });
}

export function useAgentRunDetail(id: string | null) {
  return useQuery({
    queryKey: qk.runDetail(id ?? 'none'),
    queryFn: () => api.getAgentRun(id as string),
    enabled: id !== null,
  });
}

// ------------------------------------------------------------------ task mutations

function makeOptimisticTask(input: CreateTaskInput): Task {
  return {
    id: `optimistic-${Date.now()}`,
    title: input.title,
    description: input.description ?? null,
    status: 'inbox',
    priority: input.priority ?? 'medium',
    project: input.project ?? null,
    project_id: input.project_id ?? null,
    tags: input.tags ?? [],
    due_at: input.due_at ?? null,
    planned_for: null,
    target_at: null,
    reminder_at: input.reminder_at ?? null,
    snoozed_until: null,
    estimated_minutes: input.estimated_minutes ?? null,
    estimate_source: input.estimate_source ?? null,
    review_skips: {},
    source: 'mini_app',
    created_at: new Date().toISOString(),
    completed_at: null,
    bucket: 'inbox',
  };
}

function invalidateTaskSurfaces(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: qk.tasksAll });
  void queryClient.invalidateQueries({ queryKey: qk.projects });
  void queryClient.invalidateQueries({ queryKey: qk.assistantSuggestions });
  void queryClient.invalidateQueries({ queryKey: qk.today });
}

export function useCreateTask(activeFilter: TaskFilter) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateTaskInput) => api.createTask(input),
    onMutate: async (input) => {
      const key = qk.tasks({ filter: activeFilter });
      await queryClient.cancelQueries({ queryKey: qk.tasksAll });
      const previous = queryClient.getQueryData<TasksResponse>(key);
      const isUnplannedCapture = !input.planned_for && !input.target_at;
      const acceptsInbox = ['all', 'inbox', 'review'].includes(activeFilter);
      if (previous && isUnplannedCapture && acceptsInbox) {
        queryClient.setQueryData<TasksResponse>(key, {
          ...previous,
          items: [makeOptimisticTask(input), ...previous.items],
        });
      }
      return { previous, key };
    },
    onError: (_error, _input, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous);
    },
    onSettled: () => invalidateTaskSurfaces(queryClient),
  });
}

function patchTaskInCache(queryClient: ReturnType<typeof useQueryClient>, key: QueryKey, id: string, patch: Partial<Task>) {
  const previous = queryClient.getQueryData<TasksResponse>(key);
  if (previous) {
    queryClient.setQueryData<TasksResponse>(key, {
      ...previous,
      items: previous.items.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    });
  }
  return previous;
}

export function useCompleteTask(activeFilter: TaskFilter) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.completeTask(id),
    onMutate: async (id) => {
      const key = qk.tasks({ filter: activeFilter });
      await queryClient.cancelQueries({ queryKey: qk.tasksAll });
      const previous = patchTaskInCache(queryClient, key, id, {
        status: 'done',
        completed_at: new Date().toISOString(),
        bucket: 'done',
      });
      return { previous, key };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous);
    },
    onSettled: () => invalidateTaskSurfaces(queryClient),
  });
}

export function useSnoozeTask(activeFilter: TaskFilter) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: SnoozeInput }) => api.snoozeTask(id, input),
    onMutate: async ({ id }) => {
      const key = qk.tasks({ filter: activeFilter });
      await queryClient.cancelQueries({ queryKey: qk.tasksAll });
      const previous = queryClient.getQueryData<TasksResponse>(key);
      if (previous) {
        queryClient.setQueryData<TasksResponse>(key, {
          ...previous,
          items: previous.items.filter((t) => t.id !== id),
        });
      }
      return { previous, key };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous);
    },
    onSettled: () => invalidateTaskSurfaces(queryClient),
  });
}

export function usePatchTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: PatchTaskInput }) => api.patchTask(id, input),
    onSettled: () => invalidateTaskSurfaces(queryClient),
  });
}

// ------------------------------------------------------------------ assistant suggestions mutations

function removeSuggestionFromCache(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
) {
  const previous = queryClient.getQueryData<{ items: AssistantSuggestion[] }>(qk.assistantSuggestions);
  if (previous) {
    queryClient.setQueryData(qk.assistantSuggestions, {
      items: previous.items.filter((item) => item.id !== id),
    });
  }
  return previous;
}

export function useDecideAssistantSuggestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, accept }: { id: string; accept: boolean }) =>
      accept ? api.acceptAssistantSuggestion(id) : api.dismissAssistantSuggestion(id),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: qk.assistantSuggestions });
      return { previous: removeSuggestionFromCache(queryClient, id) };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(qk.assistantSuggestions, context.previous);
    },
    onSettled: () => invalidateTaskSurfaces(queryClient),
  });
}

// ------------------------------------------------------------------ focus mutations

function invalidateFocusQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: qk.focus });
  invalidateFocusDerivedQueries(queryClient);
}

function invalidateFocusDerivedQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['focus-summary'] });
  void queryClient.invalidateQueries({ queryKey: ['focus-sessions'] });
  void queryClient.invalidateQueries({ queryKey: ['focus-session'] });
}

export function useStartFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: StartFocusSessionInput) => api.startFocusSession(input),
    onSuccess: (response) => {
      const previous = queryClient.getQueryData(qk.focus) as
        | { today?: unknown; recent_sessions?: unknown[] }
        | undefined;
      queryClient.setQueryData(qk.focus, {
        active_session: response.session,
        today: previous?.today ?? { focus_seconds: 0, completed_sessions: 0, streak_days: 0 },
        recent_sessions: previous?.recent_sessions ?? [],
      });
      invalidateFocusDerivedQueries(queryClient);
    },
  });
}

export function useLogFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LogFocusSessionInput) => api.logFocusSession(input),
    onSuccess: () => {
      invalidateFocusQueries(queryClient);
    },
  });
}

export function useFinishFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: FinishFocusSessionInput }) => api.finishFocusSession(id, input),
    onSuccess: () => {
      queryClient.setQueryData<FocusStateResponse>(qk.focus, (current) => (
        current ? { ...current, active_session: null } : current
      ));
      invalidateFocusDerivedQueries(queryClient);
    },
    onSettled: () => invalidateFocusQueries(queryClient),
  });
}

export function useUpdateFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateFocusSessionInput }) => api.updateFocusSession(id, input),
    onSuccess: () => {
      invalidateFocusQueries(queryClient);
    },
  });
}

export function useDeleteFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteFocusSession(id),
    onSuccess: () => {
      invalidateFocusQueries(queryClient);
    },
  });
}

export function useAbandonFocusSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.abandonFocusSession(id),
    onSuccess: () => {
      queryClient.setQueryData<FocusStateResponse>(qk.focus, (current) => (
        current ? { ...current, active_session: null } : current
      ));
      invalidateFocusDerivedQueries(queryClient);
    },
    onSettled: () => invalidateFocusQueries(queryClient),
  });
}

// ------------------------------------------------------------------ calendar mutations

export function useCreateEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateEventInput) => api.createCalendarEvent(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.assistantSuggestions });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

export function useUpdateCalendarPrivateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: PrivateNoteInput }) => api.updateCalendarPrivateNote(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

export function useDeleteCalendarPrivateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteCalendarPrivateNote(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

export function useConfirmBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.confirmBlock(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.assistantSuggestions });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

function removeConfirmationFromTodayCache(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  const previous = queryClient.getQueryData<TodayResponse>(qk.today);
  if (previous) {
    queryClient.setQueryData<TodayResponse>(qk.today, {
      ...previous,
      needs_attention: previous.needs_attention.filter((item) => item.ref_id !== id),
    });
  }
  return previous;
}

export function useDecideConfirmation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, accept }: { id: string; accept: boolean }) =>
      accept ? api.acceptConfirmation(id) : api.rejectConfirmation(id),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: qk.today });
      return { previousToday: removeConfirmationFromTodayCache(queryClient, id) };
    },
    onError: (_error, _vars, context) => {
      if (context?.previousToday) queryClient.setQueryData(qk.today, context.previousToday);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.today, refetchType: 'none' });
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.tasksAll });
      void queryClient.invalidateQueries({ queryKey: qk.inbox });
      void queryClient.invalidateQueries({ queryKey: qk.memories });
      void queryClient.invalidateQueries({ queryKey: qk.automations });
    },
  });
}

// ------------------------------------------------------------------ inbox mutations

export function useCreateTaskFromThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => api.createTaskFromThread(threadId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.tasksAll });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

// ------------------------------------------------------------------ news mutations

export function useCreateNewsTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateNewsTopicInput) => api.createNewsTopic(input),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qk.newsTopics }),
  });
}

export function usePatchNewsTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: PatchNewsTopicInput }) => api.patchNewsTopic(id, input),
    onMutate: async ({ id, input }) => {
      await queryClient.cancelQueries({ queryKey: qk.newsTopics });
      const previous = queryClient.getQueryData<{ items: import('./types').NewsTopic[] }>(qk.newsTopics);
      if (previous) {
        queryClient.setQueryData(qk.newsTopics, {
          items: previous.items.map((t) => (t.id === id ? { ...t, ...input } : t)),
        });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(qk.newsTopics, context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: qk.newsTopics }),
  });
}

// ------------------------------------------------------------------ automations mutations

export function useCreateAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAutomationInput) => api.createAutomation(input),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qk.automations }),
  });
}

export function usePatchAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: PatchAutomationInput }) => api.patchAutomation(id, input),
    onMutate: async ({ id, input }) => {
      await queryClient.cancelQueries({ queryKey: qk.automations });
      const previous = queryClient.getQueryData<{ items: import('./types').Automation[] }>(qk.automations);
      if (previous) {
        queryClient.setQueryData(qk.automations, {
          items: previous.items.map((a) => (a.id === id ? { ...a, ...input } : a)),
        });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(qk.automations, context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: qk.automations }),
  });
}

// ------------------------------------------------------------------ memory mutations

function removeMemoryFromCache(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  const previous = queryClient.getQueryData<{ items: import('./types').Memory[] }>(qk.memories);
  if (previous) {
    queryClient.setQueryData(qk.memories, { items: previous.items.filter((m) => m.id !== id) });
  }
  return previous;
}

export function useArchiveMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.patchMemory(id, { status: 'archived' }),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: qk.memories });
      return { previous: removeMemoryFromCache(queryClient, id) };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(qk.memories, context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: qk.memories }),
  });
}

export function useDeleteMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteMemory(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: qk.memories });
      return { previous: removeMemoryFromCache(queryClient, id) };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(qk.memories, context.previous);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: qk.memories }),
  });
}

// ------------------------------------------------------------------ settings mutations

function isThemeOnlyPatch(input: PatchSettingsInput): boolean {
  const keys = Object.entries(input)
    .filter(([, value]) => value !== undefined)
    .map(([key]) => key);
  return keys.length === 1 && keys[0] === 'theme_mode';
}

export function usePatchSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PatchSettingsInput) => api.patchSettings(input),
    onSuccess: (_data, input) => {
      if (!isThemeOnlyPatch(input)) {
        void queryClient.invalidateQueries({ queryKey: qk.settings });
        void queryClient.invalidateQueries({ queryKey: qk.assistantSuggestions });
        void queryClient.invalidateQueries({ queryKey: qk.today });
      }
      if (input.timezone !== undefined) {
        invalidateFocusQueries(queryClient);
      }
    },
  });
}

export function useDeleteEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteCalendarEvent(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
      void queryClient.invalidateQueries({ queryKey: qk.freeSlotsAll });
      void queryClient.invalidateQueries({ queryKey: qk.assistantSuggestions });
      void queryClient.invalidateQueries({ queryKey: qk.today });
    },
  });
}

export function useConnectYandex() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { username: string; app_password: string }) => api.connectYandex(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.settings });
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
    },
  });
}

export function useDisconnectYandex() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.disconnectYandex(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.settings });
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
    },
  });
}

export function useDisconnectGoogle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.disconnectGoogle(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.settings });
      void queryClient.invalidateQueries({ queryKey: qk.inbox });
      void queryClient.invalidateQueries({ queryKey: qk.eventsAll });
    },
  });
}

// ------------------------------------------------------------------ run polling

export type RunPollStatus = 'idle' | 'polling' | 'completed' | 'failed' | 'timeout';

export interface RunPollerResult {
  status: RunPollStatus;
  run: AgentRun | null;
}

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 120_000;

/**
 * Polls GET /api/agent-runs/{id} every 1.5s (up to 120s) until the run is
 * completed/failed. On completion invalidates agent-runs + today + any
 * caller-provided query keys.
 */
export function useRunPoller(runId: string | null, invalidate?: QueryKey[]): RunPollerResult {
  const queryClient = useQueryClient();
  const startedAtRef = useRef(0);
  const [timedOut, setTimedOut] = useState(false);
  const invalidateRef = useRef(invalidate);
  invalidateRef.current = invalidate;

  useEffect(() => {
    if (runId) {
      startedAtRef.current = Date.now();
      setTimedOut(false);
    }
  }, [runId]);

  const query = useQuery({
    queryKey: ['agent-run-poll', runId],
    queryFn: () => api.getAgentRun(runId as string),
    enabled: runId !== null && !timedOut,
    gcTime: 0,
    staleTime: 0,
    retry: false,
    refetchInterval: (q) => {
      const status = q.state.data?.run.status;
      if (status === 'completed' || status === 'failed') return false;
      if (Date.now() - startedAtRef.current > POLL_TIMEOUT_MS) return false;
      return POLL_INTERVAL_MS;
    },
  });

  // Timeout watcher
  useEffect(() => {
    if (!runId) return undefined;
    const timer = window.setInterval(() => {
      if (Date.now() - startedAtRef.current > POLL_TIMEOUT_MS) setTimedOut(true);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [runId]);

  const run = query.data?.run ?? null;
  let status: RunPollStatus = 'idle';
  if (runId !== null) {
    if (run?.status === 'completed') status = 'completed';
    else if (run?.status === 'failed') status = 'failed';
    else if (timedOut) status = 'timeout';
    else status = 'polling';
  }

  // Invalidate related queries once per finished run
  const doneForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!runId) return;
    if ((status === 'completed' || status === 'failed') && doneForRef.current !== runId) {
      doneForRef.current = runId;
      void queryClient.invalidateQueries({ queryKey: qk.runs });
      void queryClient.invalidateQueries({ queryKey: qk.today });
      for (const key of invalidateRef.current ?? []) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    }
  }, [status, runId, queryClient]);

  return { status, run };
}

// ------------------------------------------------------------------ run action (start + poll + toast)

export interface RunActionOptions {
  start: () => Promise<RunRef>;
  invalidate?: QueryKey[];
  successMessage?: string;
  /** Return true if the error was handled (e.g. 409 google_not_connected). */
  onApiError?: (error: ApiError) => boolean;
}

export interface RunAction {
  trigger: (startOverride?: () => Promise<RunRef>) => void;
  isRunning: boolean;
  status: RunPollStatus;
}

export function useAgentRunAction(options: RunActionOptions): RunAction {
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const poller = useRunPoller(runId, options.invalidate);
  const { show } = useToast();

  const optionsRef = useRef(options);
  optionsRef.current = options;
  const runRef = useRef(poller.run);
  runRef.current = poller.run;

  const trigger = useCallback((startOverride?: () => Promise<RunRef>) => {
    if (runId !== null || starting) return;
    setStarting(true);
    haptic('light');
    (startOverride ?? optionsRef.current.start)()
      .then((ref) => setRunId(ref.run_id))
      .catch((error: unknown) => {
        if (error instanceof ApiError && optionsRef.current.onApiError?.(error)) return;
        const message =
          error instanceof ApiError
            ? (error.detail ?? `Не удалось запустить (${error.error})`)
            : 'Не удалось запустить';
        show(message, 'error');
      })
      .finally(() => setStarting(false));
  }, [runId, starting, show]);

  useEffect(() => {
    if (poller.status === 'completed') {
      haptic('success');
      show(runRef.current?.result_summary ?? optionsRef.current.successMessage ?? 'Готово', 'success');
      setRunId(null);
    } else if (poller.status === 'failed') {
      haptic('error');
      show(runRef.current?.error_message ?? 'Запуск завершился с ошибкой', 'error');
      setRunId(null);
    } else if (poller.status === 'timeout') {
      show('Запуск ещё выполняется — результат появится в «Запусках агента»', 'info');
      setRunId(null);
    }
  }, [poller.status, show]);

  return { trigger, isRunning: starting || runId !== null, status: poller.status };
}
