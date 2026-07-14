import { CalendarDays, ListChecks, Settings, Sunrise, Timer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { AppLocale } from '../../lib/i18n';

export interface NavigationItem {
  to: string;
  label: Record<AppLocale, string>;
  icon: LucideIcon;
  also?: string[];
}

export const PRODUCT_NAV_ITEMS: NavigationItem[] = [
  { to: '/', label: { en: 'Today', ru: 'Сегодня' }, icon: Sunrise },
  { to: '/tasks', label: { en: 'Tasks', ru: 'Задачи' }, icon: ListChecks },
  { to: '/sessions', label: { en: 'Sessions', ru: 'Сессии' }, icon: Timer, also: ['/focus'] },
  { to: '/calendar', label: { en: 'Calendar', ru: 'Календарь' }, icon: CalendarDays },
];

export const SETTINGS_NAV_ITEM: NavigationItem = {
  to: '/settings',
  label: { en: 'Settings', ru: 'Настройки' },
  icon: Settings,
};

export function isNavigationItemActive(pathname: string, item: NavigationItem): boolean {
  if (item.to === '/') return pathname === '/';
  return pathname.startsWith(item.to) || (item.also?.some((path) => pathname.startsWith(path)) ?? false);
}

export function pageTitle(pathname: string, locale: AppLocale): string {
  const item = [...PRODUCT_NAV_ITEMS, SETTINGS_NAV_ITEM].find((candidate) =>
    isNavigationItemActive(pathname, candidate),
  );
  return item?.label[locale] ?? 'Lumi';
}
