import { useEffect, useState } from 'react';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { clearUnauthorizedResponse, hasUnauthorizedResponse, UNAUTHORIZED_EVENT } from './api/client';
import { useRealtimeInvalidation, useSettings } from './api/hooks';
import { AppShell } from './components/layout/AppShell';
import { UnauthorizedScreen } from './components/layout/UnauthorizedScreen';
import { TimezoneMismatchPrompt } from './components/settings/TimezoneMismatchPrompt';
import { ToastProvider } from './components/ui/Toast';
import { normalizeThemeMode } from './lib/theme';
import { setThemeMode } from './telegram/webapp';
import TodayPage from './routes/TodayPage';
import TasksPage from './routes/TasksPage';
import FocusPage from './routes/FocusPage';
import CalendarPage from './routes/CalendarPage';
import SettingsPage from './routes/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function ProductRoutes() {
  return (
    <Routes>
      <Route path="/" element={<TodayPage />} />
      <Route path="/tasks" element={<TasksPage />} />
      <Route path="/sessions" element={<FocusPage />} />
      <Route path="/focus" element={<Navigate to="/sessions" replace />} />
      <Route path="/calendar" element={<CalendarPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/inbox" element={<Navigate to="/tasks" replace />} />
      <Route path="/email" element={<Navigate to="/tasks" replace />} />
      <Route path="/news" element={<Navigate to="/" replace />} />
      <Route path="/runs" element={<Navigate to="/" replace />} />
      <Route path="/automations" element={<Navigate to="/settings" replace />} />
      <Route path="/memory" element={<Navigate to="/settings" replace />} />
      <Route path="/more" element={<Navigate to="/settings" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function AppRoutes() {
  useRealtimeInvalidation();
  const settings = useSettings();
  const [unauthorized, setUnauthorized] = useState(hasUnauthorizedResponse);
  const client = useQueryClient();

  useEffect(() => {
    const handler = () => setUnauthorized(true);
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, []);

  useEffect(() => {
    if (!settings.data) return;
    setThemeMode(normalizeThemeMode(settings.data.user.settings.theme_mode));
  }, [settings.data]);

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
      <TimezoneMismatchPrompt />
      <ProductRoutes />
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
