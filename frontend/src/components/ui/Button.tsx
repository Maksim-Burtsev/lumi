import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'md' | 'sm';

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
  /** Shows a small spinner and disables the button. */
  busy?: boolean;
  icon?: ReactNode;
  type?: 'button' | 'submit';
  className?: string;
  fullWidth?: boolean;
  'aria-label'?: string;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-[var(--accent-foreground)] shadow-[0_6px_18px_var(--accent-shadow)] font-medium',
  secondary: 'bg-[var(--secondary-bg)] text-[var(--secondary-text)] font-medium',
  ghost: 'bg-transparent border border-hairline text-ink font-medium',
  danger: 'bg-[var(--danger-soft)] text-danger font-medium',
};

const SIZES: Record<Size, string> = {
  md: 'h-11 px-5 text-[14.5px] gap-2',
  // visual 36px, effective tap area extended to ≥44px via ::after
  sm: 'h-9 px-3.5 text-[13px] gap-1.5 after:absolute after:-inset-1.5 after:content-[""]',
};

export function Button({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  busy = false,
  icon,
  type = 'button',
  className = '',
  fullWidth = false,
  'aria-label': ariaLabel,
}: ButtonProps) {
  const reduceMotion = useReducedMotion();
  const isDisabled = disabled || busy;

  return (
    <motion.button
      type={type}
      aria-label={ariaLabel}
      onClick={onClick}
      disabled={isDisabled}
      whileTap={reduceMotion || isDisabled ? undefined : { scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 420, damping: 26 }}
      className={`relative inline-flex select-none items-center justify-center whitespace-nowrap rounded-full transition-opacity disabled:opacity-55 ${VARIANTS[variant]} ${SIZES[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
    >
      {busy ? <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" /> : icon}
      {children}
    </motion.button>
  );
}
