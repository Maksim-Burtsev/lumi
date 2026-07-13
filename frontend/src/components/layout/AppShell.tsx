import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { TopBar } from './TopBar';
import { BottomNav } from './BottomNav';
import { useAppLocale } from '../../lib/useAppLocale';
import { FocusTimerCoordinator } from '../focus/FocusTimerCoordinator';

const TITLES = {
  en: {
    '/': 'Today',
    '/tasks': 'Tasks',
    '/sessions': 'Sessions',
    '/focus': 'Sessions',
    '/calendar': 'Calendar',
    '/settings': 'Settings',
  },
  ru: {
    '/': 'Сегодня',
    '/tasks': 'Задачи',
    '/sessions': 'Сессии',
    '/focus': 'Сессии',
    '/calendar': 'Календарь',
    '/settings': 'Настройки',
  },
};

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const locale = useAppLocale();
  const title = TITLES[locale][location.pathname as keyof typeof TITLES.en] ?? 'Lumi';

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  }, [location.pathname]);

  return (
    <div className="min-h-dvh">
      <FocusTimerCoordinator />
      <TopBar title={title} />
      <main
        className="mx-auto w-full max-w-content px-4"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 88px + var(--timezone-prompt-reserve, 0px))' }}
      >
        {children}
      </main>
      <BottomNav />
    </div>
  );
}
