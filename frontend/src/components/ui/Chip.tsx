import { haptic } from '../../telegram/webapp';

interface ChipProps {
  label: string;
  active?: boolean;
  onClick?: () => void;
  count?: number;
}

/** Filter chip; visual 36px, tap area extended to ≥44px via ::after. */
export function Chip({ label, active = false, onClick, count }: ChipProps) {
  return (
    <button
      type="button"
      onClick={() => {
        haptic('light');
        onClick?.();
      }}
      className={`relative inline-flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-[13px] font-medium transition-colors after:absolute after:-inset-1.5 after:content-[''] ${
        active
          ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-accent-text'
          : 'border-hairline bg-surface text-hint'
      }`}
    >
      {label}
      {count !== undefined && (
        <span className={`tnum text-[12px] ${active ? 'text-accent-text' : 'text-hint'}`}>{count}</span>
      )}
    </button>
  );
}
