import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { TopBar } from './TopBar';
import { BottomNav } from './BottomNav';
import { useAppLocale } from '../../lib/useAppLocale';

const TITLES = {
  en: {
    '/': 'Today',
    '/tasks': 'Tasks',
    '/calendar': 'Calendar',
    '/inbox': 'Inbox',
    '/more': 'More',
    '/news': 'News',
    '/automations': 'Automations',
    '/settings': 'Settings',
    '/runs': 'Agent runs',
  },
  ru: {
    '/': 'Сегодня',
    '/tasks': 'Задачи',
    '/calendar': 'Календарь',
    '/inbox': 'Почта',
    '/more': 'Ещё',
    '/news': 'Новости',
    '/automations': 'Автоматизации',
    '/settings': 'Настройки',
    '/runs': 'Запуски агента',
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
      <TopBar title={title} />
      <main
        className="mx-auto w-full max-w-content px-4"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 88px)' }}
      >
        {children}
      </main>
      <BottomNav />
    </div>
  );
}
