import type { TimeFormat } from '../../api/types';
import { formatTime, resolveTimeFormat } from '../../lib/format';
import type { AppLocale } from '../../lib/i18n';
import { Select } from '../ui/Field';

interface TimeFormatControlProps {
  value: TimeFormat;
  onChange: (value: TimeFormat) => void;
  locale: AppLocale;
  timezone: string;
}

const COPY = {
  en: {
    example: 'Example',
    label: 'Time format',
    options: [
      { value: '12h', label: '12-hour' },
      { value: '24h', label: '24-hour' },
    ],
  },
  ru: {
    example: 'Пример',
    label: 'Формат времени',
    options: [
      { value: '12h', label: '12 часов' },
      { value: '24h', label: '24 часа' },
    ],
  },
} satisfies Record<AppLocale, {
  example: string;
  label: string;
  options: { value: TimeFormat; label: string }[];
}>;

const EXAMPLE_TIME = '2026-06-17T10:30:00Z';

export function TimeFormatControl({ value, onChange, locale, timezone }: TimeFormatControlProps) {
  const copy = COPY[locale];
  const resolvedValue = resolveTimeFormat({ locale, timeFormat: value, timezone });
  const example = formatTime(EXAMPLE_TIME, { locale, timeFormat: resolvedValue, timezone });

  return (
    <label className="flex min-h-[68px] items-center justify-between gap-3 px-4 py-3">
      <span className="min-w-0">
        <span className="block text-[13.5px] font-medium text-ink">{copy.label}</span>
        <span className="tnum mt-0.5 block text-[12.5px] text-hint">
          {copy.example}: {example}
        </span>
      </span>
      <span className="w-[132px] shrink-0">
        <Select
          value={resolvedValue}
          ariaLabel={copy.label}
          onChange={(next) => onChange(next as TimeFormat)}
          options={copy.options}
        />
      </span>
    </label>
  );
}
