import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { X } from 'lucide-react';
import { useAppLocale } from '../../lib/useAppLocale';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  onClosed?: () => void;
  title?: string;
  closeLabel?: string;
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

interface SheetLayer {
  id: number;
  root: HTMLElement;
  setTop: (top: boolean) => void;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

let nextSheetId = 0;
let sheetLayers: SheetLayer[] = [];

function syncSheetLayers(): void {
  const topId = sheetLayers[sheetLayers.length - 1]?.id;
  for (const layer of sheetLayers) {
    const top = layer.id === topId;
    layer.root.inert = !top;
    if (top) {
      layer.root.removeAttribute('aria-hidden');
      layer.root.removeAttribute('inert');
    } else {
      layer.root.setAttribute('aria-hidden', 'true');
      layer.root.setAttribute('inert', '');
    }
    layer.setTop(top);
  }
}

function registerSheetLayer(layer: SheetLayer): void {
  sheetLayers = [...sheetLayers.filter((item) => item.id !== layer.id), layer];
  syncSheetLayers();
}

function unregisterSheetLayer(id: number): void {
  const next = sheetLayers.filter((item) => item.id !== id);
  if (next.length === sheetLayers.length) return;
  sheetLayers = next;
  syncSheetLayers();
}

function updateSheetLayerRoot(id: number, root: HTMLElement): void {
  const layer = sheetLayers.find((item) => item.id === id);
  if (!layer || layer.root === root) return;
  layer.root = root;
  syncSheetLayers();
}

function isTopSheet(id: number): boolean {
  return sheetLayers[sheetLayers.length - 1]?.id === id;
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter((element) => {
    return !element.hidden && element.getAttribute('aria-hidden') !== 'true';
  });
}

/** Bottom sheet for forms and detail views. */
export function Sheet({
  open,
  onClose,
  onClosed,
  title,
  closeLabel,
  headerStart,
  headerActions,
  height = 'content',
  children,
}: SheetProps) {
  const reduceMotion = useReducedMotion();
  const locale = useAppLocale();
  const layerIdRef = useRef(0);
  if (layerIdRef.current === 0) layerIdRef.current = ++nextSheetId;
  const layerRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const previousOpenRef = useRef(false);
  const registeredRef = useRef(false);
  const lockedRef = useRef(false);
  const [top, setTop] = useState(false);
  if (open && !previousOpenRef.current) {
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  previousOpenRef.current = open;
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

  useEffect(() => {
    if (!open || registeredRef.current || !layerRef.current) return;
    registerSheetLayer({ id: layerIdRef.current, root: layerRef.current, setTop });
    registeredRef.current = true;

  }, [open]);

  useLayoutEffect(() => {
    if (open && registeredRef.current && layerRef.current) {
      updateSheetLayerRoot(layerIdRef.current, layerRef.current);
    }
    if (layerRef.current) {
      layerRef.current.inert = !top;
      if (top) layerRef.current.removeAttribute('inert');
      else layerRef.current.setAttribute('inert', '');
    }
    if (!open || !top) return;
    const dialog = dialogRef.current;
    if (dialog && !dialog.contains(document.activeElement)) {
      (focusableElements(dialog)[0] ?? dialog).focus();
    }
  });

  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTopSheet(layerIdRef.current)) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = focusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === dialog || document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === dialog || document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };

    const keepFocusInside = (event: FocusEvent) => {
      if (!isTopSheet(layerIdRef.current)) return;
      const dialog = dialogRef.current;
      if (!dialog || dialog.contains(event.target as Node)) return;
      (focusableElements(dialog)[0] ?? dialog).focus();
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('focusin', keepFocusInside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('focusin', keepFocusInside);
    };
  }, [onClose, open]);

  useEffect(() => () => {
    if (!registeredRef.current) return;
    unregisterSheetLayer(layerIdRef.current);
    registeredRef.current = false;
  }, []);

  const restoreFocus = () => {
    const target = returnFocusRef.current;
    if (!target) return;
    window.setTimeout(() => {
      const currentTop = sheetLayers[sheetLayers.length - 1]?.root;
      let focusTarget = target;
      if (!focusTarget.isConnected && currentTop) {
        focusTarget = focusableElements(currentTop).find((candidate) => {
          return candidate.tagName === target.tagName
            && candidate.getAttribute('aria-label') === target.getAttribute('aria-label')
            && candidate.textContent === target.textContent;
        }) ?? target;
      }
      if (!focusTarget.isConnected) return;
      if (currentTop && !currentTop.contains(focusTarget)) return;
      if (!currentTop && focusTarget.closest('[inert]')) return;
      focusTarget.focus();
    }, 0);
  };

  const handleExitComplete = () => {
    if (open) return;
    if (registeredRef.current) {
      unregisterSheetLayer(layerIdRef.current);
      registeredRef.current = false;
    }
    unlockBody();
    restoreFocus();
    onClosed?.();
  };
  const heightClass = height === 'stable' ? 'h-[88dvh] max-h-[88dvh]' : 'max-h-[88dvh]';

  return createPortal(
    <AnimatePresence onExitComplete={handleExitComplete}>
      {open && (
        <motion.div
          ref={layerRef}
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0.999 }}
          transition={sheetTransition}
          className="fixed inset-0 z-[80] flex items-end justify-center"
          aria-hidden={top ? undefined : true}
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
            ref={dialogRef}
            initial={reduceMotion ? { opacity: 0 } : { y: '100%' }}
            animate={reduceMotion ? { opacity: 1 } : { y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { y: '100%' }}
            transition={sheetTransition}
            className={`relative ${heightClass} w-full max-w-[640px] overflow-y-auto rounded-t-[28px] border border-b-0 border-hairline bg-[var(--surface-strong)] shadow-card`}
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 20px)' }}
            role="dialog"
            aria-modal={top ? true : undefined}
            aria-label={title}
            tabIndex={-1}
            autoFocus
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
                    aria-label={closeLabel ?? (locale === 'en' ? 'Close' : 'Закрыть')}
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
    `sheet-${layerIdRef.current}`,
  );
}
