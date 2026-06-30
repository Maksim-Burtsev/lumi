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

  it('normalizes Russian locale to English labels', () => {
    expect(normalizeAppLocale('ru')).toBe('en');
    expect(runTypeLabel('daily_planning', 'ru')).toBe('Day plan');
    expect(runStatusLabel('queued', 'ru')).toBe('Queued');
    expect(inboxCategoryLabel('needs_reply', 'ru')).toBe('Needs reply');
    expect(memoryKindLabel('preference', 'ru')).toBe('Preference');
    expect(memorySourceLabel('chat', 'ru')).toBe('from chat');
    expect(automationTypeLabel('calendar_sync', 'ru')).toBe('Calendar sync');
    expect(priorityLabel('urgent', 'ru')).toBe('urgent');
  });

  it('falls back to English for missing or unsupported locale values', () => {
    expect(normalizeAppLocale(undefined)).toBe('en');
    expect(normalizeAppLocale('de')).toBe('en');
    expect(runTypeLabel('calendar_sync')).toBe('Calendar sync');
  });
});
