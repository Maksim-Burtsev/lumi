import { useSettings } from '../api/hooks';
import { normalizeAppLocale } from './i18n';

export function useAppLocale() {
  const settings = useSettings();
  return normalizeAppLocale(settings.data?.user.locale);
}
