import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

interface CardProps {
  children: ReactNode;
  className?: string;
  strong?: boolean;
  onClick?: () => void;
  'aria-label'?: string;
}

/** Glassy, restrained card. Pressable when onClick is provided (spring tap-scale). */
export function Card({ children, className = '', strong = false, onClick, 'aria-label': ariaLabel }: CardProps) {
  const reduceMotion = useReducedMotion();
  const classes = `card ${strong ? 'card-strong' : ''} ${className}`.trim();

  if (onClick) {
    return (
      <motion.button
        type="button"
        aria-label={ariaLabel}
        onClick={onClick}
        whileTap={reduceMotion ? undefined : { scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 420, damping: 26 }}
        className={`${classes} block w-full text-left`}
      >
        {children}
      </motion.button>
    );
  }

  return <div className={classes}>{children}</div>;
}
