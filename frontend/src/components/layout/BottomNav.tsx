import { useLocation, useNavigate } from 'react-router-dom';
import { CalendarDays, LayoutGrid, ListChecks, Sunrise, Timer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { haptic } from '../../telegram/webapp';
import { useAppLocale } from '../../lib/useAppLocale';

interface NavItem {
  to: string;
  label: { en: string; ru: string };
  icon: LucideIcon;
  /** Extra paths that keep this item active. */
  also?: string[];
}

const ITEMS: NavItem[] = [
  { to: '/', label: { en: 'Today', ru: 'Сегодня' }, icon: Sunrise },
  { to: '/tasks', label: { en: 'Tasks', ru: 'Задачи' }, icon: ListChecks },
  { to: '/focus', label: { en: 'Focus', ru: 'Фокус' }, icon: Timer },
  { to: '/calendar', label: { en: 'Calendar', ru: 'Календарь' }, icon: CalendarDays },
  { to: '/more', label: { en: 'More', ru: 'Ещё' }, icon: LayoutGrid, also: ['/inbox', '/news', '/automations', '/settings', '/runs'] },
];

/** Floating pill bottom navigation with safe-area padding. */
export function BottomNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const locale = useAppLocale();

  return (
    <nav
      aria-label={locale === 'en' ? 'Primary navigation' : 'Основная навигация'}
      className="fixed left-1/2 z-50 w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2"
      style={{ bottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}
    >
      <div
        className="flex items-center justify-between rounded-full border border-hairline bg-surface px-1.5 py-1.5 shadow-nav"
        style={{ backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' }}
      >
        {ITEMS.map((item) => {
          const active =
            item.to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.to) ||
                (item.also?.some((p) => location.pathname.startsWith(p)) ?? false);
          const Icon = item.icon;
          const label = item.label[locale];
          return (
            <button
              key={item.to}
              type="button"
              aria-label={label}
              aria-current={active ? 'page' : undefined}
              onClick={() => {
                if (!active) haptic('light');
                navigate(item.to);
              }}
              className="relative flex h-[52px] flex-1 flex-col items-center justify-center gap-0.5 rounded-full"
            >
              <Icon
                size={20}
                strokeWidth={active ? 2.1 : 1.8}
                className={active ? 'text-accent-text' : 'text-hint'}
              />
              <span className={`text-[10px] leading-none ${active ? 'font-medium text-accent-text' : 'text-hint'}`}>
                {label}
              </span>
              <span
                aria-hidden
                className={`absolute bottom-[3px] h-1 w-1 rounded-full transition-opacity ${
                  active ? 'bg-accent opacity-100 shadow-[0_0_6px_var(--accent)]' : 'opacity-0'
                }`}
              />
            </button>
          );
        })}
      </div>
    </nav>
  );
}
