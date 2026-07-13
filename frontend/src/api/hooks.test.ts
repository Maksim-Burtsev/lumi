import { describe, expect, it } from 'vitest';

import { normalizeTaskListQuery, qk } from './hooks';

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
});
