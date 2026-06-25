import { useEffect, useMemo, useState } from 'react';
import { Globe2 } from 'lucide-react';
import { usePatchSettings, useSettings } from '../../api/hooks';
import { getDeviceTimezone, timezoneDismissKey } from '../../lib/timezones';

const COPY = {
  en: {
    title: 'Detected time zone differs',
    current: 'Current',
    detected: 'Detected',
    use: 'Use detected',
    keep: 'Keep current',
  },
  ru: {
    title: 'Часовой пояс отличается',
    current: 'Сейчас',
    detected: 'Определён',
    use: 'Использовать',
    keep: 'Оставить текущий',
  },
};

function localeOf(value: string | null | undefined): 'en' | 'ru' {
  return value === 'ru' ? 'ru' : 'en';
}

export function TimezoneMismatchPrompt() {
  const settings = useSettings();
  const patch = usePatchSettings();
  const deviceTimezone = getDeviceTimezone();
  const profileTimezone = settings.data?.user.timezone ?? null;
  const locale = localeOf(settings.data?.user.locale);
  const copy = COPY[locale];
  const dismissKey = useMemo(() => (
    profileTimezone && deviceTimezone
      ? timezoneDismissKey(profileTimezone, deviceTimezone)
      : null
  ), [deviceTimezone, profileTimezone]);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setDismissed(dismissKey ? localStorage.getItem(dismissKey) === '1' : false);
  }, [dismissKey]);

  const dismissedInStorage = dismissKey ? localStorage.getItem(dismissKey) === '1' : false;
  if (
    !profileTimezone
    || !deviceTimezone
    || profileTimezone === deviceTimezone
    || dismissed
    || dismissedInStorage
  ) {
    return null;
  }

  const keepCurrent = () => {
    if (dismissKey) localStorage.setItem(dismissKey, '1');
    setDismissed(true);
  };
  const useDetected = () => {
    patch.mutate({ timezone: deviceTimezone }, { onSuccess: () => setDismissed(true) });
  };

  return (
    <div
      className="fixed left-1/2 z-[70] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 rounded-2xl border border-hairline bg-surface px-4 py-3 shadow-card"
      style={{ bottom: 'calc(env(safe-area-inset-bottom) + 148px)' }}
      role="status"
    >
      <div className="flex items-start gap-2.5">
        <Globe2 size={18} className="mt-0.5 shrink-0 text-accent-text" />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold text-ink">{copy.title}</p>
          <p className="mt-1 break-words text-[12.5px] leading-snug text-hint">
            {copy.current}: {profileTimezone} · {copy.detected}: {deviceTimezone}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={useDetected}
              disabled={patch.isPending}
              className="h-10 min-w-0 rounded-full bg-accent px-2 text-[13px] font-medium text-white shadow-[0_6px_18px_rgba(46,99,231,0.3)] disabled:opacity-55"
            >
              {copy.use}
            </button>
            <button
              type="button"
              onClick={keepCurrent}
              className="h-10 min-w-0 rounded-full border border-hairline px-2 text-[13px] font-medium text-ink"
            >
              {copy.keep}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
