import { getInitData } from '../telegram/webapp';
import type {
  AgentRunDetailResponse,
  AgentRunsResponse,
  AssistantSuggestionResponse,
  AssistantSuggestionsResponse,
  AutomationResponse,
  AutomationsResponse,
  CalendarEventResponse,
  CalendarEventsResponse,
  ConfirmationDecisionResponse,
  CreateAutomationInput,
  CreateEventInput,
  CreateNewsTopicInput,
  CreateTaskInput,
  FinishFocusSessionInput,
  FocusSessionsResponse,
  FocusSessionResponse,
  FocusStateResponse,
  FocusSummaryResponse,
  FreeSlotsResponse,
  GoogleStatus,
  YandexConnectInput,
  YandexStatus,
  HealthResponse,
  InboxSummaryResponse,
  LogFocusSessionInput,
  MeResponse,
  MemoriesResponse,
  MemoryResponse,
  MessagesResponse,
  NewsDigestsResponse,
  NewsTopicResponse,
  NewsTopicsResponse,
  OkResponse,
  PatchAutomationInput,
  PatchMemoryInput,
  PatchNewsTopicInput,
  PrivateNoteInput,
  PatchSettingsInput,
  PatchTaskInput,
  ProjectsResponse,
  RunRef,
  SettingsResponse,
  SnoozeInput,
  StartFocusSessionInput,
  TaskFilter,
  TaskResponse,
  TasksResponse,
  TimezonesResponse,
  TodayResponse,
  UpdateFocusSessionInput,
} from './types';

/** Errors: non-2xx responses return {"error": "<machine_code>", "detail": "<text>"} */
export class ApiError extends Error {
  readonly status: number;
  readonly error: string;
  readonly detail: string | null;

  constructor(status: number, error: string, detail: string | null) {
    super(detail ?? error);
    this.name = 'ApiError';
    this.status = status;
    this.error = error;
    this.detail = detail;
  }
}

/** Event the app shell listens to in order to show the "open inside Telegram" screen. */
export const UNAUTHORIZED_EVENT = 'lumi:unauthorized';
let unauthorizedSeen = false;

export function hasUnauthorizedResponse(): boolean {
  return unauthorizedSeen;
}

export function clearUnauthorizedResponse(): void {
  unauthorizedSeen = false;
}

export function markUnauthorizedResponse(): void {
  unauthorizedSeen = true;
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type FocusPeriod = 'week' | 'month' | 'custom';

export interface FocusRangeQuery {
  period?: FocusPeriod;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}

interface RequestOptions {
  query?: Record<string, string | number | undefined>;
  body?: unknown;
}

async function request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<T> {
  let url = path;
  if (options.query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined && value !== '') params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  const initData = getInitData();
  if (initData) headers['X-Telegram-Init-Data'] = initData;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Нет соединения с сервером');
  }

  if (!response.ok) {
    let code = 'http_error';
    let detail: string | null = null;
    try {
      const data = (await response.json()) as { error?: unknown; detail?: unknown };
      if (typeof data.error === 'string') code = data.error;
      if (typeof data.detail === 'string') detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    if (response.status === 401) {
      markUnauthorizedResponse();
    }
    throw new ApiError(response.status, code, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export class LumiApiClient {
  // -------------------------------------------------- Health
  health(): Promise<HealthResponse> {
    return request('GET', '/health');
  }

  // -------------------------------------------------- Me / Settings
  getMe(): Promise<MeResponse> {
    return request('GET', '/api/me');
  }

  getSettings(): Promise<SettingsResponse> {
    return request('GET', '/api/settings');
  }

  getTimezones(): Promise<TimezonesResponse> {
    return request('GET', '/api/timezones');
  }

  patchSettings(input: PatchSettingsInput): Promise<MeResponse> {
    return request('PATCH', '/api/settings', { body: input });
  }

  // -------------------------------------------------- Today
  getToday(): Promise<TodayResponse> {
    return request('GET', '/api/today');
  }

  // -------------------------------------------------- Chat history
  getMessages(limit = 50): Promise<MessagesResponse> {
    return request('GET', '/api/messages', { query: { limit } });
  }

  // -------------------------------------------------- Tasks
  listTasks(filter: TaskFilter = 'all', limit = 100, project_id?: string): Promise<TasksResponse> {
    return request('GET', '/api/tasks', { query: { filter, limit, project_id } });
  }

  createTask(input: CreateTaskInput): Promise<TaskResponse> {
    return request('POST', '/api/tasks', { body: input });
  }

  patchTask(id: string, input: PatchTaskInput): Promise<TaskResponse> {
    return request('PATCH', `/api/tasks/${id}`, { body: input });
  }

  completeTask(id: string): Promise<TaskResponse> {
    return request('POST', `/api/tasks/${id}/complete`);
  }

  snoozeTask(id: string, input: SnoozeInput): Promise<TaskResponse> {
    return request('POST', `/api/tasks/${id}/snooze`, { body: input });
  }

  listProjects(): Promise<ProjectsResponse> {
    return request('GET', '/api/projects');
  }

  listAssistantSuggestions(kind?: string): Promise<AssistantSuggestionsResponse> {
    return request('GET', '/api/assistant/suggestions', { query: { kind } });
  }

  acceptAssistantSuggestion(id: string): Promise<AssistantSuggestionResponse> {
    return request('POST', `/api/assistant/suggestions/${id}/accept`);
  }

  dismissAssistantSuggestion(id: string): Promise<AssistantSuggestionResponse> {
    return request('POST', `/api/assistant/suggestions/${id}/dismiss`);
  }

  // -------------------------------------------------- Focus
  getFocusState(): Promise<FocusStateResponse> {
    return request('GET', '/api/focus/state');
  }

  getFocusSummary(input: FocusPeriod | FocusRangeQuery = 'week'): Promise<FocusSummaryResponse> {
    const query = typeof input === 'string' ? { period: input } : input;
    return request('GET', '/api/focus/summary', { query: query as Record<string, string | number | undefined> });
  }

  listFocusSessions(input: FocusPeriod | FocusRangeQuery = 'week', limit = 100): Promise<FocusSessionsResponse> {
    const query = typeof input === 'string' ? { period: input, limit } : { limit, ...input };
    return request('GET', '/api/focus/sessions', { query: query as Record<string, string | number | undefined> });
  }

  startFocusSession(input: StartFocusSessionInput): Promise<FocusSessionResponse> {
    return request('POST', '/api/focus/sessions', { body: input });
  }

  logFocusSession(input: LogFocusSessionInput): Promise<FocusSessionResponse> {
    return request('POST', '/api/focus/sessions/log', { body: input });
  }

  finishFocusSession(id: string, input: FinishFocusSessionInput): Promise<FocusSessionResponse> {
    return request('POST', `/api/focus/sessions/${id}/finish`, { body: input });
  }

  updateFocusSession(id: string, input: UpdateFocusSessionInput): Promise<FocusSessionResponse> {
    return request('PATCH', `/api/focus/sessions/${id}`, { body: input });
  }

  deleteFocusSession(id: string): Promise<void> {
    return request('DELETE', `/api/focus/sessions/${id}`);
  }

  abandonFocusSession(id: string): Promise<FocusSessionResponse> {
    return request('POST', `/api/focus/sessions/${id}/abandon`);
  }

  // -------------------------------------------------- Calendar
  listCalendarEvents(start: string, end: string): Promise<CalendarEventsResponse> {
    return request('GET', '/api/calendar/events', { query: { start, end } });
  }

  createCalendarEvent(input: CreateEventInput): Promise<CalendarEventResponse> {
    return request('POST', '/api/calendar/events', { body: input });
  }

  updateCalendarPrivateNote(id: string, input: PrivateNoteInput): Promise<CalendarEventResponse> {
    return request('PUT', `/api/calendar/events/${id}/private-note`, { body: input });
  }

  planDay(date?: string): Promise<RunRef> {
    return request('POST', '/api/calendar/plan-day', { body: date ? { date } : {} });
  }

  confirmBlock(id: string): Promise<CalendarEventResponse> {
    return request('POST', `/api/calendar/blocks/${id}/confirm`);
  }

  acceptConfirmation(id: string): Promise<ConfirmationDecisionResponse> {
    return request('POST', `/api/confirmations/${id}/accept`);
  }

  rejectConfirmation(id: string): Promise<ConfirmationDecisionResponse> {
    return request('POST', `/api/confirmations/${id}/reject`);
  }

  deleteCalendarEvent(id: string): Promise<OkResponse> {
    return request('DELETE', `/api/calendar/events/${id}`);
  }

  deleteCalendarPrivateNote(id: string): Promise<CalendarEventResponse> {
    return request('DELETE', `/api/calendar/events/${id}/private-note`);
  }

  syncCalendar(): Promise<RunRef> {
    return request('POST', '/api/calendar/sync');
  }

  getFreeSlots(date: string, duration = 60): Promise<FreeSlotsResponse> {
    return request('GET', '/api/calendar/free-slots', { query: { date, duration } });
  }

  // -------------------------------------------------- Inbox
  getInboxSummary(): Promise<InboxSummaryResponse> {
    return request('GET', '/api/inbox/summary');
  }

  runEmailTriage(): Promise<RunRef> {
    return request('POST', '/api/inbox/triage/run');
  }

  createTaskFromThread(threadId: string): Promise<TaskResponse> {
    return request('POST', `/api/inbox/threads/${threadId}/create-task`);
  }

  // -------------------------------------------------- News
  listNewsTopics(): Promise<NewsTopicsResponse> {
    return request('GET', '/api/news/topics');
  }

  createNewsTopic(input: CreateNewsTopicInput): Promise<NewsTopicResponse> {
    return request('POST', '/api/news/topics', { body: input });
  }

  patchNewsTopic(id: string, input: PatchNewsTopicInput): Promise<NewsTopicResponse> {
    return request('PATCH', `/api/news/topics/${id}`, { body: input });
  }

  listNewsDigests(limit = 5): Promise<NewsDigestsResponse> {
    return request('GET', '/api/news/digests', { query: { limit } });
  }

  runNewsDigest(): Promise<RunRef> {
    return request('POST', '/api/news/digest/run');
  }

  // -------------------------------------------------- Automations
  listAutomations(): Promise<AutomationsResponse> {
    return request('GET', '/api/automations');
  }

  createAutomation(input: CreateAutomationInput): Promise<AutomationResponse> {
    return request('POST', '/api/automations', { body: input });
  }

  patchAutomation(id: string, input: PatchAutomationInput): Promise<AutomationResponse> {
    return request('PATCH', `/api/automations/${id}`, { body: input });
  }

  runAutomation(id: string): Promise<RunRef> {
    return request('POST', `/api/automations/${id}/run`);
  }

  // -------------------------------------------------- Memory
  listMemories(params: { kind?: string; status?: string } = {}): Promise<MemoriesResponse> {
    return request('GET', '/api/memories', { query: { kind: params.kind, status: params.status ?? 'active' } });
  }

  patchMemory(id: string, input: PatchMemoryInput): Promise<MemoryResponse> {
    return request('PATCH', `/api/memories/${id}`, { body: input });
  }

  deleteMemory(id: string): Promise<OkResponse> {
    return request('DELETE', `/api/memories/${id}`);
  }

  // -------------------------------------------------- Agent runs
  listAgentRuns(limit = 30, type?: string): Promise<AgentRunsResponse> {
    return request('GET', '/api/agent-runs', { query: { limit, type } });
  }

  getAgentRun(id: string): Promise<AgentRunDetailResponse> {
    return request('GET', `/api/agent-runs/${id}`);
  }

  // -------------------------------------------------- Connectors
  getGoogleStatus(): Promise<GoogleStatus> {
    return request('GET', '/api/connectors/google/status');
  }

  disconnectGoogle(): Promise<OkResponse> {
    return request('POST', '/api/connectors/google/disconnect');
  }

  getGoogleAuthUrl(): Promise<{ url: string; redirect_uri: string }> {
    return request('GET', '/api/connectors/google/auth-url');
  }

  getYandexStatus(): Promise<YandexStatus> {
    return request('GET', '/api/connectors/yandex/status');
  }

  connectYandex(input: YandexConnectInput): Promise<YandexStatus> {
    return request('POST', '/api/connectors/yandex/connect', { body: input });
  }

  disconnectYandex(): Promise<OkResponse> {
    return request('POST', '/api/connectors/yandex/disconnect');
  }
}

export const api = new LumiApiClient();
