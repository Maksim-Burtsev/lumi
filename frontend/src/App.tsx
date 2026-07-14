import { useEffect, useState } from 'react';
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { clearUnauthorizedResponse, hasUnauthorizedResponse, UNAUTHORIZED_EVENT } from './api/client';
import { useRealtimeInvalidation, useSettings } from './api/hooks';
import { AppShell } from './components/layout/AppShell';
import { LogoutScreen } from './components/layout/LogoutScreen';
import { UnauthorizedScreen } from './components/layout/UnauthorizedScreen';
import { WebLoginScreen } from './components/layout/WebLoginScreen';
import {
  clearWebIdentityState,
  hasPendingWebLogout,
  markPendingWebLogout,
} from './api/webAuth';
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

function AuthenticatedProduct({ onLogout }: { onLogout: () => Promise<void> }) {
  useRealtimeInvalidation();
  const settings = useSettings();

  useEffect(() => {
    if (!settings.data) return;
    setThemeMode(normalizeThemeMode(settings.data.user.settings.theme_mode));
  }, [settings.data]);

  return (
    <AppShell
      onLogout={onLogout}
      showLogout={settings.data?.flags.dev_auth === false}
    >
      <TimezoneMismatchPrompt />
      <ProductRoutes />
    </AppShell>
  );
}

function AuthenticatedRoutes() {
  const [unauthorized, setUnauthorized] = useState(hasUnauthorizedResponse);
  const client = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    const handler = () => {
      setUnauthorized(true);
      clearWebIdentityState(client);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [client]);

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
    <AuthenticatedProduct
      onLogout={async () => {
        markPendingWebLogout();
        clearWebIdentityState(client);
        navigate('/logout', { replace: true });
      }}
    />
  );
}

export function RouteGate() {
  const location = useLocation();
  if (location.pathname === '/logout' || hasPendingWebLogout()) return <LogoutScreen />;
  if (location.pathname === '/web-login') return <WebLoginScreen />;
  return <AuthenticatedRoutes />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <HashRouter>
          <RouteGate />
        </HashRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
