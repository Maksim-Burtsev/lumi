/**
 * TypeScript types matching docs/api-contract.md exactly.
 * All timestamps are ISO-8601 strings with timezone offset.
 */

// ---------------------------------------------------------------- Health

export interface HealthResponse {
  status: string;
  app: string;
  env: string;
  version: string;
}

// ---------------------------------------------------------------- Me / Settings

export interface User {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  timezone: string;
  locale: string;
  settings: Record<string, unknown>;
  created_at: string;
  last_seen_at: string | null;
}

export interface MeResponse {
  user: User;
}

export type LlmProvider = 'minimax' | 'mock';

export interface LlmStatus {
  provider: LlmProvider;
  model: string;
  configured: boolean;
}

export interface AppFlags {
  store_email_bodies: boolean;
  store_llm_debug_payloads: boolean;
  dev_auth: boolean;
}

export interface AppInfo {
  public_url: string | null;
  env: string;
}

export interface YandexStatus {
  status: 'disconnected' | 'connected' | 'error' | 'needs_reauth';
  username: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  /** Present in the connect response: id of the auto-started first sync. */
  run_id?: string;
}

export interface YandexConnectInput {
  username: string;
  app_password: string;
}

export interface SettingsResponse {
  user: User;
  llm: LlmStatus;
  google: GoogleStatus;
  yandex: YandexStatus;
  flags: AppFlags;
  app: AppInfo;
}

export interface TimezoneItem {
  id: string;
}

export interface TimezonesResponse {
  items: TimezoneItem[];
}

export type TimeFormat = 'auto' | '24h' | '12h';

export interface PatchSettingsInput {
  timezone?: string;
  locale?: string;
  reply_language_mode?: 'auto' | 'app_locale';
  time_format?: TimeFormat;
  settings?: Record<string, unknown>;
}

// ---------------------------------------------------------------- Today

export interface TodaySummary {
  meetings_today: number;
  tasks_active: number;
  tasks_due_today: number;
  tasks_overdue: number;
  emails_need_reply: number;
}

export type TimelineKind = 'event' | 'focus' | 'proposed' | 'task';
export type EventSource = 'internal' | 'google' | 'yandex';
export type EventStatus = 'confirmed' | 'tentative' | 'proposed' | 'cancelled';

export interface TimelineItem {
  id: string;
  kind: TimelineKind;
  title: string;
  start_at: string;
  end_at: string;
  source: EventSource;
  status: EventStatus;
  busy: boolean;
}

export type AttentionKind = 'overdue_task' | 'due_task' | 'email' | 'confirmation';
export type RiskClass =
  | 'write_internal'
  | 'write_internal_memory'
  | 'write_internal_scheduled'
  | 'write_external'
  | 'external_communication'
  | 'destructive'
  | 'unknown';
export type ApprovalMode = 'auto' | 'auto_or_confirm' | 'confirm' | 'draft_then_confirm' | 'strong_confirm';
export type AttentionUiMode = 'none' | 'inline_confirm' | 'review_then_confirm' | 'strong_confirm';

export interface AttentionItem {
  id: string;
  kind: AttentionKind;
  title: string;
  subtitle: string | null;
  ref_id: string | null;
  action_type?: string;
  action_payload?: Record<string, unknown>;
  risk_class?: RiskClass;
  approval_mode?: ApprovalMode;
  ui_mode?: AttentionUiMode;
  primary_label?: string;
  secondary_label?: string;
}

export interface PendingConfirmation {
  id: string;
  action_type: string;
  title: string;
  status: 'pending' | 'accepted' | 'rejected' | 'expired';
  action_payload: Record<string, unknown>;
  created_at: string | null;
  expires_at: string | null;
  decided_at: string | null;
  risk_class: RiskClass;
  approval_mode: ApprovalMode;
  ui_mode: AttentionUiMode;
  primary_label: string;
  secondary_label: string;
}

export interface ConfirmationDecisionResponse {
  confirmation: PendingConfirmation;
  result_text: string;
  executed: boolean;
}

export type SuggestionKind = 'focus_block' | 'plan_day' | 'email_triage' | 'news_digest';
export type SuggestionActionType = 'plan_day' | 'run_triage' | 'run_digest' | 'confirm_block';

export interface SuggestionAction {
  type: SuggestionActionType;
  payload: Record<string, unknown>;
}

export interface Suggestion {
  id: string;
  kind: SuggestionKind;
  title: string;
  description: string | null;
  action: SuggestionAction;
}

export interface AgentRunBrief {
  id: string;
  type: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  result_summary: string | null;
}

export interface TodayResponse {
  date: string;
  greeting: string;
  summary: TodaySummary;
  timeline: TimelineItem[];
  needs_attention: AttentionItem[];
  suggestions: Suggestion[];
  recent_runs: AgentRunBrief[];
}

// ---------------------------------------------------------------- Chat history

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface MessagesResponse {
  items: ChatMessage[];
}

// ---------------------------------------------------------------- Tasks

export type TaskStatus = 'inbox' | 'active' | 'done' | 'cancelled';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';
export type TaskFilter = 'today' | 'upcoming' | 'inbox' | 'done' | 'all';

export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  project: string | null;
  tags: string[];
  due_at: string | null;
  reminder_at: string | null;
  snoozed_until: string | null;
  source: string;
  created_at: string;
  completed_at: string | null;
}

export interface TasksResponse {
  items: Task[];
}

export interface TaskResponse {
  task: Task;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  priority?: TaskPriority;
  project?: string;
  tags?: string[];
  due_at?: string;
  reminder_at?: string;
}

export interface PatchTaskInput {
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  project?: string | null;
  tags?: string[];
  due_at?: string | null;
  reminder_at?: string | null;
}

export type SnoozePreset = '1h' | '3h' | 'tomorrow' | 'next_week';

export type SnoozeInput = { preset: SnoozePreset } | { until: string };

// ---------------------------------------------------------------- Focus

export type FocusSessionStatus = 'active' | 'completed' | 'abandoned';

export interface FocusReflection {
  accomplished_text: string | null;
  distraction_text: string | null;
  next_step_text: string | null;
  focus_score: number | null;
}

export interface FocusSession {
  id: string;
  status: FocusSessionStatus;
  task: Task | null;
  project: string | null;
  intention: string;
  planned_minutes: number;
  started_at: string;
  target_end_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  reflection: FocusReflection;
}

export interface FocusTodaySummary {
  focus_seconds: number;
  completed_sessions: number;
  streak_days: number;
}

export interface FocusStateResponse {
  active_session: FocusSession | null;
  today: FocusTodaySummary;
  recent_sessions: FocusSession[];
}

export interface StartFocusSessionInput {
  task_id?: string | null;
  project?: string | null;
  intention: string;
  planned_minutes: number;
}

export interface FinishFocusSessionInput {
  ended_at?: string;
  accomplished_text?: string | null;
  distraction_text?: string | null;
  next_step_text?: string | null;
  focus_score?: number | null;
}

export interface FocusSessionResponse {
  session: FocusSession;
}

export interface FocusDailyActivity {
  date: string;
  focus_seconds: number;
  session_count: number;
}

export interface FocusProjectBreakdown {
  project: string;
  focus_seconds: number;
  session_count: number;
}

export interface FocusSummaryResponse {
  period: 'week' | 'month';
  total_focus_seconds: number;
  total_sessions: number;
  streak_days: number;
  average_focus_score: number | null;
  daily_activity: FocusDailyActivity[];
  project_breakdown: FocusProjectBreakdown[];
  next_steps: string[];
}

// ---------------------------------------------------------------- Calendar

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  start_at: string;
  end_at: string;
  all_day: boolean;
  busy: boolean;
  status: EventStatus;
  source: EventSource;
  created_by: string;
  location: string | null;
  meeting_url: string | null;
  external_url: string | null;
  links: string[];
  last_synced_at: string | null;
  organizer: CalendarPerson | null;
  attendees: CalendarAttendee[];
  attendee_count: number;
  user_response_status: string | null;
}

export interface CalendarPerson {
  name?: string;
  email?: string;
}

export interface CalendarAttendee extends CalendarPerson {
  response_status?: string | null;
  optional?: boolean;
  resource?: boolean;
  organizer?: boolean;
  self?: boolean;
  rsvp?: boolean;
}

export interface CalendarSyncState {
  connected: boolean;
  last_sync_at: string | null;
  stale: boolean;
  refresh_queued: boolean;
}

export interface CalendarEventsResponse {
  items: CalendarEvent[];
  sync?: CalendarSyncState;
}

export interface CalendarEventResponse {
  event: CalendarEvent;
}

export interface CreateEventInput {
  title: string;
  start_at: string;
  end_at: string;
  description?: string;
  location?: string;
  meeting_url?: string;
  external_url?: string;
  links?: string[];
}

export interface FreeSlot {
  start_at: string;
  end_at: string;
}

export interface FreeSlotsResponse {
  items: FreeSlot[];
}

// ---------------------------------------------------------------- Runs (enqueue ref)

export interface RunRef {
  run_id: string;
  status: string;
}

// ---------------------------------------------------------------- Inbox

export interface InboxCounts {
  needs_reply: number;
  waiting_for_me: number;
  decision_needed: number;
  fyi: number;
  newsletter: number;
  invoice_document: number;
  ignore: number;
  unknown: number;
}

export interface TaskCandidate {
  title: string;
  due_at: string | null;
  priority: string;
}

export interface EmailThread {
  id: string;
  subject: string | null;
  sender: string | null;
  snippet: string | null;
  category: string;
  importance: number;
  summary: string | null;
  suggested_action: string | null;
  last_message_at: string | null;
  task_candidate: TaskCandidate | null;
}

export interface InboxSummaryResponse {
  connected: boolean;
  last_triage_at: string | null;
  counts: InboxCounts;
  threads: EmailThread[];
}

// ---------------------------------------------------------------- News

export interface NewsTopic {
  id: string;
  title: string;
  query: string;
  language: string;
  enabled: boolean;
  created_at: string;
}

export interface NewsTopicsResponse {
  items: NewsTopic[];
}

export interface NewsTopicResponse {
  topic: NewsTopic;
}

export interface CreateNewsTopicInput {
  title: string;
  query: string;
  language?: string;
}

export interface PatchNewsTopicInput {
  title?: string;
  query?: string;
  language?: string;
  enabled?: boolean;
}

export interface NewsDigest {
  id: string;
  title: string;
  digest_text: string;
  created_at: string;
}

export interface NewsDigestsResponse {
  items: NewsDigest[];
}

// ---------------------------------------------------------------- Automations

export type AutomationType =
  | 'morning_brief'
  | 'news_digest'
  | 'email_triage'
  | 'daily_planning'
  | 'calendar_sync'
  | 'task_review'
  | 'custom_prompt';

export interface Automation {
  id: string;
  type: AutomationType;
  title: string;
  cron_expression: string;
  timezone: string;
  enabled: boolean;
  config: Record<string, unknown>;
  last_run_at: string | null;
  next_run_at: string | null;
  failure_count: number;
  last_error: string | null;
}

export interface AutomationsResponse {
  items: Automation[];
}

export interface AutomationResponse {
  automation: Automation;
}

export interface CreateAutomationInput {
  type: AutomationType;
  title: string;
  cron_expression: string;
  timezone?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
  /** One-shot: fire once at this ISO datetime instead of a cron schedule. */
  run_at?: string;
}

export interface PatchAutomationInput {
  title?: string;
  cron_expression?: string;
  timezone?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
}

// ---------------------------------------------------------------- Memory

export type MemoryKind = 'preference' | 'fact' | 'project' | 'instruction' | 'contact' | 'workflow' | 'other';
export type MemoryStatus = 'active' | 'archived';
export type MemorySource = 'chat' | 'email' | 'agent' | 'manual';

export interface Memory {
  id: string;
  kind: MemoryKind;
  status: MemoryStatus;
  text: string;
  tags: string[];
  importance: number;
  confidence: number;
  source: MemorySource | null;
  created_at: string;
  last_accessed_at: string | null;
}

export interface MemoriesResponse {
  items: Memory[];
}

export interface MemoryResponse {
  memory: Memory;
}

export interface PatchMemoryInput {
  status?: MemoryStatus;
  text?: string;
  importance?: number;
}

// ---------------------------------------------------------------- Agent runs

export interface AgentRunListItem extends AgentRunBrief {
  trigger: string;
  input_summary: string | null;
  error_message: string | null;
}

export interface AgentRunsResponse {
  items: AgentRunListItem[];
}

/** Full run object — brief fields plus whatever extra detail backend stores. */
export interface AgentRun extends AgentRunBrief {
  trigger?: string | null;
  input_summary?: string | null;
  error_message?: string | null;
  started_at?: string | null;
}

export interface ToolCall {
  id: string;
  tool_name: string;
  status: string;
  args_json: unknown;
  result_json: unknown;
  error_message: string | null;
  created_at: string;
}

export interface LlmCall {
  id: string;
  provider: string;
  model: string;
  request_kind: string;
  status: string;
  latency_ms: number | null;
  input_char_count: number | null;
  output_char_count: number | null;
  created_at: string;
}

export interface AgentRunDetailResponse {
  run: AgentRun;
  tool_calls: ToolCall[];
  llm_calls: LlmCall[];
}

// ---------------------------------------------------------------- Connectors

export type GoogleConnectionStatus = 'disconnected' | 'connected' | 'error' | 'needs_reauth';

export interface GoogleStatus {
  status: GoogleConnectionStatus;
  scopes: string[];
  last_sync_at: string | null;
  last_error: string | null;
  gmail_available: boolean;
  calendar_available: boolean;
}

export interface OkResponse {
  ok: boolean;
}
