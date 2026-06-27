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

  return (
    <header className="sticky top-0 z-40" style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      <div className="bg-[var(--bg)]">
        <div className="mx-auto flex h-14 w-full max-w-content items-center justify-between px-5">
          <h1 className="text-[17px] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
          <div className="flex items-center gap-1.5" title={dotTitle}>
            <span className="font-display text-[13px] font-normal tracking-[0.06em] text-ink">Lumi</span>
            <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} aria-hidden />
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
