import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}

/** Premium, warm empty state — never looks like an error. */
export function EmptyState({ icon: Icon, title, hint, action, className = '' }: EmptyStateProps) {
  return (
    <div className={`card flex flex-col items-center px-6 py-10 text-center ${className}`}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)]">
        <Icon size={22} className="text-accent-text" strokeWidth={1.8} />
      </div>
      <p className="mt-4 text-[15px] font-medium text-ink">{title}</p>
      {hint && <p className="mt-1.5 max-w-[300px] text-[13px] leading-relaxed text-hint">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
