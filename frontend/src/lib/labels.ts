/** Russian label maps for machine codes coming from the API. */

export const RUN_TYPE_LABELS: Record<string, string> = {
  email_triage: 'Разбор почты',
  news_digest: 'Дайджест новостей',
  daily_planning: 'План дня',
  plan_day: 'План дня',
  calendar_sync: 'Синхронизация календаря',
  task_review: 'Обзор задач',
  custom_prompt: 'Свой сценарий',
  chat: 'Чат',
};

export function runTypeLabel(type: string): string {
  return RUN_TYPE_LABELS[type] ?? type;
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: 'В очереди',
  running: 'Выполняется',
  completed: 'Готово',
  failed: 'Ошибка',
  cancelled: 'Отменён',
};

export function runStatusLabel(status: string): string {
  return RUN_STATUS_LABELS[status] ?? status;
}

export const INBOX_CATEGORY_LABELS: Record<string, string> = {
  needs_reply: 'Ждут ответа',
  waiting_for_me: 'Жду ответа',
  decision_needed: 'Нужно решение',
  fyi: 'К сведению',
  newsletter: 'Рассылки',
  invoice_document: 'Счета и документы',
  ignore: 'Можно пропустить',
  unknown: 'Прочее',
};

export function inboxCategoryLabel(category: string): string {
  return INBOX_CATEGORY_LABELS[category] ?? category;
}

export const MEMORY_KIND_LABELS: Record<string, string> = {
  preference: 'Предпочтение',
  fact: 'Факт',
  project: 'Проект',
  instruction: 'Инструкция',
  contact: 'Контакт',
  workflow: 'Процесс',
  other: 'Другое',
};

export function memoryKindLabel(kind: string): string {
  return MEMORY_KIND_LABELS[kind] ?? kind;
}

export const MEMORY_SOURCE_LABELS: Record<string, string> = {
  chat: 'из чата',
  email: 'из почты',
  agent: 'от агента',
  manual: 'добавлено вручную',
};

export const AUTOMATION_TYPE_LABELS: Record<string, string> = {
  morning_brief: 'Утренний бриф',
  news_digest: 'Дайджест новостей',
  email_triage: 'Разбор почты',
  daily_planning: 'План дня',
  calendar_sync: 'Синхронизация календаря',
  task_review: 'Обзор задач',
  custom_prompt: 'Свой сценарий',
};

export function automationTypeLabel(type: string): string {
  return AUTOMATION_TYPE_LABELS[type] ?? type;
}

export const PRIORITY_LABELS: Record<string, string> = {
  low: 'низкий',
  medium: 'средний',
  high: 'высокий',
  urgent: 'срочно',
};

/** Common timezone choices for the Settings select. */
export const COMMON_TIMEZONES: string[] = [
  'Europe/Moscow',
  'Europe/Kaliningrad',
  'Europe/Samara',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Krasnoyarsk',
  'Asia/Irkutsk',
  'Asia/Vladivostok',
  'Europe/Kyiv',
  'Europe/Minsk',
  'Europe/Belgrade',
  'Europe/Berlin',
  'Europe/Paris',
  'Europe/London',
  'Europe/Lisbon',
  'Asia/Tbilisi',
  'Asia/Yerevan',
  'Asia/Almaty',
  'Asia/Tashkent',
  'Asia/Dubai',
  'Asia/Bangkok',
  'Asia/Singapore',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
];
