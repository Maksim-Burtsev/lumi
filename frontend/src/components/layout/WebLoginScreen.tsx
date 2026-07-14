import { useEffect, useRef, useState } from 'react';
import { Check, Clock3, Loader2, ShieldCheck } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import { clearPendingWebLogout, clearWebIdentityState } from '../../api/webAuth';
import { beginStandaloneWebAuth } from '../../telegram/webapp';

type WebLoginState = 'signed-out' | 'redeeming' | 'success' | 'expired-or-used' | 'invalid';

const exchanges = new Map<string, Promise<{ authenticated: true }>>();

function exchangeOnce(nonce: string): Promise<{ authenticated: true }> {
  const existing = exchanges.get(nonce);
  if (existing) return existing;
  const exchange = api.exchangeWebLogin(nonce);
  exchanges.set(nonce, exchange);
  const forget = () => {
    if (exchanges.get(nonce) === exchange) exchanges.delete(nonce);
  };
  void exchange.then(forget, forget);
  return exchange;
}

function stripNonceFromHash(): void {
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${window.location.search}#/web-login`,
  );
}

function stateForError(error: unknown): WebLoginState {
  if (!(error instanceof ApiError)) return 'invalid';
  const message = `${error.error} ${error.detail ?? ''}`.toLowerCase();
  if (
    message.includes('invalid_or_expired_login')
    || message.includes('expired')
    || message.includes('used')
    || message.includes('replay')
    || message.includes('consumed')
  ) return 'expired-or-used';
  return 'invalid';
}

const CONTENT: Record<WebLoginState, { title: string; body: string }> = {
  'signed-out': {
    title: 'Sign in through Telegram',
    body: 'Send /web to Lumi in Telegram to get a fresh one-time sign-in link.',
  },
  redeeming: {
    title: 'Signing you in',
    body: 'This one-time link is being verified.',
  },
  success: {
    title: 'Signed in',
    body: 'Opening your Lumi workspace.',
  },
  'expired-or-used': {
    title: 'This link expired or was already used',
    body: 'Each link works once. Send /web to Lumi in Telegram to get a fresh one.',
  },
  invalid: {
    title: 'This link is not valid',
    body: 'Send /web to Lumi in Telegram and open the newest sign-in link.',
  },
};

export function WebLoginScreen() {
  beginStandaloneWebAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const nonceRef = useRef(new URLSearchParams(location.search).get('nonce'));
  const [state, setState] = useState<WebLoginState>(nonceRef.current ? 'redeeming' : 'signed-out');

  useEffect(() => {
    const nonce = nonceRef.current;
    if (!nonce) return undefined;

    stripNonceFromHash();
    clearWebIdentityState(queryClient);
    let active = true;
    let redirectTimer: number | undefined;
    void exchangeOnce(nonce).then(
      () => {
        clearWebIdentityState(queryClient);
        clearPendingWebLogout();
        if (!active) return;
        setState('success');
        redirectTimer = window.setTimeout(() => navigate('/', { replace: true }), 350);
      },
      (error: unknown) => {
        clearWebIdentityState(queryClient);
        if (active) setState(stateForError(error));
      },
    );

    return () => {
      active = false;
      if (redirectTimer !== undefined) window.clearTimeout(redirectTimer);
    };
  }, [navigate, queryClient]);

  const content = CONTENT[state];
  const StateIcon = state === 'redeeming' ? Loader2 : state === 'success' ? Check : state === 'expired-or-used' ? Clock3 : ShieldCheck;

  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-10">
      <div className="w-full max-w-[420px] text-center">
        <span className="font-display text-[28px] font-light tracking-[0.05em] text-ink">Lumi</span>
        <div className="card card-strong mt-7 px-6 py-7">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)] text-accent-text">
            <StateIcon size={21} className={state === 'redeeming' ? 'animate-spin' : ''} strokeWidth={1.9} aria-hidden />
          </div>
          <h1 className="mt-5 text-[18px] font-semibold text-ink">{content.title}</h1>
          <p className="mx-auto mt-2 max-w-[320px] text-[13.5px] leading-relaxed text-hint">{content.body}</p>
          <p className="mt-5 text-[12px] text-hint" role="status" aria-live="polite">
            {state === 'redeeming' ? 'Verifying secure link...' : state === 'success' ? 'Authentication complete.' : 'No password is stored in the browser.'}
          </p>
        </div>
      </div>
    </main>
  );
}
