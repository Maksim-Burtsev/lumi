import { useEffect, useState } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { clearUnauthorizedResponse, hasUnauthorizedResponse, UNAUTHORIZED_EVENT } from './api/client';
import { useRealtimeInvalidation } from './api/hooks';
import { AppShell } from './components/layout/AppShell';
import { UnauthorizedScreen } from './components/layout/UnauthorizedScreen';
import { TimezoneMismatchPrompt } from './components/settings/TimezoneMismatchPrompt';
import { ToastProvider } from './components/ui/Toast';
import TodayPage from './routes/TodayPage';
import TasksPage from './routes/TasksPage';
import CalendarPage from './routes/CalendarPage';
import InboxPage from './routes/InboxPage';
import NewsPage from './routes/NewsPage';
import AutomationsPage from './routes/AutomationsPage';
import SettingsPage from './routes/SettingsPage';
import AgentRunsPage from './routes/AgentRunsPage';
import MorePage from './routes/MorePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function AppRoutes() {
  useRealtimeInvalidation();
  const [unauthorized, setUnauthorized] = useState(hasUnauthorizedResponse);
  const client = useQueryClient();

  useEffect(() => {
    const handler = () => setUnauthorized(true);
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, []);

  if (unauthorized) {
    return (
      <UnauthorizedScreen
        onRetry={() => {
          clearUnauthorizedResponse();
          setUnauthorized(false);
          void client.resetQueries();
        }}
      />
    );
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TodayPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/automations" element={<AutomationsPage />} />
        <Route path="/memory" element={<Navigate to="/more" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/runs" element={<AgentRunsPage />} />
        <Route path="/more" element={<MorePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <TimezoneMismatchPrompt />
    </AppShell>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <HashRouter>
          <AppRoutes />
        </HashRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
