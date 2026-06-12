import { RotateCcw } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

/** Small inline error card with retry — calm, not alarming. */
export function ErrorState({ message = 'Не удалось загрузить данные.', onRetry, className = '' }: ErrorStateProps) {
  return (
    <div className={`card flex flex-col items-center gap-3 px-6 py-7 text-center ${className}`}>
      <p className="text-[14px] text-hint">{message}</p>
      {onRetry && (
        <Button variant="ghost" size="sm" icon={<RotateCcw size={14} />} onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
