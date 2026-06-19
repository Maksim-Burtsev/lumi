import type { TimeFormat } from '../../api/types';
import { formatTime } from '../../lib/format';
import type { AppLocale } from '../../lib/i18n';

interface TimeFormatControlProps {
  value: TimeFormat;
  onChange: (value: TimeFormat) => void;
  locale: AppLocale;
  timezone: string;
}

const COPY = {
  en: {
    example: 'Example',
    options: [
      { value: 'auto', label: 'Automatic' },
      { value: '12h', label: '12-hour' },
      { value: '24h', label: '24-hour' },
    ],
  },
  ru: {
    example: 'Пример',
    options: [
      { value: 'auto', label: 'Авто' },
      { value: '12h', label: '12 часов' },
      { value: '24h', label: '24 часа' },
    ],
  },
} satisfies Record<AppLocale, {
  example: string;
  options: { value: TimeFormat; label: string }[];
}>;

const EXAMPLE_TIME = '2026-06-17T10:30:00Z';

export function TimeFormatControl({ value, onChange, locale, timezone }: TimeFormatControlProps) {
  const copy = COPY[locale];
  const example = formatTime(EXAMPLE_TIME, { locale, timeFormat: value, timezone });

  return (
    <div>
      <div
        className="grid min-h-[44px] grid-cols-3 gap-1 rounded-xl border border-hairline bg-[var(--surface-strong)] p-1"
        role="group"
      >
        {copy.options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={`min-h-[36px] rounded-lg px-2 text-[13.5px] font-medium transition-colors ${
                active
                  ? 'bg-[var(--secondary-bg)] text-ink shadow-[0_1px_3px_rgba(20,18,14,0.08)]'
                  : 'text-hint hover:bg-[var(--secondary-bg)]'
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      <p className="tnum mt-1.5 text-[12.5px] text-hint">
        {copy.example}: {example}
      </p>
    </div>
  );
}
