import { useCallback, useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { X } from 'lucide-react';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  onClosed?: () => void;
  title?: string;
  headerStart?: ReactNode;
  headerActions?: ReactNode;
  height?: 'content' | 'stable';
  children: ReactNode;
}

interface BodyLockState {
  count: number;
  scrollY: number;
  previous: {
    left: string;
    overflow: string;
    position: string;
    right: string;
    top: string;
    width: string;
  };
}

let bodyLockState: BodyLockState | null = null;

/** Bottom sheet for forms and detail views. */
export function Sheet({ open, onClose, onClosed, title, headerStart, headerActions, height = 'content', children }: SheetProps) {
  const reduceMotion = useReducedMotion();
  const lockedRef = useRef(false);
  const sheetTransition = reduceMotion
    ? { duration: 0.12 }
    : { duration: 0.22, ease: 'easeOut', type: 'tween' as const };

  const lockBody = useCallback(() => {
    if (lockedRef.current) return;
    if (bodyLockState) {
      bodyLockState.count += 1;
      lockedRef.current = true;
      return;
    }

    bodyLockState = {
      count: 1,
      scrollY: window.scrollY,
      previous: {
        left: document.body.style.left,
        overflow: document.body.style.overflow,
        position: document.body.style.position,
        right: document.body.style.right,
        top: document.body.style.top,
        width: document.body.style.width,
      },
    };

    document.body.style.left = '0';
    document.body.style.overflow = 'hidden';
    document.body.style.position = 'fixed';
    document.body.style.right = '0';
    document.body.style.top = `-${bodyLockState.scrollY}px`;
    document.body.style.width = '100%';
    lockedRef.current = true;
  }, []);

  const unlockBody = useCallback(() => {
    if (!lockedRef.current) return;
    lockedRef.current = false;
    const lock = bodyLockState;
    if (!lock) return;
    lock.count -= 1;
    if (lock.count > 0) return;

    bodyLockState = null;
    document.body.style.left = lock.previous.left;
    document.body.style.overflow = lock.previous.overflow;
    document.body.style.position = lock.previous.position;
    document.body.style.right = lock.previous.right;
    document.body.style.top = lock.previous.top;
    document.body.style.width = lock.previous.width;
    window.scrollTo(0, lock.scrollY);
  }, []);

  useEffect(() => {
    if (open) lockBody();
    if (!open && lockedRef.current) {
      const timeout = window.setTimeout(unlockBody, 260);
      return () => window.clearTimeout(timeout);
    }
    return undefined;
  }, [lockBody, open, unlockBody]);

  useEffect(() => () => unlockBody(), [unlockBody]);

  const handleExitComplete = () => {
    if (open) return;
    unlockBody();
    onClosed?.();
  };
  const heightClass = height === 'stable' ? 'h-[88dvh] max-h-[88dvh]' : 'max-h-[88dvh]';

  return createPortal(
    <AnimatePresence onExitComplete={handleExitComplete}>
      {open && (
        <motion.div
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0.999 }}
          transition={sheetTransition}
          className="fixed inset-0 z-[80] flex items-end justify-center"
        >
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
            transition={sheetTransition}
            className={`relative ${heightClass} w-full max-w-[640px] overflow-y-auto rounded-t-[28px] border border-b-0 border-hairline bg-[var(--surface-strong)] shadow-card`}
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)' }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
          >
            <div className="sticky top-0 z-10 bg-[var(--surface-strong)] px-5 pb-2 pt-3">
              <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-[var(--hairline)]" />
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  {headerStart}
                  <h2 className="truncate text-[17px] font-semibold text-ink">{title}</h2>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {headerActions}
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
            </div>
            <div className="px-5 pt-1">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
