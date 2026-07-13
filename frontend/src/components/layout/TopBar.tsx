import { Settings } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useHealth } from '../../api/hooks';
import { useAppLocale } from '../../lib/useAppLocale';

interface TopBarProps {
  title: string;
}

export function TopBar({ title }: TopBarProps) {
  const health = useHealth();
  const locale = useAppLocale();

  const dotColor = health.isPending
    ? 'bg-[var(--hint)]'
    : health.isError
      ? 'bg-danger'
      : 'bg-success shadow-[0_0_6px_rgba(78,155,107,0.7)]';

  const dotTitle = health.isPending
    ? locale === 'en' ? 'Checking connection...' : 'Проверяем соединение…'
    : health.isError
      ? locale === 'en' ? 'Server unavailable' : 'Сервер недоступен'
      : `Lumi · ${health.data?.env ?? ''} ${health.data?.version ?? ''}`.trim();
  const settingsLabel = locale === 'en' ? 'Settings' : 'Настройки';

  return (
    <header className="sticky top-0 z-40" style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      <div className="bg-[var(--bg)]">
        <div className="mx-auto flex h-14 w-full max-w-content items-center justify-between px-5">
          <h1 className="text-[17px] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
          <div className="flex items-center gap-1">
            <div className="flex items-center gap-1.5" title={dotTitle}>
              <span className="font-display text-[13px] font-normal tracking-[0.06em] text-ink">Lumi</span>
              <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} aria-hidden />
            </div>
            <NavLink
              to="/settings"
              aria-label={settingsLabel}
              className={({ isActive }) =>
                `flex h-11 w-11 items-center justify-center rounded-full outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent-border)] ${
                  isActive ? 'bg-[var(--accent-soft)] text-accent-text' : 'text-hint'
                }`
              }
            >
              <Settings size={19} strokeWidth={1.9} aria-hidden />
            </NavLink>
          </div>
        </div>
      </div>
      {/* soft fade below the bar instead of a hard border */}
      <div
        aria-hidden
        className="pointer-events-none h-4"
        style={{ background: 'linear-gradient(to bottom, var(--bg), transparent)' }}
      />
    </header>
  );
}
