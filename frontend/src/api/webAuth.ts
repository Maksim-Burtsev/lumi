import type { QueryClient } from '@tanstack/react-query';
import { clearUnauthorizedResponse } from './client';
import { clearRealtimeCursor } from './hooks';

const LOGOUT_PENDING_KEY = 'lumi:logout-pending';

export function clearWebIdentityState(queryClient: QueryClient): void {
  clearUnauthorizedResponse();
  queryClient.clear();
  clearRealtimeCursor();
}

export function hasPendingWebLogout(): boolean {
  try {
    return sessionStorage.getItem(LOGOUT_PENDING_KEY) === '1';
  } catch {
    return false;
  }
}

export function markPendingWebLogout(): void {
  try {
    sessionStorage.setItem(LOGOUT_PENDING_KEY, '1');
  } catch {
    /* The explicit /logout route still preserves recovery on reload. */
  }
}

export function clearPendingWebLogout(): void {
  try {
    sessionStorage.removeItem(LOGOUT_PENDING_KEY);
  } catch {
    /* Storage can be unavailable in embedded clients. */
  }
}
