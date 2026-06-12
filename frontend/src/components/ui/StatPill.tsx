type Tone = 'neutral' | 'accent' | 'danger' | 'success';

interface StatPillProps {
  label: string;
  tone?: Tone;
  onClick?: () => void;
  className?: string;
}

const TONES: Record<Tone, string> = {
  neutral: 'bg-[var(--secondary-bg)] text-hint',
  accent: 'bg-[var(--accent-soft)] text-accent-text',
  danger: 'bg-[var(--danger-soft)] text-danger',
  success: 'bg-[var(--success-soft)] text-success',
};

export function StatPill({ label, tone = 'neutral', onClick, className = '' }: StatPillProps) {
  const classes = `tnum inline-flex h-7 items-center gap-1 rounded-full px-3 text-[12px] font-medium ${TONES[tone]} ${className}`;
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={`${classes} relative after:absolute after:-inset-2 after:content-['']`}>
        {label}
      </button>
    );
  }
  return <span className={classes}>{label}</span>;
}
