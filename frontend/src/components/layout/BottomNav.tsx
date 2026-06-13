import { useLocation, useNavigate } from 'react-router-dom';
import { CalendarDays, LayoutGrid, ListChecks, Mail, Sunrise } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { haptic } from '../../telegram/webapp';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Extra paths that keep this item active. */
  also?: string[];
}

const ITEMS: NavItem[] = [
  { to: '/', label: 'Сегодня', icon: Sunrise },
  { to: '/tasks', label: 'Задачи', icon: ListChecks },
  { to: '/calendar', label: 'Календарь', icon: CalendarDays },
  { to: '/inbox', label: 'Почта', icon: Mail },
  { to: '/more', label: 'Ещё', icon: LayoutGrid, also: ['/news', '/automations', '/settings', '/runs'] },
];

/** Floating pill bottom navigation with safe-area padding. */
export function BottomNav() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav
      aria-label="Основная навигация"
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
          return (
            <button
              key={item.to}
              type="button"
              aria-label={item.label}
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
                {item.label}
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
