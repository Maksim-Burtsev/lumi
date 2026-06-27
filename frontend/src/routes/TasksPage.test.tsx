import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { AssistantSuggestion, AssistantSuggestionsResponse, Project, ProjectsResponse, SettingsResponse, Task, TasksResponse, User } from '../api/types';
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
    created_at: '2026-06-21T00:00:00Z',
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

function makeTask(overrides: Partial<Task>): Task {
  return {
    id: overrides.id ?? 'task-1',
    title: overrides.title ?? 'Compare Mira design',
    description: null,
    status: 'active',
    priority: 'medium',
    project: null,
    project_id: null,
    tags: [],
    due_at: null,
    target_at: null,
    reminder_at: null,
    snoozed_until: null,
    estimated_minutes: null,
    estimate_source: null,
    review_skips: {},
    source: 'manual',
    created_at: '2026-06-21T08:00:00Z',
    completed_at: null,
    ...overrides,
  };
}

function makeProject(overrides: Partial<Project>): Project {
  return {
    id: overrides.id ?? 'project-1',
    name: overrides.name ?? 'Lumi',
    status: 'active',
    color: null,
    system_key: null,
    is_system: false,
    active_task_count: 1,
    completed_task_count: 0,
    estimated_minutes_total: 0,
    health_status: 'moving',
    health_reason: 'Next move ready',
    next_task: null,
    created_at: '2026-06-21T08:00:00Z',
    ...overrides,
  };
}

function renderTasksPage(locale: 'en' | 'ru' = 'en') {
  vi.spyOn(api, 'getSettings').mockResolvedValue(makeSettings(locale));
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

  return queryClient;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('TasksPage Projects UX', () => {
  it('completes a task when the task row itself is tapped', async () => {
    const task = makeTask({ id: 'task-buy', title: 'Buy capsules' });
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [task] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });
    const completeSpy = vi.spyOn(api, 'completeTask').mockResolvedValue({
      task: { ...task, status: 'done', completed_at: '2026-06-21T08:02:00Z' },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: /Buy capsules/i }));

    await waitFor(() => {
      expect(completeSpy).toHaveBeenCalledWith('task-buy');
    });
    expect(screen.queryByRole('dialog', { name: 'Task' })).not.toBeInTheDocument();
  });

  it('uses the top field as search and opens task creation from the floating plus', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [
        makeTask({ id: 'task-1', title: 'Buy capsules' }),
        makeTask({ id: 'task-2', title: 'Compare Mira design' }),
      ],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });
    const createSpy = vi.spyOn(api, 'createTask').mockResolvedValue({
      task: makeTask({ id: 'task-new', title: 'Write launch notes' }),
    });

    const user = userEvent.setup();
    renderTasksPage('en');

    await user.type(await screen.findByRole('searchbox', { name: 'Search tasks' }), 'capsules');
    expect(screen.getByText('Buy capsules')).toBeInTheDocument();
    expect(screen.queryByText('Compare Mira design')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Add task' }));
    expect(screen.getByRole('dialog', { name: 'New task' })).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Task title' }), 'Write launch notes');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({ title: 'Write launch notes' });
    });
  });

  it('renders Health Stack projects without demotivating progress percentages', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({
      items: [
        makeProject({
          id: 'project-work',
          name: 'Work',
          active_task_count: 1,
          estimated_minutes_total: 45,
          health_status: 'needs_attention',
          health_reason: 'Quiet 4 days',
          next_task: makeTask({ id: 'task-work', title: 'Extend tool pool', project: 'Work', project_id: 'project-work' }),
        }),
        makeProject({
          id: 'project-lumi',
          name: 'Lumi',
          active_task_count: 2,
          completed_task_count: 1,
          estimated_minutes_total: 90,
          health_status: 'moving',
          health_reason: 'Updated today',
          next_task: makeTask({ id: 'task-lumi', title: 'Compare Mira design', project: 'Lumi', project_id: 'project-lumi' }),
        }),
      ],
    } satisfies ProjectsResponse);
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Projects' }));

    expect(screen.getByText('Project Health')).toBeInTheDocument();
    expect(screen.getAllByText('Needs attention').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Moving').length).toBeGreaterThan(0);
    expect(screen.getByText('Next: Extend tool pool')).toBeInTheDocument();
    expect(screen.getByText('Quiet 4 days')).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('opens an Attention First project detail when a project row is clicked', async () => {
    vi.spyOn(api, 'listTasks').mockImplementation(async (_filter, _limit, projectId) => ({
      items: projectId === 'project-work'
        ? [
            makeTask({ id: 'task-work', title: 'Extend tool pool', project: 'Work', project_id: 'project-work', estimated_minutes: 45 }),
            makeTask({ id: 'task-later', title: 'Write launch notes', project: 'Work', project_id: 'project-work' }),
          ]
        : [],
    }));
    vi.spyOn(api, 'listProjects').mockResolvedValue({
      items: [
        makeProject({
          id: 'project-work',
          name: 'Work',
          active_task_count: 2,
          estimated_minutes_total: 45,
          health_status: 'needs_attention',
          health_reason: 'Quiet 4 days',
          next_task: makeTask({ id: 'task-work', title: 'Extend tool pool', project: 'Work', project_id: 'project-work', estimated_minutes: 45 }),
        }),
      ],
    } satisfies ProjectsResponse);
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Projects' }));
    await user.click(screen.getByRole('button', { name: /Open project Work/i }));

    expect(await screen.findByText('Why it needs attention')).toBeInTheDocument();
    expect(screen.getByText('Next move')).toBeInTheDocument();
    expect(screen.getAllByText('Extend tool pool').length).toBeGreaterThan(0);
    expect(screen.getByText('Next')).toBeInTheDocument();
    expect(screen.getByText('Later')).toBeInTheDocument();
  });
});

describe('TasksPage Review and estimates', () => {
  it('opens a bulk estimate review from the Estimates category', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [
        makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi' }),
        makeTask({ id: 'task-2', title: 'Buy capsules', project: 'Shopping' }),
      ],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    const firstSuggestion = {
      id: 'suggestion-1',
      kind: 'task_estimate',
      status: 'pending',
      title: 'Estimate Compare Mira design',
      description: 'Fits a focus block today',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-1'],
      payload: { task_id: 'task-1', estimated_minutes: 45, reason: 'Fits a focus block today' },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:00:00Z',
    } satisfies AssistantSuggestion;
    const secondSuggestion = {
      id: 'suggestion-2',
      kind: 'task_estimate',
      status: 'pending',
      title: 'Estimate Buy capsules',
      description: 'Quick errand',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-2'],
      payload: { task_id: 'task-2', estimated_minutes: 10, reason: 'Quick errand' },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:01:00Z',
    } satisfies AssistantSuggestion;
    vi.spyOn(api, 'listAssistantSuggestions')
      .mockResolvedValueOnce({ items: [firstSuggestion, secondSuggestion] } satisfies AssistantSuggestionsResponse)
      .mockResolvedValue({ items: [secondSuggestion] } satisfies AssistantSuggestionsResponse);

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review estimates/i }));

    const dialog = screen.getByRole('dialog', { name: 'Estimate suggestions' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText('Compare Mira design')).toBeInTheDocument();
    expect(within(dialog).getByText('Buy capsules')).toBeInTheDocument();
    expect(within(dialog).getByText('45 min')).toBeInTheDocument();
    expect(within(dialog).getByText('10 min')).toBeInTheDocument();
  });

  it('keeps the bulk estimate review open and removes an accepted row', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [
        makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi' }),
        makeTask({ id: 'task-2', title: 'Buy capsules', project: 'Shopping' }),
      ],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    const firstSuggestion = {
      id: 'suggestion-1',
      kind: 'task_estimate',
      status: 'pending',
      title: 'Estimate Compare Mira design',
      description: 'Fits a focus block today',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-1'],
      payload: { task_id: 'task-1', estimated_minutes: 45, reason: 'Fits a focus block today' },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:00:00Z',
    } satisfies AssistantSuggestion;
    const secondSuggestion = {
      id: 'suggestion-2',
      kind: 'task_estimate',
      status: 'pending',
      title: 'Estimate Buy capsules',
      description: 'Quick errand',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-2'],
      payload: { task_id: 'task-2', estimated_minutes: 10, reason: 'Quick errand' },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:01:00Z',
    } satisfies AssistantSuggestion;
    vi.spyOn(api, 'listAssistantSuggestions')
      .mockResolvedValueOnce({ items: [firstSuggestion, secondSuggestion] } satisfies AssistantSuggestionsResponse)
      .mockResolvedValue({ items: [secondSuggestion] } satisfies AssistantSuggestionsResponse);
    vi.spyOn(api, 'acceptAssistantSuggestion').mockResolvedValue({
      suggestion: {
        id: 'suggestion-1',
        kind: 'task_estimate',
        status: 'accepted',
        title: 'Estimate Compare Mira design',
        description: 'Fits a focus block today',
        start_at: null,
        end_at: null,
        affected_task_ids: ['task-1'],
        payload: { task_id: 'task-1', estimated_minutes: 45 },
        expires_at: null,
        decided_at: '2026-06-21T08:01:00Z',
        created_at: '2026-06-21T08:00:00Z',
      },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review estimates/i }));
    await user.click(screen.getByRole('button', { name: /Accept estimate for Compare Mira design/i }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Estimate suggestions' })).toBeInTheDocument();
      expect(screen.queryByText('Compare Mira design')).not.toBeInTheDocument();
      expect(screen.getByText('Buy capsules')).toBeInTheDocument();
    });
  });

  it('lets the user change or permanently skip a rejected estimate', async () => {
    const task = makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi' });
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [task] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({
      items: [
        {
          id: 'suggestion-1',
          kind: 'task_estimate',
          status: 'pending',
          title: 'Estimate Compare Mira design',
          description: 'Fits a focus block today',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-1'],
          payload: { task_id: 'task-1', estimated_minutes: 45, reason: 'Fits a focus block today' },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:00:00Z',
        },
      ],
    } satisfies AssistantSuggestionsResponse);
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...task, estimate_source: 'skipped' },
    });
    const dismissSpy = vi.spyOn(api, 'dismissAssistantSuggestion').mockResolvedValue({
      suggestion: {
        id: 'suggestion-1',
        kind: 'task_estimate',
        status: 'dismissed',
        title: 'Estimate Compare Mira design',
        description: 'Fits a focus block today',
        start_at: null,
        end_at: null,
        affected_task_ids: ['task-1'],
        payload: { task_id: 'task-1', estimated_minutes: 45 },
        expires_at: null,
        decided_at: '2026-06-21T08:01:00Z',
        created_at: '2026-06-21T08:00:00Z',
      },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review estimates/i }));
    await user.click(screen.getByRole('button', { name: /Change estimate for Compare Mira design/i }));
    await user.click(screen.getByRole('button', { name: 'Do not estimate' }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('task-1', { estimated_minutes: null, estimate_source: 'skipped' });
      expect(dismissSpy).toHaveBeenCalledWith('suggestion-1');
    });
  });

  it('shows a prepared Review command center instead of raw task gaps', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [
        makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi', project_id: 'project-lumi' }),
        makeTask({ id: 'task-2', title: 'Need project', estimated_minutes: 15 }),
      ],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({
      items: [
        {
          id: 'suggestion-1',
          kind: 'task_estimate',
          status: 'pending',
          title: 'Estimate Compare Mira design',
          description: 'Fits a focus block today',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-1'],
          payload: { task_id: 'task-1', estimated_minutes: 45, reason: 'Fits a focus block today' },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:00:00Z',
        },
        {
          id: 'suggestion-2',
          kind: 'task_project',
          status: 'pending',
          title: 'Sort into Backlog',
          description: 'Default place until clearer',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-2'],
          payload: { task_id: 'task-2', project: 'Backlog', confidence: 'medium', reason: 'Default place until clearer' },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:01:00Z',
        },
      ],
    } satisfies AssistantSuggestionsResponse);

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));

    expect(screen.getByText('Review Hub')).toBeInTheDocument();
    expect(screen.getByText('Lumi prepared 2 decisions')).toBeInTheDocument();
    expect(screen.getByText('Estimate Compare Mira design')).toBeInTheDocument();
    expect(screen.getByText('Sort into Backlog')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review estimates/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Review project sorting/i })).toBeInTheDocument();
    expect(screen.queryByText('Need project')).not.toBeInTheDocument();
    expect(screen.queryByText('Разбор')).not.toBeInTheDocument();
  });

  it('opens Plan dates as grouped decision cards and accepts a prepared due date', async () => {
    const task = makeTask({
      id: 'task-plan',
      title: 'Prepare UI progress notes',
      project: 'Lumi',
      project_id: 'project-lumi',
      estimated_minutes: 25,
    });
    const dueSuggestion = {
      id: 'suggestion-due',
      kind: 'task_due_date',
      status: 'pending',
      title: 'Plan date',
      description: 'Small task that fits this week',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-plan'],
      payload: {
        task_id: 'task-plan',
        due_at: '2026-06-26T15:00:00Z',
        bucket: 'Likely this week',
        reason: 'Small task that fits this week',
      },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:00:00Z',
    } satisfies AssistantSuggestion;
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [task] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions')
      .mockResolvedValueOnce({ items: [dueSuggestion] } satisfies AssistantSuggestionsResponse)
      .mockResolvedValue({ items: [] } satisfies AssistantSuggestionsResponse);
    const acceptSpy = vi.spyOn(api, 'acceptAssistantSuggestion').mockResolvedValue({
      suggestion: { ...dueSuggestion, status: 'accepted', decided_at: '2026-06-21T08:01:00Z' },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review plan dates/i }));

    expect(screen.getByRole('dialog', { name: 'Plan dates' })).toBeInTheDocument();
    expect(screen.getByText('Likely this week')).toBeInTheDocument();
    expect(screen.getByText('Prepare UI progress notes')).toBeInTheDocument();
    expect(screen.getByText('Small task that fits this week')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Accept date for Prepare UI progress notes/i }));
    await waitFor(() => {
      expect(acceptSpy).toHaveBeenCalledWith('suggestion-due');
      expect(screen.queryByText('Prepare UI progress notes')).not.toBeInTheDocument();
    });
  });

  it('marks a Plan dates card as no deadline with a scoped review skip', async () => {
    const task = makeTask({
      id: 'task-backlog-date',
      title: 'Think about subscription UX',
      project: 'Backlog',
      project_id: 'project-backlog',
    });
    const dueSuggestion = {
      id: 'suggestion-no-date',
      kind: 'task_due_date',
      status: 'pending',
      title: 'No deadline',
      description: 'Backlog items can stay open without a deadline.',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-backlog-date'],
      payload: {
        task_id: 'task-backlog-date',
        no_deadline: true,
        bucket: 'Someday / Backlog',
        reason: 'Backlog items can stay open without a deadline.',
      },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:00:00Z',
    } satisfies AssistantSuggestion;
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [task] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [dueSuggestion] });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...task, review_skips: { due_date: true } },
    });
    vi.spyOn(api, 'dismissAssistantSuggestion').mockResolvedValue({
      suggestion: { ...dueSuggestion, status: 'dismissed', decided_at: '2026-06-21T08:01:00Z' },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review plan dates/i }));
    await user.click(screen.getByRole('button', { name: /No deadline for Think about subscription UX/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('task-backlog-date', { review_skips: { due_date: true } });
    });
  });

  it('opens Sort into projects as suggestion cards and can keep a task unassigned', async () => {
    const task = makeTask({ id: 'task-sort', title: 'Update office files', estimated_minutes: 20 });
    const projectSuggestion = {
      id: 'suggestion-project',
      kind: 'task_project',
      status: 'pending',
      title: 'Sort into Lumi',
      description: 'Looks related to Lumi docs',
      start_at: null,
      end_at: null,
      affected_task_ids: ['task-sort'],
      payload: {
        task_id: 'task-sort',
        project: 'Lumi',
        confidence: 'High',
        reason: 'Looks related to Lumi docs',
      },
      expires_at: null,
      decided_at: null,
      created_at: '2026-06-21T08:00:00Z',
    } satisfies AssistantSuggestion;
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [task] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [makeProject({ id: 'project-lumi', name: 'Lumi' })] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [projectSuggestion] } satisfies AssistantSuggestionsResponse);
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...task, review_skips: { project: true } },
    });
    const dismissSpy = vi.spyOn(api, 'dismissAssistantSuggestion').mockResolvedValue({
      suggestion: { ...projectSuggestion, status: 'dismissed', decided_at: '2026-06-21T08:01:00Z' },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Review' }));
    await user.click(screen.getByRole('button', { name: /Review project sorting/i }));

    const dialog = screen.getByRole('dialog', { name: 'Sort into projects' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText('Suggested project')).toBeInTheDocument();
    expect(within(dialog).getByText('Lumi')).toBeInTheDocument();
    expect(within(dialog).getByText('Looks related to Lumi docs')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Keep Update office files unassigned/i }));
    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('task-sort', { review_skips: { project: true } });
      expect(dismissSpy).toHaveBeenCalledWith('suggestion-project');
    });
  });

  it('shows Backlog as a system project with a cleanup panel', async () => {
    const backlogProject = makeProject({
      id: 'project-backlog',
      name: 'Backlog',
      system_key: 'backlog',
      is_system: true,
      active_task_count: 2,
      health_status: 'light',
      health_reason: 'Open ideas',
      next_task: makeTask({ id: 'task-backlog-1', title: 'Think about subscription UX', project: 'Backlog', project_id: 'project-backlog' }),
    });
    vi.spyOn(api, 'listTasks').mockImplementation(async (_filter, _limit, projectId) => ({
      items: projectId === 'project-backlog'
        ? [
            makeTask({ id: 'task-backlog-1', title: 'Think about subscription UX', project: 'Backlog', project_id: 'project-backlog' }),
            makeTask({ id: 'task-backlog-2', title: 'Review onboarding ideas', project: 'Backlog', project_id: 'project-backlog', estimated_minutes: 30 }),
          ]
        : [],
    }));
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [backlogProject] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({
      items: [
        {
          id: 'suggestion-backlog-estimate',
          kind: 'task_estimate',
          status: 'pending',
          title: 'Estimate Think about subscription UX',
          description: 'Small enough for one focus block.',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-backlog-1'],
          payload: {
            task_id: 'task-backlog-1',
            estimated_minutes: 30,
            reason: 'Small enough for one focus block.',
          },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:00:00Z',
        },
      ],
    } satisfies AssistantSuggestionsResponse);

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Projects' }));
    await user.click(screen.getByRole('button', { name: /Open project Backlog/i }));

    expect(await screen.findByText('Backlog cleanup')).toBeInTheDocument();
    expect(screen.getByText('1 decision ready')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review cleanup' })).toBeInTheDocument();
  });

  it('groups Done tasks and can undo completion inline', async () => {
    const doneTask = makeTask({
      id: 'task-done',
      title: 'Buy capsules',
      status: 'done',
      project: 'Shopping',
      estimated_minutes: 5,
      completed_at: new Date().toISOString(),
    });
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [doneTask] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...doneTask, status: 'active', completed_at: null },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Done' }));

    expect(await screen.findByText('Work done')).toBeInTheDocument();
    expect(screen.getAllByText('Today').length).toBeGreaterThan(1);
    await user.click(screen.getByRole('button', { name: /Undo completion for Buy capsules/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('task-done', { status: 'active' });
    });
  });

  it('can undo completion from the Done task detail sheet', async () => {
    const doneTask = makeTask({
      id: 'task-done-detail',
      title: 'Send recap',
      status: 'done',
      completed_at: new Date().toISOString(),
    });
    vi.spyOn(api, 'listTasks').mockResolvedValue({ items: [doneTask] } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({ items: [] });
    const patchSpy = vi.spyOn(api, 'patchTask').mockResolvedValue({
      task: { ...doneTask, status: 'active', completed_at: null },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Done' }));
    await user.click(await screen.findByRole('button', { name: /Open task details/i }));
    await user.click(screen.getByRole('button', { name: 'Undo completion' }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('task-done-detail', { status: 'active' });
    });
  });

  it('opens an estimate bottom sheet from the task-card nudge', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi' })],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({
      items: [
        {
          id: 'suggestion-1',
          kind: 'task_estimate',
          status: 'pending',
          title: 'Estimate Compare Mira design',
          description: 'Fits a focus block today',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-1'],
          payload: { task_id: 'task-1', estimated_minutes: 45, reason: 'Fits a focus block today' },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:00:00Z',
        },
      ],
    } satisfies AssistantSuggestionsResponse);

    const user = userEvent.setup();
    renderTasksPage('en');

    expect(await screen.findByText('Estimate: 45 min')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Edit estimate for Compare Mira design' }));

    expect(screen.getByRole('dialog', { name: 'Estimate task' })).toBeInTheDocument();
    expect(screen.getAllByText('Fits a focus block today').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '45m' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('accepts the suggested estimate from the task-card nudge', async () => {
    vi.spyOn(api, 'listTasks').mockResolvedValue({
      items: [makeTask({ id: 'task-1', title: 'Compare Mira design', project: 'Lumi' })],
    } satisfies TasksResponse);
    vi.spyOn(api, 'listProjects').mockResolvedValue({ items: [] });
    vi.spyOn(api, 'listAssistantSuggestions').mockResolvedValue({
      items: [
        {
          id: 'suggestion-1',
          kind: 'task_estimate',
          status: 'pending',
          title: 'Estimate Compare Mira design',
          description: 'Fits a focus block today',
          start_at: null,
          end_at: null,
          affected_task_ids: ['task-1'],
          payload: { task_id: 'task-1', estimated_minutes: 45 },
          expires_at: null,
          decided_at: null,
          created_at: '2026-06-21T08:00:00Z',
        },
      ],
    } satisfies AssistantSuggestionsResponse);
    const acceptSpy = vi.spyOn(api, 'acceptAssistantSuggestion').mockResolvedValue({
      suggestion: {
        id: 'suggestion-1',
        kind: 'task_estimate',
        status: 'accepted',
        title: 'Estimate Compare Mira design',
        description: 'Fits a focus block today',
        start_at: null,
        end_at: null,
        affected_task_ids: ['task-1'],
        payload: { task_id: 'task-1', estimated_minutes: 45 },
        expires_at: null,
        decided_at: '2026-06-21T08:01:00Z',
        created_at: '2026-06-21T08:00:00Z',
      },
    });

    const user = userEvent.setup();
    renderTasksPage('en');
    await user.click(await screen.findByRole('button', { name: 'Accept estimate for Compare Mira design' }));

    await waitFor(() => {
      expect(acceptSpy).toHaveBeenCalledWith('suggestion-1');
    });
  });
});
