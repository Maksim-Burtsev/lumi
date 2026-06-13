import '@testing-library/jest-dom/vitest';
import React from 'react';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

const motionProps = new Set([
  'animate',
  'exit',
  'initial',
  'layout',
  'transition',
  'variants',
  'whileTap',
]);

vi.mock('framer-motion', () => {
  const motion = new Proxy(
    {},
    {
      get: (_target, tag: string) =>
        React.forwardRef<HTMLElement, Record<string, unknown> & { children?: React.ReactNode }>(
          ({ children, ...props }, ref) => {
            const domProps = Object.fromEntries(
              Object.entries(props).filter(([key]) => !motionProps.has(key)),
            );
            return React.createElement(tag, { ...domProps, ref }, children as React.ReactNode);
          },
        ),
    },
  );

  function AnimatePresence({
    children,
    onExitComplete,
  }: {
    children: React.ReactNode;
    onExitComplete?: () => void;
  }) {
    const hadChildrenRef = React.useRef(false);

    React.useEffect(() => {
      const hasChildren = React.Children.toArray(children).length > 0;
      let timeoutId: number | undefined;
      if (!hasChildren && hadChildrenRef.current) {
        timeoutId = window.setTimeout(() => onExitComplete?.(), 75);
      }
      hadChildrenRef.current = hasChildren;
      return () => {
        if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      };
    }, [children, onExitComplete]);

    return React.createElement(React.Fragment, null, children);
  }

  return {
    AnimatePresence,
    motion,
    useReducedMotion: () => true,
  };
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

beforeEach(() => {
  window.scrollTo = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.body.removeAttribute('style');
  document.documentElement.removeAttribute('class');
  document.documentElement.removeAttribute('style');
  sessionStorage.clear();
});
