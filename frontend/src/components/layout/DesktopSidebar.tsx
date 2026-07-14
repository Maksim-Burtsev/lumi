import { LogOut } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useHealth } from '../../api/hooks';
import { useAppLocale } from '../../lib/useAppLocale';
import { PRODUCT_NAV_ITEMS, SETTINGS_NAV_ITEM, isNavigationItemActive } from './navigation';

interface DesktopSidebarProps {
  loggingOut: boolean;
  onLogout: () => void;
  showLogout?: boolean;
}

export function DesktopSidebar({ loggingOut, onLogout, showLogout = true }: DesktopSidebarProps) {
  const locale = useAppLocale();
  const location = useLocation();
  const health = useHealth();
  const statusClass = health.isError ? 'bg-danger' : health.isPending ? 'bg-hint' : 'bg-success';
  const logoutLabel = locale === 'en' ? 'Log out' : 'Выйти';
  const settingsActive = isNavigationItemActive(location.pathname, SETTINGS_NAV_ITEM);
  const SettingsIcon = SETTINGS_NAV_ITEM.icon;

  return (
    <aside className="sticky top-0 hidden h-dvh min-h-0 py-5 lg:flex" aria-label={locale === 'en' ? 'Desktop navigation' : 'Навигация'}>
      <div className="flex min-h-0 w-48 flex-col border-r border-hairline pr-5">
        <div className="flex h-12 items-center gap-2 px-3">
          <span className="font-display text-[16px] font-normal tracking-[0.06em] text-ink">Lumi</span>
          <span className={`h-1.5 w-1.5 rounded-full ${statusClass}`} aria-hidden />
        </div>

        <nav className="mt-5 space-y-1" aria-label={locale === 'en' ? 'Primary navigation' : 'Основная навигация'}>
          {PRODUCT_NAV_ITEMS.map((item) => {
            const active = isNavigationItemActive(location.pathname, item);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={`flex h-11 items-center gap-3 rounded-2xl px-3 text-[14px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent-border)] ${
                  active ? 'bg-[var(--accent-soft)] text-accent-text' : 'text-hint hover:bg-[var(--secondary-bg)] hover:text-ink'
                }`}
              >
                <Icon size={19} strokeWidth={active ? 2.1 : 1.8} aria-hidden />
                {item.label[locale]}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto space-y-1 pt-5">
          <Link
            to={SETTINGS_NAV_ITEM.to}
            aria-current={settingsActive ? 'page' : undefined}
            className={`flex h-11 items-center gap-3 rounded-2xl px-3 text-[14px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent-border)] ${
              settingsActive
                ? 'bg-[var(--accent-soft)] text-accent-text'
                : 'text-hint hover:bg-[var(--secondary-bg)] hover:text-ink'
            }`}
          >
            <SettingsIcon size={19} strokeWidth={settingsActive ? 2.1 : 1.8} aria-hidden />
            {SETTINGS_NAV_ITEM.label[locale]}
          </Link>
          {showLogout && (
            <button
              type="button"
              disabled={loggingOut}
              onClick={onLogout}
              className="flex h-11 w-full items-center gap-3 rounded-2xl px-3 text-[14px] font-medium text-hint outline-none transition-colors hover:bg-[var(--secondary-bg)] hover:text-ink focus-visible:ring-2 focus-visible:ring-[var(--accent-border)] disabled:opacity-55"
            >
              <LogOut size={19} strokeWidth={1.8} aria-hidden />
              {loggingOut ? (locale === 'en' ? 'Logging out...' : 'Выходим...') : logoutLabel}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
