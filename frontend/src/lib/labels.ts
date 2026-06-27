import type { AppLocale } from './i18n';
import { normalizeAppLocale } from './i18n';

/** Labels for machine codes coming from the API. */

type LabelMap = Record<string, string>;
type LocalizedLabels = Record<AppLocale, LabelMap>;

function labelFrom(labels: LocalizedLabels, key: string, locale?: AppLocale): string {
  return labels[normalizeAppLocale(locale)][key] ?? key;
}

export const RUN_TYPE_LABELS: LocalizedLabels = {
  en: {
    email_triage: 'Email triage',
    news_digest: 'News digest',
    daily_planning: 'Day plan',
    plan_day: 'Day plan',
    calendar_sync: 'Calendar sync',
    task_review: 'Task review',
    custom_prompt: 'Custom workflow',
    chat: 'Chat',
  },
  ru: {
    email_triage: 'Разбор почты',
    news_digest: 'Дайджест новостей',
    daily_planning: 'План дня',
    plan_day: 'План дня',
    calendar_sync: 'Синхронизация календаря',
    task_review: 'Обзор задач',
    custom_prompt: 'Свой сценарий',
    chat: 'Чат',
  },
};

export function runTypeLabel(type: string, locale?: AppLocale): string {
  return labelFrom(RUN_TYPE_LABELS, type, locale);
}

export const RUN_STATUS_LABELS: LocalizedLabels = {
  en: {
    queued: 'Queued',
    running: 'Running',
    completed: 'Done',
    failed: 'Error',
    cancelled: 'Cancelled',
  },
  ru: {
    queued: 'В очереди',
    running: 'Выполняется',
    completed: 'Готово',
    failed: 'Ошибка',
    cancelled: 'Отменён',
  },
};

export function runStatusLabel(status: string, locale?: AppLocale): string {
  return labelFrom(RUN_STATUS_LABELS, status, locale);
}

export const INBOX_CATEGORY_LABELS: LocalizedLabels = {
  en: {
    needs_reply: 'Needs reply',
    waiting_for_me: 'Waiting on me',
    decision_needed: 'Decision needed',
    fyi: 'FYI',
    newsletter: 'Newsletters',
    invoice_document: 'Invoices and docs',
    ignore: 'Can skip',
    unknown: 'Other',
  },
  ru: {
    needs_reply: 'Ждут ответа',
    waiting_for_me: 'Жду ответа',
    decision_needed: 'Нужно решение',
    fyi: 'К сведению',
    newsletter: 'Рассылки',
    invoice_document: 'Счета и документы',
    ignore: 'Можно пропустить',
    unknown: 'Прочее',
  },
};

export function inboxCategoryLabel(category: string, locale?: AppLocale): string {
  return labelFrom(INBOX_CATEGORY_LABELS, category, locale);
}

export const MEMORY_KIND_LABELS: LocalizedLabels = {
  en: {
    preference: 'Preference',
    fact: 'Fact',
    project: 'Project',
    instruction: 'Instruction',
    contact: 'Contact',
    workflow: 'Workflow',
    other: 'Other',
  },
  ru: {
    preference: 'Предпочтение',
    fact: 'Факт',
    project: 'Проект',
    instruction: 'Инструкция',
    contact: 'Контакт',
    workflow: 'Процесс',
    other: 'Другое',
  },
};

export function memoryKindLabel(kind: string, locale?: AppLocale): string {
  return labelFrom(MEMORY_KIND_LABELS, kind, locale);
}

export const MEMORY_SOURCE_LABELS: LocalizedLabels = {
  en: {
    chat: 'from chat',
    email: 'from email',
    agent: 'from agent',
    manual: 'added manually',
  },
  ru: {
    chat: 'из чата',
    email: 'из почты',
    agent: 'от агента',
    manual: 'добавлено вручную',
  },
};

export function memorySourceLabel(source: string, locale?: AppLocale): string {
  return labelFrom(MEMORY_SOURCE_LABELS, source, locale);
}

export const AUTOMATION_TYPE_LABELS: LocalizedLabels = {
  en: {
    morning_brief: 'Morning brief',
    news_digest: 'News digest',
    email_triage: 'Email triage',
    daily_planning: 'Day plan',
    calendar_sync: 'Calendar sync',
    task_review: 'Task review',
    custom_prompt: 'Custom workflow',
  },
  ru: {
    morning_brief: 'Утренний бриф',
    news_digest: 'Дайджест новостей',
    email_triage: 'Разбор почты',
    daily_planning: 'План дня',
    calendar_sync: 'Синхронизация календаря',
    task_review: 'Обзор задач',
    custom_prompt: 'Свой сценарий',
  },
};

export function automationTypeLabel(type: string, locale?: AppLocale): string {
  return labelFrom(AUTOMATION_TYPE_LABELS, type, locale);
}

export const PRIORITY_LABELS: LocalizedLabels = {
  en: {
    low: 'low',
    medium: 'medium',
    high: 'high',
    urgent: 'urgent',
  },
  ru: {
    low: 'низкий',
    medium: 'средний',
    high: 'высокий',
    urgent: 'срочно',
  },
};

export function priorityLabel(priority: string, locale?: AppLocale): string {
  return labelFrom(PRIORITY_LABELS, priority, locale);
}
