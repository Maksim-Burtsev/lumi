import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Loader2, ShieldAlert } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { api } from '../../api/client';
import {
  clearPendingWebLogout,
  clearWebIdentityState,
  markPendingWebLogout,
} from '../../api/webAuth';
import { Button } from '../ui/Button';
import { WebLoginScreen } from './WebLoginScreen';

type LogoutState = 'pending' | 'failed' | 'complete';

export function LogoutScreen() {
  const queryClient = useQueryClient();
  const location = useLocation();
  const autoStarted = useRef(false);
  const [state, setState] = useState<LogoutState>('pending');

  const logout = useCallback(async () => {
    markPendingWebLogout();
    clearWebIdentityState(queryClient);
    setState('pending');
    try {
      await api.logoutWebSession();
      clearPendingWebLogout();
      setState('complete');
    } catch {
      setState('failed');
    }
  }, [queryClient]);

  useEffect(() => {
    if (autoStarted.current) return;
    autoStarted.current = true;
    void logout();
  }, [logout]);

  if (state === 'complete' && location.pathname === '/web-login') {
    return <WebLoginScreen />;
  }

  const complete = state === 'complete';
  const failed = state === 'failed';
  const Icon = complete ? Check : failed ? ShieldAlert : Loader2;
  const title = complete
    ? 'Signed out'
    : failed
      ? 'Logout is not confirmed'
      : 'Signing you out';
  const body = complete
    ? 'Send /web to Lumi in Telegram whenever you want a new one-time sign-in link.'
    : failed
      ? 'Lumi could not confirm that the server session was revoked. Keep this tab open and retry.'
      : 'Revoking this browser session and clearing private data from the screen.';

  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-10">
      <div className="w-full max-w-[420px] text-center">
        <span className="font-display text-[28px] font-light tracking-[0.05em] text-ink">Lumi</span>
        <div className="card card-strong mt-7 px-6 py-7">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)] text-accent-text">
            <Icon size={21} className={state === 'pending' ? 'animate-spin' : ''} strokeWidth={1.9} aria-hidden />
          </div>
          <h1 className="mt-5 text-[18px] font-semibold text-ink">{title}</h1>
          <p className="mx-auto mt-2 max-w-[330px] text-[13.5px] leading-relaxed text-hint">{body}</p>
          {failed && (
            <Button variant="secondary" className="mt-6" onClick={() => void logout()}>
              Retry logout
            </Button>
          )}
        </div>
      </div>
    </main>
  );
}
