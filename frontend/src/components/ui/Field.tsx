import type { ReactNode, ChangeEvent } from 'react';
import { ChevronDown } from 'lucide-react';

/** Consistent form controls for sheets and settings. */

const CONTROL =
  'w-full rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]';

export function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="mb-1.5 block text-[12.5px] font-medium text-hint">{children}</span>;
}

interface InputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  autoFocus?: boolean;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
}

export function Input({ value, onChange, placeholder, type = 'text', autoFocus, onKeyDown }: InputProps) {
  return (
    <input
      type={type}
      value={value}
      autoFocus={autoFocus}
      onKeyDown={onKeyDown}
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`${CONTROL} h-11`}
    />
  );
}

interface TextareaProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  mono?: boolean;
}

export function Textarea({ value, onChange, placeholder, rows = 4, mono = false }: TextareaProps) {
  return (
    <textarea
      value={value}
      rows={rows}
      onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`${CONTROL} resize-y py-2.5 ${mono ? 'font-mono text-[13px]' : ''}`}
    />
  );
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  ariaLabel?: string;
}

export function Select({ value, onChange, options, ariaLabel }: SelectProps) {
  return (
    <span className="relative block w-full">
      <select
        value={value}
        aria-label={ariaLabel}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
        className={`${CONTROL} h-11 appearance-none pr-9`}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden
        size={16}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-hint"
      />
    </span>
  );
}
