import { useMemo, useState } from 'react';
import { Check, Search } from 'lucide-react';
import { useTimezones } from '../../api/hooks';
import { Button } from '../ui/Button';
import { FieldLabel, Input } from '../ui/Field';
import { Sheet } from '../ui/Sheet';
import {
  buildTimezoneOptions,
  getBrowserTimezones,
  getDeviceTimezone,
  timezoneOptionMatches,
} from '../../lib/timezones';

interface TimezonePickerProps {
  value: string;
  onChange: (timezone: string) => void;
  locale: 'en' | 'ru';
}

const COPY = {
  en: {
    change: 'Change time zone',
    detected: 'Detected',
    search: 'Search city or time zone',
    title: 'Time zone',
    noResults: 'Nothing found',
  },
  ru: {
    change: 'Изменить часовой пояс',
    detected: 'Определён',
    search: 'Поиск города или часового пояса',
    title: 'Часовой пояс',
    noResults: 'Ничего не найдено',
  },
};

export function TimezonePicker({ value, onChange, locale }: TimezonePickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const timezones = useTimezones();
  const deviceTimezone = getDeviceTimezone();
  const copy = COPY[locale];
  const options = useMemo(() => buildTimezoneOptions({
    apiTimezones: timezones.data?.items.map((item) => item.id),
    browserTimezones: getBrowserTimezones(),
    extraTimezones: [value, deviceTimezone],
  }), [deviceTimezone, timezones.data?.items, value]);
  const selected = options.find((option) => option.value === value);
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = (normalizedQuery
    ? options.filter((option) => timezoneOptionMatches(option, query))
    : options
  ).slice(0, 80);

  const handleSelect = (timezone: string) => {
    onChange(timezone);
    setOpen(false);
    setQuery('');
  };

  return (
    <>
      <button
        type="button"
        aria-label={copy.change}
        onClick={() => setOpen(true)}
        className="flex min-h-[44px] w-full items-center justify-between gap-3 rounded-xl border border-hairline bg-[var(--surface-strong)] px-3.5 py-2 text-left text-[15px] text-ink outline-none transition-shadow focus:border-[var(--accent-border)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
      >
        <span className="min-w-0">
          <span className="block truncate">{selected?.label ?? value}</span>
          {deviceTimezone && deviceTimezone !== value && (
            <span className="mt-0.5 block truncate text-[12px] text-hint">
              {copy.detected}: {deviceTimezone}
            </span>
          )}
        </span>
        <span className="shrink-0 text-[13px] font-medium text-accent-text">{copy.change}</span>
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title={copy.title}>
        <label className="block">
          <FieldLabel>
            <span className="inline-flex items-center gap-1.5">
              <Search size={13} />
              {copy.search}
            </span>
          </FieldLabel>
          <Input value={query} onChange={setQuery} placeholder={copy.search} autoFocus />
        </label>
        <div className="mt-3 flex flex-col gap-1.5">
          {filtered.length === 0 && <p className="px-1 py-3 text-[13px] text-hint">{copy.noResults}</p>}
          {filtered.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => handleSelect(option.value)}
              className={`flex min-h-[44px] items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-[13.5px] transition-colors ${
                option.value === value
                  ? 'bg-[var(--accent-soft)] text-ink'
                  : 'bg-transparent text-ink hover:bg-[var(--secondary-bg)]'
              }`}
            >
              <span className="min-w-0">
                <span className="block truncate">{option.label}</span>
              </span>
              {option.value === value && <Check size={16} className="shrink-0 text-accent-text" />}
            </button>
          ))}
        </div>
        {timezones.isError && (
          <p className="mt-3 text-[12px] text-hint">Using browser time zones.</p>
        )}
        <Button className="mt-4" fullWidth variant="secondary" onClick={() => setOpen(false)}>
          {locale === 'en' ? 'Close' : 'Закрыть'}
        </Button>
      </Sheet>
    </>
  );
}
