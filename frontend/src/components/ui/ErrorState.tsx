import { RotateCcw } from 'lucide-react';
import { Button } from './Button';
import { useAppLocale } from '../../lib/useAppLocale';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

/** Small inline error card with retry — calm, not alarming. */
export function ErrorState({ message, onRetry, className = '' }: ErrorStateProps) {
  const locale = useAppLocale();
  const fallback = locale === 'en' ? 'Could not load data.' : 'Не удалось загрузить данные.';
  const retry = locale === 'en' ? 'Retry' : 'Повторить';
  return (
    <div className={`card flex flex-col items-center gap-3 px-6 py-7 text-center ${className}`}>
      <p className="text-[14px] text-hint">{message ?? fallback}</p>
      {onRetry && (
        <Button variant="ghost" size="sm" icon={<RotateCcw size={14} />} onClick={onRetry}>
          {retry}
        </Button>
      )}
    </div>
  );
}
