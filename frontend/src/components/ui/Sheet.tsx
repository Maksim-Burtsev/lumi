import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { X } from 'lucide-react';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

/** Bottom sheet for forms and detail views. */
export function Sheet({ open, onClose, title, children }: SheetProps) {
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[80] flex items-end justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="absolute inset-0 bg-[rgba(20,19,16,0.4)]"
            aria-hidden
          />
          <motion.div
            initial={reduceMotion ? { opacity: 0 } : { y: '100%' }}
            animate={reduceMotion ? { opacity: 1 } : { y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { y: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            className="relative max-h-[88dvh] w-full max-w-[640px] overflow-y-auto rounded-t-[28px] border border-b-0 border-hairline bg-[var(--surface-strong)] shadow-card"
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)' }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
          >
            <div className="sticky top-0 z-10 bg-[var(--surface-strong)] px-5 pb-2 pt-3">
              <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-[var(--hairline)]" />
              <div className="flex items-center justify-between">
                <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть"
                  className="-mr-2 flex h-11 w-11 items-center justify-center rounded-full text-hint"
                >
                  <X size={20} />
                </button>
              </div>
            </div>
            <div className="px-5 pt-1">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
