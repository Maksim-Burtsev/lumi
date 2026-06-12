import type { ReactNode } from 'react';

interface SectionHeaderProps {
  title: string;
  action?: ReactNode;
  className?: string;
}

export function SectionHeader({ title, action, className = '' }: SectionHeaderProps) {
  return (
    <div className={`mb-3 mt-7 flex items-baseline justify-between px-1 ${className}`}>
      <h2 className="text-[15.5px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
      {action}
    </div>
  );
}
