import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ProductRoutes } from './App';

vi.mock('./routes/TodayPage', () => ({ default: () => <div>Today route</div> }));
vi.mock('./routes/TasksPage', () => ({ default: () => <div>Tasks route</div> }));
vi.mock('./routes/FocusPage', () => ({ default: () => <div>Sessions route</div> }));
vi.mock('./routes/CalendarPage', () => ({ default: () => <div>Calendar route</div> }));
vi.mock('./routes/SettingsPage', () => ({ default: () => <div>Settings route</div> }));

function CurrentPath() {
  return <output aria-label="Current path">{useLocation().pathname}</output>;
}

describe('ProductRoutes legacy redirects', () => {
  it.each([
    ['/inbox', '/tasks', 'Tasks route'],
    ['/email', '/tasks', 'Tasks route'],
    ['/news', '/', 'Today route'],
    ['/runs', '/', 'Today route'],
    ['/automations', '/settings', 'Settings route'],
    ['/memory', '/settings', 'Settings route'],
    ['/more', '/settings', 'Settings route'],
  ])('redirects %s to %s', async (source, target, targetContent) => {
    render(
      <MemoryRouter initialEntries={[source]}>
        <ProductRoutes />
        <CurrentPath />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText('Current path')).toHaveTextContent(target));
    expect(screen.getByText(targetContent)).toBeInTheDocument();
  });
});
