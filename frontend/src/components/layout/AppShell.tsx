import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { TopBar } from './TopBar';
import { BottomNav } from './BottomNav';
import { useAppLocale } from '../../lib/useAppLocale';
import { FocusTimerCoordinator } from '../focus/FocusTimerCoordinator';
import { getInitData } from '../../telegram/webapp';
import { DesktopSidebar } from './DesktopSidebar';
import { pageTitle } from './navigation';

interface AppShellProps {
  children: ReactNode;
  onLogout: () => Promise<void>;
  showLogout?: boolean;
}

export function AppShell({ children, onLogout, showLogout = true }: AppShellProps) {
  const location = useLocation();
  const locale = useAppLocale();
  const title = pageTitle(location.pathname, locale);
  const standalone = getInitData().length === 0;
  const [loggingOut, setLoggingOut] = useState(false);

  const logout = () => {
    if (loggingOut) return;
    setLoggingOut(true);
    void onLogout().catch(() => undefined).finally(() => setLoggingOut(false));
  };

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  }, [location.pathname]);

  return (
    <div className="min-h-dvh">
      <FocusTimerCoordinator />
      <div className={standalone ? 'standalone-shell lg:mx-auto lg:grid lg:max-w-[1124px] lg:grid-cols-[192px_minmax(0,860px)] lg:gap-6 lg:px-6' : ''}>
        {standalone && (
          <DesktopSidebar loggingOut={loggingOut} onLogout={logout} showLogout={showLogout} />
        )}
        <div className="min-w-0">
          <TopBar
            title={title}
            standalone={standalone}
            loggingOut={loggingOut}
            onLogout={showLogout ? logout : undefined}
          />
          <main className="app-content mx-auto w-full max-w-content px-4">
            {children}
          </main>
          <BottomNav standalone={standalone} />
        </div>
      </div>
    </div>
  );
}
