import { useEffect, useMemo, useState } from 'react';
import { Globe2 } from 'lucide-react';
import { usePatchSettings, useSettings } from '../../api/hooks';
import { Button } from '../ui/Button';
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

const PROMPT_RESERVE = '148px';

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
  const visible = !(
    !profileTimezone ||
    !deviceTimezone ||
    profileTimezone === deviceTimezone ||
    dismissed ||
    dismissedInStorage
  );

  useEffect(() => {
    const root = document.documentElement;
    if (!visible) {
      root.style.removeProperty('--timezone-prompt-reserve');
      return;
    }
    root.style.setProperty('--timezone-prompt-reserve', PROMPT_RESERVE);
    return () => {
      root.style.removeProperty('--timezone-prompt-reserve');
    };
  }, [visible]);

  if (!visible) {
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
      className="fixed left-1/2 z-[45] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 rounded-2xl border border-hairline bg-surface px-4 py-3 shadow-card"
      style={{ bottom: 'calc(env(safe-area-inset-bottom) + 84px)' }}
      role="status"
    >
      <div className="flex items-start gap-2.5">
        <Globe2 size={18} className="mt-0.5 shrink-0 text-accent-text" />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold text-ink">{copy.title}</p>
          <p className="mt-1 break-words text-[12.5px] leading-snug text-hint">
            {copy.current}: {profileTimezone} · {copy.detected}: {deviceTimezone}
          </p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={useDetected} busy={patch.isPending}>
              {copy.use}
            </Button>
            <Button size="sm" variant="ghost" onClick={keepCurrent}>
              {copy.keep}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
