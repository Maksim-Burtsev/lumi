import { describe, expect, it } from 'vitest';
import {
  automationTypeLabel,
  inboxCategoryLabel,
  memoryKindLabel,
  memorySourceLabel,
  priorityLabel,
  runStatusLabel,
  runTypeLabel,
} from './labels';
import { normalizeAppLocale } from './i18n';

describe('localized API labels', () => {
  it('uses English labels when locale is English', () => {
    expect(runTypeLabel('daily_planning', 'en')).toBe('Day plan');
    expect(runStatusLabel('queued', 'en')).toBe('Queued');
    expect(inboxCategoryLabel('needs_reply', 'en')).toBe('Needs reply');
    expect(memoryKindLabel('preference', 'en')).toBe('Preference');
    expect(memorySourceLabel('chat', 'en')).toBe('from chat');
    expect(automationTypeLabel('calendar_sync', 'en')).toBe('Calendar sync');
    expect(priorityLabel('urgent', 'en')).toBe('urgent');
  });

  it('keeps Russian labels when locale is Russian', () => {
    expect(runTypeLabel('daily_planning', 'ru')).toBe('План дня');
    expect(runStatusLabel('queued', 'ru')).toBe('В очереди');
    expect(inboxCategoryLabel('needs_reply', 'ru')).toBe('Ждут ответа');
    expect(memoryKindLabel('preference', 'ru')).toBe('Предпочтение');
    expect(memorySourceLabel('chat', 'ru')).toBe('из чата');
    expect(automationTypeLabel('calendar_sync', 'ru')).toBe('Синхронизация календаря');
    expect(priorityLabel('urgent', 'ru')).toBe('срочно');
  });

  it('falls back to English for missing or unsupported locale values', () => {
    expect(normalizeAppLocale(undefined)).toBe('en');
    expect(normalizeAppLocale('de')).toBe('en');
    expect(runTypeLabel('calendar_sync')).toBe('Calendar sync');
  });
});
