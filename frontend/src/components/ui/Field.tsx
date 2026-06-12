import type { ReactNode, ChangeEvent } from 'react';

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
}

export function Select({ value, onChange, options }: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
      className={`${CONTROL} h-11 appearance-none bg-no-repeat pr-9`}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238A8478' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
        backgroundPosition: 'right 12px center',
      }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
