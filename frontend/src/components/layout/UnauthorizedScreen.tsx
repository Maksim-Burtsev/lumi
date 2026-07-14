import { Send } from 'lucide-react';
import { Button } from '../ui/Button';

interface UnauthorizedScreenProps {
  onRetry: () => void;
}

/** App-level signed-out screen for standalone web and invalid Mini App auth. */
export function UnauthorizedScreen({ onRetry }: UnauthorizedScreenProps) {
  const copy = {
    title: 'Sign in through Telegram',
    body: 'Send /web to Lumi in Telegram to get a short-lived one-time sign-in link.',
    devTitle: 'Development hint',
    devStart: 'Run the backend with',
    devTail: 'then requests without initData are authorized as',
    retry: 'Retry',
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <div className="relative">
        <span className="font-display text-[34px] font-light tracking-[0.04em] text-ink">Lumi</span>
        <span
          aria-hidden
          className="absolute -right-3 top-1.5 h-2 w-2 rounded-full bg-accent shadow-[0_0_10px_var(--accent)]"
        />
      </div>
      <div className="mt-8 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent-soft)]">
        <Send size={20} className="text-accent-text" strokeWidth={1.8} />
      </div>
      <p className="mt-5 text-[17px] font-medium text-ink">{copy.title}</p>
      <p className="mt-2 max-w-[300px] text-[13.5px] leading-relaxed text-hint">
        {copy.body}
      </p>
      {import.meta.env.DEV && (
        <div className="card mt-6 max-w-[340px] px-4 py-3 text-left">
          <p className="text-[12px] font-medium text-accent-text">{copy.devTitle}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-hint">
            {copy.devStart} <code className="font-mono text-ink">DEV_AUTH_ENABLED=true</code>. {copy.devTail}{' '}
            <code className="font-mono text-ink">DEV_AUTH_TELEGRAM_USER_ID</code>.
          </p>
        </div>
      )}
      <Button variant="secondary" className="mt-7" onClick={onRetry}>
        {copy.retry}
      </Button>
    </div>
  );
}
