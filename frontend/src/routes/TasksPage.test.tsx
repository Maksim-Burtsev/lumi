import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { Project, SettingsResponse, Task, TaskFilter, TasksResponse, User } from '../api/types';
import { TaskEditSheet } from '../components/task/TaskEditSheet';
import { ToastProvider } from '../components/ui/Toast';
import TasksPage from './TasksPage';

function makeUser(locale: 'en' | 'ru' = 'en'): User {
  return {
    id: 'user-1',
    telegram_user_id: 777000,
    username: 'tester',
    first_name: 'Test',
    last_name: 'User',
    timezone: 'Asia/Yerevan',
    locale,
    settings: { reply_language_mode: 'auto', time_format: '24h' },
    created_at: '2026-07-15T00:00:00Z',
    last_seen_at: null,
  };
}

function makeSettings(locale: 'en' | 'ru' = 'en'): SettingsResponse {
  return {
    user: makeUser(locale),
    llm: { provider: 'mock', model: 'mock-1', configured: true },
    google: {
      status: 'disconnected',
      gmail_available: false,
      calendar_available: false,
      scopes: [],
      last_sync_at: null,
      last_error: null,
    },
    yandex: { status: 'disconnected', username: null, last_sync_at: null, last_error: null },
    flags: { store_email_bodies: false, store_llm_debug_payloads: false, dev_auth: true },
    app: { public_url: null, env: 'local' },
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  const status = overrides.status ?? 'active';
  const bucket = overrides.bucket ?? (status === 'done' ? 'done' : status === 'inbox' ? 'inbox' : 'later');
  return {
    id: 'task-1',
    title: 'Compare Mira design',
    description: null,
    status,
    priority: 'medium',
    project: null,
    project_id: null,
    tags: [],
    due_at: null,
    planned_for: null,
    target_at: null,
    reminder_at: null,
    snoozed_until: null,
    estimated_minutes: null,
    estimate_source: null,
    review_skips: {},
    source: 'manual',
    created_at: '2026-07-15T08:00:00Z',
    completed_at: status === 'done' ? '2026-07-15T09:00:00Z' : null,
    bucket,
    ...overrides,
  };
}

function makeTasksResponse(
  items: Task[] = [],
  pagination: Pick<TasksResponse, 'has_more' | 'next_offset'> = { has_more: false, next_offset: null },
): TasksResponse {
  return { items, ...pagination };
}

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'project-lumi',
    name: 'Lumi',
    status: 'active',
    color: null,
    system_key: null,
    is_system: false,
    active_task_count: 1,
    completed_task_count: 0,
    estimated_minutes_total: 30,
    health_status: 'moving',
    health_reason: 'Updated today',
    next_task: null,
    created_at: '2026-07-15T08:00:00Z',
    ...overrides,
  };
}

function mockBuckets(lists: Partial<Record<TaskFilter, Task[]>> = {}) {
  return vi.spyOn(api, 'listTasks').mockImplementation(async (query) => (
    makeTasksResponse(lists[query?.filter ?? 'all'] ?? [])
  ));
}

function renderTasksPage(projects: Project[] = [], locale: 'en' | 'ru' = 'en') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettings(locale));
  vi.spyOn(api, 'listProjects').mockResolvedValue({ items: projects });
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TasksPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function renderTaskEditor(task: Task, timezone = 'Asia/Yerevan') {
  const settings = makeSettings();
  settings.user.timezone = timezone;
  vi.spyOn(api, 'getSettings').mockResolvedValue(settings);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TaskEditSheet task={task} projects={[]} onClose={vi.fn()} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('TasksPage V2', () => {
  it('shows the three open groups and weekly capacity without legacy tabs', async () => {
    mockBuckets({
      inbox: [makeTask({ id: 'inbox-1', title: 'Triage notes', status: 'inbox', bucket: 'inbox' })],
      this_week: [
        makeTask({ id: 'week-1', title: 'Write launch copy', bucket: 'this_week', estimated_minutes: 30 }),
        makeTask({ id: 'week-2', title: 'Review release', bucket: 'this_week', estimated_minutes: 90 }),
      ],
      later: [makeTask({ id: 'later-1', title: 'Refresh archive', bucket: 'later' })],
    });

    renderTasksPage();

    await waitFor(() => {
      expect(screen.getByText('Triage notes')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Inbox' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'This week' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Later' })).toBeInTheDocument();
      expect(screen.getByText('2 h estimated')).toBeInTheDocument();
    });
    expect(screen.queryByText('Today')).not.toBeInTheDocument();
    expect(screen.queryByText('Projects')).not.toBeInTheDocument();
    expect(screen.queryByText('Review')).not.toBeInTheDocument();
  });

  it('sends search and project filters to every open task query', async () => {
    const listSpy = mockBuckets();
    const user = userEvent.setup();
    renderTasksPage([makeProject()]);

    await screen.findByRole('option', { name: 'Lumi' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by project' }), 'project-lumi');
    await user.type(screen.getByRole('searchbox', { name: 'Search tasks' }), 'launch');

    await waitFor(() => {
      for (const filter of ['inbox', 'this_week', 'later'] as const) {
        expect(listSpy).toHaveBeenCalledWith(expect.objectContaining({
          filter,
          q: 'launch',
          project_id: 'project-lumi',
          limit: 20,
          offset: 0,
        }));
      }
    });
  });

  it('creates from the inline field on Enter and preserves the title on failure', async () => {
    mockBuckets();
    const createSpy = vi.spyOn(api, 'createTask').mockRejectedValue(new Error('offline'));
    const user = userEvent.setup();
    renderTasksPage();

    const input = await screen.findByRole('textbox', { name: 'Add a task to Inbox' });
    await user.type(input, 'Keep this title{Enter}');

    await waitFor(() => expect(createSpy).toHaveBeenCalledWith({ title: 'Keep this title' }));
    expect(await screen.findByText('Could not create task')).toBeInTheDocument();
    expect(input).toHaveValue('Keep this title');
  });

  it('loads the next server page into its group', async () => {
    const listSpy = vi.spyOn(api, 'listTasks').mockImplementation(async (query) => {
      if (query?.filter !== 'inbox') return makeTasksResponse();
      if (query.offset === 20) return makeTasksResponse([makeTask({ id: 'inbox-2', title: 'Second page', status: 'inbox', bucket: 'inbox' })]);
      return makeTasksResponse(
        [makeTask({ id: 'inbox-1', title: 'First page', status: 'inbox', bucket: 'inbox' })],
        { has_more: true, next_offset: 20 },
      );
    });
    const user = userEvent.setup();
    renderTasksPage();

    await waitFor(() => expect(screen.getByText('First page')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Load more' }));

    await waitFor(() => expect(screen.getByText('Second page')).toBeInTheDocument());
    expect(listSpy).toHaveBeenCalledWith(expect.objectContaining({ filter: 'inbox', limit: 20, offset: 20 }));
  });

  it('opens details from the title and completes only from the checkbox', async () => {
    const task = makeTask({ id: 'deep-work', title: 'Deep work', status: 'inbox', bucket: 'inbox' });
    mockBuckets({ inbox: [task] });
    const completeSpy = vi.spyOn(api, 'completeTask').mockResolvedValue({
      task: { ...task, status: 'done', bucket: 'done', completed_at: '2026-07-15T10:00:00Z' },
    });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({ task });
    const user = userEvent.setup();
    renderTasksPage();

    await waitFor(() => expect(screen.getByRole('button', { name: 'Open details: Deep work' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open details: Deep work' }));
    expect(completeSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Task details' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Task details' })).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Complete: Deep work' }));
    await waitFor(() => expect(completeSpy).toHaveBeenCalledWith('deep-work'));
    await waitFor(
      () => expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument(),
      { timeout: 3000 },
    );
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(
      () => expect(patchSpy).toHaveBeenCalledWith('deep-work', { status: 'active' }),
      { timeout: 3000 },
    );
  });

  it('restores the right row when concurrent completions settle out of order', async () => {
    const first = makeTask({ id: 'first', title: 'First task', status: 'inbox', bucket: 'inbox' });
    const second = makeTask({ id: 'second', title: 'Second task', status: 'inbox', bucket: 'inbox' });
    mockBuckets({ inbox: [first, second] });
    let rejectFirst: (reason: Error) => void = () => undefined;
    const firstRequest = new Promise<{ task: Task }>((_resolve, reject) => { rejectFirst = reject; });
    vi.spyOn(api, 'completeTask').mockImplementation((id) => (
      id === first.id
        ? firstRequest
        : Promise.resolve({ task: { ...second, status: 'done', bucket: 'done', completed_at: '2026-07-15T10:00:00Z' } })
    ));
    renderTasksPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Complete: First task' }));
    fireEvent.click(screen.getByRole('button', { name: 'Complete: Second task' }));
    expect(screen.queryByRole('button', { name: 'Complete: First task' })).not.toBeInTheDocument();

    await act(async () => rejectFirst(new Error('offline')));

    expect(await screen.findByRole('button', { name: 'Complete: First task' })).toBeInTheDocument();
    expect(await screen.findByText('Could not complete task')).toBeInTheDocument();
  });

  it('edits estimate and hard deadline while moving a task to This week', async () => {
    const task = makeTask({ id: 'move-me', title: 'Move me', status: 'inbox', bucket: 'inbox' });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...task, status: 'active', bucket: 'this_week' },
    });
    renderTaskEditor(task);

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Task details' }).closest('[inert]')).toBeNull());
    fireEvent.change(screen.getByDisplayValue('Inbox'), { target: { value: 'this_week' } });
    expect(screen.getByDisplayValue('This week')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('30'), { target: { value: '45' } });
    expect(screen.getByPlaceholderText('30')).toHaveValue(45);
    const deadline = '2035-07-17T18:00';
    const deadlineInput = screen.getByRole('dialog', { name: 'Task details' })
      .querySelector<HTMLInputElement>('input[type="datetime-local"]');
    expect(deadlineInput).not.toBeNull();
    fireEvent.change(deadlineInput as HTMLInputElement, { target: { value: deadline } });
    expect(screen.getByDisplayValue(deadline)).toBeInTheDocument();
    const saveButton = screen.getByRole('button', { name: 'Save changes' });
    expect(saveButton).toBeEnabled();
    saveButton.click();

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('move-me', expect.objectContaining({
        status: 'active',
        planned_for: expect.any(String),
        estimated_minutes: 45,
        due_at: '2035-07-17T14:00:00.000Z',
      }));
    });
  });

  it('renders and preserves hard deadlines in the profile timezone', async () => {
    const task = makeTask({ id: 'timezone-deadline', due_at: '2035-07-17T14:00:00Z' });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({ task });
    renderTaskEditor(task, 'Pacific/Chatham');

    await screen.findByRole('dialog', { name: 'Task details' });
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Task details' }).closest('[inert]')).toBeNull());
    await waitFor(() => expect(screen.getByLabelText('Hard deadline')).toHaveValue('2035-07-18T02:45'));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith(
      'timezone-deadline',
      expect.objectContaining({ due_at: '2035-07-17T14:00:00.000Z' }),
    ));
  });

  it('preserves a Later plan and an unavailable current project on ordinary edits', async () => {
    const plannedFor = '2035-08-13T09:00:00Z';
    const task = makeTask({
      id: 'preserve-me',
      title: 'Preserve me',
      bucket: 'later',
      planned_for: plannedFor,
      project: 'Archived work',
      project_id: 'archived-project',
    });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({ task });
    renderTaskEditor(task);

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Task details' }).closest('[inert]')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const input = patchSpy.mock.calls[0]?.[1];
    expect(input).toEqual(expect.objectContaining({ status: 'active', planned_for: plannedFor }));
    expect(input).not.toHaveProperty('project');
    expect(input).not.toHaveProperty('project_id');
  });

  it('opens the Done archive and reopens a completed task', async () => {
    const done = makeTask({ id: 'done-1', title: 'Archived task', status: 'done', bucket: 'done' });
    mockBuckets({ done: [done] });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...done, status: 'active', bucket: 'later', completed_at: null },
    });
    const user = userEvent.setup();
    renderTasksPage();

    await user.click(await screen.findByRole('button', { name: 'Done' }));
    expect(await screen.findByRole('heading', { name: 'Done archive' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reopen: Archived task' }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith('done-1', { status: 'active' }));
  });

  it('shows the global empty state', async () => {
    mockBuckets();
    renderTasksPage();

    expect(await screen.findByText('No open tasks')).toBeInTheDocument();
    expect(screen.getByText('Capture the next thing above. It will land in Inbox.')).toBeInTheDocument();
  });

  it('shows a section error and retries it', async () => {
    let inboxAttempts = 0;
    vi.spyOn(api, 'listTasks').mockImplementation(async (query) => {
      if (query?.filter !== 'inbox') return makeTasksResponse();
      inboxAttempts += 1;
      if (inboxAttempts === 1) throw new Error('offline');
      return makeTasksResponse([makeTask({ id: 'recovered', title: 'Recovered task', status: 'inbox', bucket: 'inbox' })]);
    });
    const user = userEvent.setup();
    renderTasksPage();

    expect(await screen.findByText('Could not load this list.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Recovered task')).toBeInTheDocument();
    expect(inboxAttempts).toBe(2);
  });
});
