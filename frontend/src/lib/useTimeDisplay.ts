import { useSettings } from '../api/hooks';
import type { TimeDisplayOptions } from './format';
import { normalizeTimeFormat } from './format';
import { normalizeAppLocale } from './i18n';

export function useTimeDisplay(): TimeDisplayOptions {
  const settings = useSettings();
  const user = settings.data?.user;
  return {
    locale: normalizeAppLocale(user?.locale),
    timeFormat: normalizeTimeFormat(user?.settings?.time_format),
    timezone: user?.timezone,
  };
}
