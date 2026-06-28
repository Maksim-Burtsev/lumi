import { useMemo, useState } from 'react';
import { Check, ChevronRight, MapPin, Search } from 'lucide-react';
import { useTimezones } from '../../api/hooks';
import { FieldLabel, Input } from '../ui/Field';
import { Sheet } from '../ui/Sheet';
import {
  buildTimezoneOptions,
  getBrowserTimezones,
  getDeviceTimezone,
  getTimezoneDisplay,
  sortTimezoneOptions,
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
    fieldLabel: 'Time zone',
    search: 'Search city or time zone',
    title: 'Time zone',
    close: 'Close',
    noResults: 'Try a city, country, or abbreviation: San Francisco, USA, PST',
    topMatches: 'Top matches',
    fallback: 'Using browser time zones.',
  },
  ru: {
    change: 'Изменить часовой пояс',
    detected: 'Определён',
    fieldLabel: 'Часовой пояс',
    search: 'Поиск города или часового пояса',
    title: 'Часовой пояс',
    close: 'Закрыть',
    noResults: 'Попробуй город, страну или сокращение: San Francisco, USA, PST',
    topMatches: 'Лучшие совпадения',
    fallback: 'Использую часовые пояса браузера.',
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
    currentTimezone: value,
    deviceTimezone,
  }), [deviceTimezone, timezones.data?.items, value]);
  const selected = options.find((option) => option.value === value);
  const selectedDisplay = selected ? getTimezoneDisplay(selected, '') : null;
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = (normalizedQuery
    ? options
      .filter((option) => timezoneOptionMatches(option, query))
      .sort((a, b) => sortTimezoneOptions(a, b, query))
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
        className="flex min-h-[68px] w-full items-center justify-between gap-3 px-4 py-3 text-left outline-none transition-colors hover:bg-[var(--surface)] focus:bg-[var(--surface)]"
      >
        <span className="min-w-0">
          <span className="block text-[13.5px] font-medium text-ink">{copy.fieldLabel}</span>
          <span className="mt-1 block break-words text-[14px] font-semibold leading-snug text-ink">
            {selectedDisplay?.primaryLabel ?? value.replace(/_/g, ' ')}
          </span>
          {selectedDisplay?.secondaryLabel && (
            <span className="mt-0.5 block break-words text-[12.5px] leading-snug text-hint">
              {selectedDisplay.secondaryLabel}
            </span>
          )}
          {deviceTimezone && deviceTimezone !== value && (
            <span className="mt-0.5 block break-words text-[12px] leading-snug text-hint">
              {copy.detected}: {deviceTimezone.replace(/_/g, ' ')}
            </span>
          )}
        </span>
        <ChevronRight size={17} className="shrink-0 text-hint" />
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title={copy.title} closeLabel={copy.close}>
        <div className="space-y-3">
          <label className="block">
            <FieldLabel>
              <span className="inline-flex items-center gap-1.5">
                <Search size={13} />
                {copy.search}
              </span>
            </FieldLabel>
            <Input value={query} onChange={setQuery} placeholder={copy.search} autoFocus />
          </label>

          {filtered.length > 0 && (
            <span className="mt-0.5 block truncate text-[12px] text-hint">
              {normalizedQuery
                ? copy.topMatches
                : locale === 'en'
                  ? `${filtered.length} time zones`
                  : `${filtered.length} зон`}
            </span>
          )}

          <div className="flex flex-col gap-1.5">
            {filtered.length === 0 && (
              <div className="rounded-[18px] border border-dashed border-hairline bg-[var(--surface)] px-4 py-5 text-center">
                <p className="text-[13px] font-medium text-ink">{copy.noResults}</p>
              </div>
            )}
            {filtered.map((option) => {
              const display = getTimezoneDisplay(option, query);
              const active = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => handleSelect(option.value)}
                  className={`group flex min-h-[64px] items-center justify-between gap-3 rounded-[18px] border px-3 py-2.5 text-left text-[13.5px] transition-colors ${
                    active
                      ? 'border-[var(--accent-border)] bg-[var(--accent-soft)] text-ink'
                      : 'border-transparent bg-transparent text-ink hover:border-hairline hover:bg-[var(--surface)]'
                  }`}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                      active ? 'bg-[var(--surface-strong)] text-accent-text' : 'bg-[var(--secondary-bg)] text-hint'
                    }`}
                    >
                      <MapPin size={17} />
                    </span>
                    <span className="min-w-0">
                      <span className="block break-words text-[14px] font-semibold leading-snug">{display.primaryLabel}</span>
                      <span className="mt-0.5 block break-words text-[12px] leading-snug text-hint">{display.secondaryLabel}</span>
                      {display.chips.length > 0 && (
                        <span className="mt-1.5 flex flex-wrap gap-1">
                          {display.chips.slice(0, 3).map((chip) => (
                            <span
                              key={chip}
                              className="rounded-full bg-[var(--secondary-bg)] px-2 py-0.5 text-[11px] font-medium text-hint"
                            >
                              {chip}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                  </span>
                  {active && <Check size={17} className="shrink-0 text-accent-text" />}
                </button>
              );
            })}
          </div>

          {timezones.isError && (
            <p className="text-[12px] text-hint">{copy.fallback}</p>
          )}
        </div>
      </Sheet>
    </>
  );
}
