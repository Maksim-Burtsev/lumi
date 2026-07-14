import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CloudOff,
  Copy,
  ExternalLink,
  Users,
  MapPin,
  Plus,
  RefreshCw,
  Sparkles,
  Video,
  X,
} from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { api } from '../api/client';
import {
  qk,
  useAgentRunAction,
  useCalendarEvents,
  useConfirmBlock,
  useCreateEvent,
  useDeleteCalendarPrivateNote,
  useDeleteEvent,
  useUpdateCalendarPrivateNote,
} from '../api/hooks';
import type { CalendarAttendee, CalendarEvent, CalendarPerson } from '../api/types';
import { DayGrid } from '../components/calendar/DayGrid';
import { PRIVATE_NOTE_MAX_CHARS, PrivateNoteSection } from '../components/calendar/PrivateNoteSection';
import { Button } from '../components/ui/Button';
import { ErrorState } from '../components/ui/ErrorState';
import { Sheet } from '../components/ui/Sheet';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SkeletonTimeline } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { addDays, formatDateParam, formatDayLabel, formatRelative, formatTime, formatTimeRange, isSameDay, startOfDay } from '../lib/format';
import type { AppLocale } from '../lib/i18n';
import { useAppLocale } from '../lib/useAppLocale';
import { useTimeDisplay } from '../lib/useTimeDisplay';
import { haptic, openExternalLink } from '../telegram/webapp';

interface SheetPrefill {
  start: string; // "HH:MM"
  end: string;
}

interface ContactAction {
  person: CalendarPerson | CalendarAttendee;
  anchor: DOMRect;
}

const CALENDAR_COPY: Record<AppLocale, {
  linkFallback: string;
  participantFallback: string;
  responseDeclined: string;
  responseTentative: string;
  responseNeedsAction: string;
  copyEmail: string;
  closeContact: string;
  participantContact: string;
  defaultBlockTitle: string;
  titleRequired: string;
  endAfterStart: string;
  blockCreated: string;
  blockCreateFailed: string;
  newBlock: string;
  internalCalendar: string;
  title: string;
  titlePlaceholder: string;
  start: string;
  end: string;
  descriptionOptional: string;
  descriptionPlaceholder: string;
  locationOptional: string;
  locationPlaceholder: string;
  linksOptional: string;
  createBlock: string;
  noteLabel: string;
  notePlaceholder: string;
  noteMaxError: string;
  noteDeleted: string;
  noteDeleteFailed: string;
  noteSaved: string;
  noteSaveFailed: string;
  calendarSynced: string;
  planReady: string;
  copied: string;
  copyFailed: string;
  prevDay: string;
  nextDay: string;
  backToday: string;
  sync: string;
  planDay: string;
  updatingExternal: string;
  lastSync: (value: string) => string;
  externalSyncHint: string;
  googleMissingTitle: string;
  googleMissingHint: string;
  openSettings: string;
  hideHint: string;
  loadFailed: string;
  noMeetingsScheduled: string;
  yandexCalendar: string;
  proposedLumi: string;
  participants: string;
  organizer: string;
  optional: string;
  resource: string;
  hide: string;
  showAll: (count: number) => string;
  meeting: string;
  openOriginal: string;
  externalManaged: string;
  blockConfirmed: string;
  confirmFailed: string;
  accept: string;
  removed: string;
  removeFailed: string;
  reject: string;
  remove: string;
}> = {
  en: {
    linkFallback: 'Link',
    participantFallback: 'Participant',
    responseDeclined: 'declined',
    responseTentative: 'tentative',
    responseNeedsAction: 'needs reply',
    copyEmail: 'Copy email',
    closeContact: 'Close contact',
    participantContact: 'Attendee contact',
    defaultBlockTitle: 'Focus block',
    titleRequired: 'Name the block, for example "Lumi architecture"',
    endAfterStart: 'End time must be after start time',
    blockCreated: 'Block created',
    blockCreateFailed: 'Could not create block',
    newBlock: 'New block',
    internalCalendar: 'Lumi internal calendar',
    title: 'Title',
    titlePlaceholder: 'Focus: Lumi architecture',
    start: 'Start',
    end: 'End',
    descriptionOptional: 'Description (optional)',
    descriptionPlaceholder: 'What needs to happen in this block',
    locationOptional: 'Location (optional)',
    locationPlaceholder: 'Office, Zoom, home',
    linksOptional: 'Links (optional)',
    createBlock: 'Create block',
    noteLabel: 'Personal note (optional)',
    notePlaceholder: 'Context just for yourself',
    noteMaxError: `Personal note is limited to ${PRIVATE_NOTE_MAX_CHARS} characters`,
    noteDeleted: 'Note deleted',
    noteDeleteFailed: 'Could not delete note',
    noteSaved: 'Note saved',
    noteSaveFailed: 'Could not save note',
    calendarSynced: 'Calendar synced',
    planReady: 'Plan ready',
    copied: 'Copied',
    copyFailed: 'Could not copy',
    prevDay: 'Previous day',
    nextDay: 'Next day',
    backToday: 'Back to today',
    sync: 'Sync',
    planDay: 'Plan day',
    updatingExternal: 'Calendar is updating from an external source.',
    lastSync: (value) => `Last sync: ${value}.`,
    externalSyncHint: 'External calendar will update after connection or manual sync.',
    googleMissingTitle: 'Google Calendar is not connected',
    googleMissingHint: 'Lumi already keeps an internal calendar. After you connect Google, it will include work meetings too.',
    openSettings: 'Open settings',
    hideHint: 'Hide hint',
    loadFailed: 'Could not load calendar.',
    noMeetingsScheduled: 'No meetings scheduled',
    yandexCalendar: 'Yandex Calendar',
    proposedLumi: 'Lumi proposal',
    participants: 'Participants',
    organizer: 'organizer',
    optional: 'opt.',
    resource: 'resource',
    hide: 'Hide',
    showAll: (count) => `Show all (${count})`,
    meeting: 'Meeting',
    openOriginal: 'Open original',
    externalManaged: 'External calendar event: it is managed there, Lumi only reads it.',
    blockConfirmed: 'Block confirmed',
    confirmFailed: 'Could not confirm',
    accept: 'Accept',
    removed: 'Removed from schedule',
    removeFailed: 'Could not remove',
    reject: 'Reject',
    remove: 'Remove',
  },
  ru: {
    linkFallback: 'Ссылка',
    participantFallback: 'Участник',
    responseDeclined: 'отказался',
    responseTentative: 'возможно',
    responseNeedsAction: 'ждёт ответа',
    copyEmail: 'Скопировать email',
    closeContact: 'Закрыть контакт',
    participantContact: 'Контакт участника',
    defaultBlockTitle: 'Фокус-блок',
    titleRequired: 'Назови блок — например, «Архитектура Lumi»',
    endAfterStart: 'Время окончания должно быть позже начала',
    blockCreated: 'Блок создан',
    blockCreateFailed: 'Не удалось создать блок',
    newBlock: 'Новый блок',
    internalCalendar: 'внутренний календарь Lumi',
    title: 'Название',
    titlePlaceholder: 'Фокус: архитектура Lumi',
    start: 'Начало',
    end: 'Конец',
    descriptionOptional: 'Описание (необязательно)',
    descriptionPlaceholder: 'Что нужно сделать в этом блоке',
    locationOptional: 'Место (необязательно)',
    locationPlaceholder: 'Офис, Zoom, дом',
    linksOptional: 'Ссылки (необязательно)',
    createBlock: 'Создать блок',
    noteLabel: 'Личная заметка (необязательно)',
    notePlaceholder: 'Контекст только для себя',
    noteMaxError: `Личная заметка — до ${PRIVATE_NOTE_MAX_CHARS} символов`,
    noteDeleted: 'Заметка удалена',
    noteDeleteFailed: 'Не удалось удалить заметку',
    noteSaved: 'Заметка сохранена',
    noteSaveFailed: 'Не удалось сохранить заметку',
    calendarSynced: 'Календарь синхронизирован',
    planReady: 'План готов',
    copied: 'Скопировано',
    copyFailed: 'Не удалось скопировать',
    prevDay: 'Предыдущий день',
    nextDay: 'Следующий день',
    backToday: 'Вернуться к сегодня',
    sync: 'Синхронизировать',
    planDay: 'Спланировать день',
    updatingExternal: 'Календарь обновляется из внешнего источника.',
    lastSync: (value) => `Последняя синхронизация: ${value}.`,
    externalSyncHint: 'Внешний календарь обновится после подключения или ручной синхронизации.',
    googleMissingTitle: 'Google Calendar не подключен',
    googleMissingHint: 'Lumi уже ведёт внутренний календарь. После подключения Google он будет учитывать и рабочие встречи.',
    openSettings: 'Открыть настройки',
    hideHint: 'Скрыть подсказку',
    loadFailed: 'Не удалось загрузить календарь.',
    noMeetingsScheduled: 'Нет запланированных встреч',
    yandexCalendar: 'Яндекс.Календарь',
    proposedLumi: 'предложение Lumi',
    participants: 'Участники',
    organizer: 'организатор',
    optional: 'опц.',
    resource: 'ресурс',
    hide: 'Скрыть',
    showAll: (count) => `Показать всех (${count})`,
    meeting: 'Встреча',
    openOriginal: 'Открыть оригинал',
    externalManaged: 'Событие из внешнего календаря — управляется там, Lumi его только читает.',
    blockConfirmed: 'Блок подтверждён',
    confirmFailed: 'Не удалось подтвердить',
    accept: 'Принять',
    removed: 'Убрано из расписания',
    removeFailed: 'Не удалось убрать',
    reject: 'Отклонить',
    remove: 'Убрать',
  },
};

function combine(day: Date, time: string): Date | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (!m) return null;
  return new Date(day.getFullYear(), day.getMonth(), day.getDate(), parseInt(m[1], 10), parseInt(m[2], 10));
}

function parseLinks(value: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of value.split(/[\s,\n]+/)) {
    const link = raw.trim().replace(/[.,;:!?)]$/, '');
    if (!/^https?:\/\//i.test(link) || seen.has(link)) continue;
    out.push(link);
    seen.add(link);
  }
  return out;
}

function linkLabel(url: string, locale: AppLocale): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return CALENDAR_COPY[locale].linkFallback;
  }
}

function sameUrl(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a.replace(/\/$/, '').toLowerCase() === b.replace(/\/$/, '').toLowerCase());
}

function isCalendarServiceLink(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '').toLowerCase();
    return host === 'calendar.yandex.ru' || host === 'calendar.yandex.com' || host === 'calendar.google.com';
  } catch {
    return false;
  }
}

function visibleLinks(event: CalendarEvent): string[] {
  return event.links.filter(
    (link) => !sameUrl(link, event.meeting_url) && !sameUrl(link, event.external_url) && !isCalendarServiceLink(link),
  );
}

function personLabel(person: { name?: string; email?: string }, locale: AppLocale): string {
  return person.name || person.email || CALENDAR_COPY[locale].participantFallback;
}

function responseLabel(status: string | null | undefined, locale: AppLocale): string | null {
  const copy = CALENDAR_COPY[locale];
  if (status === 'declined') return copy.responseDeclined;
  if (status === 'tentative') return copy.responseTentative;
  if (status === 'needsAction') return copy.responseNeedsAction;
  return null;
}

function contactPopoverStyle(anchor: DOMRect): CSSProperties {
  const margin = 12;
  const width = Math.min(360, window.innerWidth - margin * 2);
  const height = 164;
  const left = Math.min(Math.max(anchor.left, margin), window.innerWidth - width - margin);
  let top = anchor.bottom + 8;
  if (top + height > window.innerHeight - margin) {
    top = Math.max(margin, anchor.top - height - 8);
  }
  return { left, top, width };
}

function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);

  const input = document.createElement('textarea');
  input.value = value;
  input.setAttribute('readonly', '');
  input.style.position = 'fixed';
  input.style.opacity = '0';
  document.body.appendChild(input);
  input.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(input);
  return ok ? Promise.resolve() : Promise.reject(new Error('copy_failed'));
}

function ContactActionSheet({
  contact,
  onClose,
  onCopy,
  locale,
}: {
  contact: ContactAction | null;
  onClose: () => void;
  onCopy: (email: string) => void;
  locale: AppLocale;
}) {
  const reduceMotion = useReducedMotion();
  const copy = CALENDAR_COPY[locale];
  const email = contact?.person.email;
  if (!contact || !email) return null;

  const actions = (
    <>
      <p className="truncate px-4 py-3 text-[15px] text-hint">{email}</p>
      <div className="h-px bg-[var(--hairline)]" />
      <button
        type="button"
        onClick={() => onCopy(email)}
        className="flex min-h-12 w-full items-center gap-3 px-4 text-left text-[15px] font-medium text-ink"
      >
        <Copy size={17} className="shrink-0 text-hint" />
        {copy.copyEmail}
      </button>
    </>
  );

  const content = (
    <div className="fixed inset-0 z-[90]">
      <button type="button" aria-label={copy.closeContact} className="absolute inset-0 cursor-default" onClick={onClose} />
      <motion.div
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="absolute inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+14px)] overflow-hidden rounded-[22px] border border-hairline bg-[var(--surface-strong)] shadow-card sm:hidden"
        role="dialog"
        aria-modal="true"
        aria-label={copy.participantContact}
      >
        {actions}
      </motion.div>
      <motion.div
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="absolute hidden overflow-hidden rounded-2xl border border-hairline bg-[var(--surface-strong)] shadow-card sm:block"
        style={contactPopoverStyle(contact.anchor)}
        role="dialog"
        aria-modal="true"
        aria-label={copy.participantContact}
      >
        {actions}
      </motion.div>
    </div>
  );

  return createPortal(content, document.body);
}

function ParticipantRow({
  person,
  labels,
  onContact,
  locale,
}: {
  person: CalendarPerson | CalendarAttendee;
  labels: string[];
  onContact: (person: CalendarPerson | CalendarAttendee, anchor: DOMRect) => void;
  locale: AppLocale;
}) {
  const label = personLabel(person, locale);
  const badges = labels.filter(Boolean);
  const content = (
    <>
      <span className="min-w-0 flex-1 truncate text-[14px] text-ink">{label}</span>
      {badges.map((badge) => (
        <span key={badge} className="shrink-0 text-[12.5px] text-hint">
          {badge}
        </span>
      ))}
    </>
  );

  if (!person.email) {
    return <p className="flex min-w-0 items-center gap-2 py-0.5">{content}</p>;
  }

  return (
    <button
      type="button"
      onClick={(event) => onContact(person, event.currentTarget.getBoundingClientRect())}
      className="-mx-2 flex w-[calc(100%+16px)] min-w-0 items-center gap-2 rounded-xl px-2 py-1.5 text-left transition active:bg-[var(--secondary-bg)] sm:hover:bg-[var(--secondary-bg)]"
      aria-label={locale === 'en' ? `Open contact: ${label}` : `Открыть контакт: ${label}`}
    >
      {content}
    </button>
  );
}

function CreateBlockSheet({
  open,
  onClose,
  day,
  prefill,
  locale,
}: {
  open: boolean;
  onClose: () => void;
  day: Date;
  prefill: SheetPrefill | null;
  locale: AppLocale;
}) {
  const [title, setTitle] = useState('');
  const [start, setStart] = useState('10:00');
  const [end, setEnd] = useState('11:00');
  const [description, setDescription] = useState('');
  const [privateNote, setPrivateNote] = useState('');
  const [location, setLocation] = useState('');
  const [linksText, setLinksText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createEvent = useCreateEvent();
  const { show } = useToast();
  const timeDisplay = useTimeDisplay();
  const copy = CALENDAR_COPY[locale];

  // Re-seed fields each time the sheet opens (keyed remount from parent)
  const [seeded, setSeeded] = useState(false);
  if (open && !seeded) {
    setSeeded(true);
    if (prefill) {
      setStart(prefill.start);
      setEnd(prefill.end);
      setTitle(copy.defaultBlockTitle);
    }
  }
  if (!open && seeded) {
    setSeeded(false);
    setTitle('');
    setStart('10:00');
    setEnd('11:00');
    setDescription('');
    setPrivateNote('');
    setLocation('');
    setLinksText('');
    setError(null);
  }

  const submit = () => {
    const trimmed = title.trim();
    if (!trimmed) {
      setError(copy.titleRequired);
      return;
    }
    const startDate = combine(day, start);
    const endDate = combine(day, end);
    if (!startDate || !endDate || endDate.getTime() <= startDate.getTime()) {
      setError(copy.endAfterStart);
      return;
    }
    if (privateNote.length > PRIVATE_NOTE_MAX_CHARS) {
      setError(copy.noteMaxError);
      return;
    }
    setError(null);
    const links = parseLinks(linksText);
    createEvent.mutate(
      {
        title: trimmed,
        start_at: startDate.toISOString(),
        end_at: endDate.toISOString(),
        ...(description.trim() ? { description: description.trim() } : {}),
        ...(privateNote.trim() ? { private_note: privateNote.trim() } : {}),
        ...(location.trim() ? { location: location.trim() } : {}),
        ...(links.length ? { links } : {}),
      },
      {
        onSuccess: () => {
          haptic('success');
          show(copy.blockCreated, 'success');
          onClose();
        },
        onError: () => show(copy.blockCreateFailed, 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title={copy.newBlock}>
      <p className="mb-4 text-[13px] text-hint">{formatDayLabel(day, timeDisplay)} · {copy.internalCalendar}</p>
      <label className="block">
        <FieldLabel>{copy.title}</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder={copy.titlePlaceholder} />
      </label>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <FieldLabel>{copy.start}</FieldLabel>
          <Input type="time" value={start} onChange={setStart} />
        </label>
        <label className="block">
          <FieldLabel>{copy.end}</FieldLabel>
          <Input type="time" value={end} onChange={setEnd} />
        </label>
      </div>
      <label className="mt-4 block">
        <FieldLabel>{copy.descriptionOptional}</FieldLabel>
        <Textarea value={description} onChange={setDescription} rows={2} placeholder={copy.descriptionPlaceholder} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.noteLabel}</FieldLabel>
        <Textarea value={privateNote} onChange={setPrivateNote} rows={3} placeholder={copy.notePlaceholder} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.locationOptional}</FieldLabel>
        <Input value={location} onChange={setLocation} placeholder={copy.locationPlaceholder} />
      </label>
      <label className="mt-4 block">
        <FieldLabel>{copy.linksOptional}</FieldLabel>
        <Textarea value={linksText} onChange={setLinksText} rows={2} placeholder="https://..." />
      </label>
      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createEvent.isPending} onClick={submit}>
        {copy.createBlock}
      </Button>
    </Sheet>
  );
}

export default function CalendarPage() {
  const [day, setDay] = useState<Date>(() => startOfDay(new Date()));
  const [sheetOpen, setSheetOpen] = useState(false);
  const [prefill, setPrefill] = useState<SheetPrefill | null>(null);
  const [googleHint, setGoogleHint] = useState(false);
  const navigate = useNavigate();
  const { show } = useToast();
  const reduceMotion = useReducedMotion();
  const timeDisplay = useTimeDisplay();
  const locale = useAppLocale();
  const copy = CALENDAR_COPY[locale];

  const rangeStart = day.toISOString();
  const rangeEnd = addDays(day, 1).toISOString();
  const eventsQuery = useCalendarEvents(rangeStart, rangeEnd);
  const confirmBlock = useConfirmBlock();
  const deleteEvent = useDeleteEvent();
  const updatePrivateNote = useUpdateCalendarPrivateNote();
  const deletePrivateNote = useDeleteCalendarPrivateNote();

  const syncAction = useAgentRunAction({
    start: () => api.syncCalendar(),
    invalidate: [qk.eventsAll, qk.freeSlotsAll],
    successMessage: copy.calendarSynced,
    onApiError: (error) => {
      if (error.status === 409 && (error.error === 'calendar_not_connected' || error.error === 'google_not_connected')) {
        setGoogleHint(true);
        return true;
      }
      return false;
    },
  });

  const planAction = useAgentRunAction({
    start: () => api.planDay(formatDateParam(day)),
    invalidate: [qk.eventsAll, qk.freeSlotsAll, qk.tasksAll],
    successMessage: copy.planReady,
  });

  const isToday = isSameDay(day, startOfDay(new Date()));

  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [showAllAttendees, setShowAllAttendees] = useState(false);
  const [contactAction, setContactAction] = useState<ContactAction | null>(null);
  const [noteEditing, setNoteEditing] = useState(false);
  const [noteExpanded, setNoteExpanded] = useState(false);
  const [noteDraft, setNoteDraft] = useState('');
  const [noteError, setNoteError] = useState<string | null>(null);
  const dayStart = useMemo(() => startOfDay(day), [day]);
  const events = eventsQuery.data?.items ?? [];
  const hasVisibleEvents = events.some((e) => e.status !== 'cancelled');
  const syncState = eventsQuery.data?.sync;

  useEffect(() => {
    setNoteEditing(false);
    setNoteExpanded(false);
    setNoteDraft(selectedEvent?.private_note ?? '');
    setNoteError(null);
  }, [selectedEvent?.id, selectedEvent?.private_note]);

  const openContactAction = (person: CalendarPerson | CalendarAttendee, anchor: DOMRect) => {
    if (!person.email) return;
    haptic('light');
    setContactAction({ person, anchor });
  };

  const copyContactEmail = (email: string) => {
    void copyText(email)
      .then(() => {
        haptic('success');
        show(copy.copied, 'success');
        setContactAction(null);
      })
      .catch(() => show(copy.copyFailed, 'error'));
  };

  const closeEventSheet = () => {
    setShowAllAttendees(false);
    setContactAction(null);
    setSelectedEvent(null);
  };

  const savePrivateNote = () => {
    if (!selectedEvent) return;
    if (noteDraft.length > PRIVATE_NOTE_MAX_CHARS) {
      setNoteError(copy.noteMaxError);
      return;
    }
    const note = noteDraft.trim();
    setNoteError(null);
    if (!note) {
      if (!selectedEvent.private_note) {
        setNoteEditing(false);
        return;
      }
      deletePrivateNote.mutate(selectedEvent.id, {
        onSuccess: ({ event }) => {
          haptic('success');
          show(copy.noteDeleted, 'success');
          setSelectedEvent(event);
          setNoteEditing(false);
        },
        onError: () => show(copy.noteDeleteFailed, 'error'),
      });
      return;
    }
    updatePrivateNote.mutate(
      { id: selectedEvent.id, input: { note } },
      {
        onSuccess: ({ event }) => {
          haptic('success');
          show(copy.noteSaved, 'success');
          setSelectedEvent(event);
          setNoteEditing(false);
          setNoteExpanded(false);
        },
        onError: () => show(copy.noteSaveFailed, 'error'),
      },
    );
  };

  const removePrivateNote = () => {
    if (!selectedEvent?.private_note) return;
    deletePrivateNote.mutate(selectedEvent.id, {
      onSuccess: ({ event }) => {
        haptic('success');
        show(copy.noteDeleted, 'success');
        setSelectedEvent(event);
        setNoteEditing(false);
      },
      onError: () => show(copy.noteDeleteFailed, 'error'),
    });
  };

  return (
    <Stagger>
      {/* Day switcher */}
      <Rise>
        <div className="card card-strong flex items-center justify-between px-2 py-1.5">
          <button
            type="button"
            aria-label={copy.prevDay}
            onClick={() => {
              haptic('light');
              setDay((d) => addDays(d, -1));
            }}
            className="flex h-11 w-11 items-center justify-center rounded-full text-hint"
          >
            <ChevronLeft size={20} />
          </button>
          <div className="text-center">
            <p className="tnum text-[15px] font-semibold text-ink">{formatDayLabel(day, timeDisplay)}</p>
            {!isToday && (
              <button
                type="button"
                onClick={() => setDay(startOfDay(new Date()))}
                className="relative text-[12px] font-medium text-accent-text after:absolute after:-inset-1.5 after:content-['']"
              >
                {copy.backToday}
              </button>
            )}
          </div>
          <button
            type="button"
            aria-label={copy.nextDay}
            onClick={() => {
              haptic('light');
              setDay((d) => addDays(d, 1));
            }}
            className="flex h-11 w-11 items-center justify-center rounded-full text-hint"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      </Rise>

      {/* Actions */}
      <Rise>
        <div className="mt-3 flex flex-wrap gap-2.5">
          <Button
            variant="secondary"
            icon={<RefreshCw size={15} />}
            busy={syncAction.isRunning}
            onClick={syncAction.trigger}
          >
            {copy.sync}
          </Button>
          <Button variant="primary" icon={<Sparkles size={15} />} busy={planAction.isRunning} onClick={planAction.trigger}>
            {copy.planDay}
          </Button>
        </div>
        <p className="mt-2 px-1 text-[12px] leading-snug text-hint">
          {syncState?.stale && syncState.refresh_queued
            ? copy.updatingExternal
            : syncState?.last_sync_at
              ? copy.lastSync(formatRelative(syncState.last_sync_at, timeDisplay))
              : copy.externalSyncHint}
        </p>
      </Rise>

      {/* Google-not-connected calm hint */}
      {googleHint && (
        <Rise>
          <div className="card mt-3 px-4 py-3.5">
            <div className="flex items-start gap-3">
              <CloudOff size={18} className="mt-0.5 shrink-0 text-hint" strokeWidth={1.8} />
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-medium text-ink">{copy.googleMissingTitle}</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-hint">
                  {copy.googleMissingHint}
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/settings')}
                  className="relative mt-2 text-[13px] font-medium text-accent-text after:absolute after:-inset-1.5 after:content-['']"
                >
                  {copy.openSettings} →
                </button>
              </div>
              <button
                type="button"
                aria-label={copy.hideHint}
                onClick={() => setGoogleHint(false)}
                className="-m-1.5 shrink-0 p-1.5 text-hint"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        </Rise>
      )}

      {/* Day grid */}
      <Rise className="mt-5">
        {eventsQuery.isPending ? (
          <SkeletonTimeline rows={4} />
        ) : eventsQuery.isError ? (
          <ErrorState message={copy.loadFailed} onRetry={() => void eventsQuery.refetch()} />
        ) : (
          <div className="card card-strong px-4 py-4">
            {!hasVisibleEvents && (
              <div className="mb-3 flex justify-end">
                <div className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-hairline bg-[var(--surface-muted)] px-3 py-1.5 text-[12px] font-medium leading-none text-hint">
                  <CalendarDays size={13} strokeWidth={1.8} className="shrink-0" aria-hidden="true" />
                  <span className="truncate">{copy.noMeetingsScheduled}</span>
                </div>
              </div>
            )}
            <DayGrid
              events={events}
              dayStart={dayStart}
              locale={locale}
              nowLine={isToday}
              onEventTap={(e) => {
                setShowAllAttendees(false);
                setContactAction(null);
                setNoteEditing(false);
                setNoteExpanded(false);
                setSelectedEvent(e);
              }}
              onEmptyTap={(time) => {
                const end = new Date(time.getTime() + 60 * 60000);
                setPrefill({ start: formatTime(time.toISOString()), end: formatTime(end.toISOString()) });
                setSheetOpen(true);
              }}
            />
          </div>
        )}
      </Rise>

      {/* Event details */}
      <Sheet
        open={selectedEvent !== null}
        onClose={closeEventSheet}
        title={selectedEvent?.title ?? ''}
      >
        {selectedEvent && (
          <div className="space-y-4">
            <p className="tnum text-[14px] text-hint">
              {formatTimeRange(selectedEvent.start_at, selectedEvent.end_at, timeDisplay)}
              {selectedEvent.source === 'google' && ' · Google Calendar'}
              {selectedEvent.source === 'yandex' && ` · ${copy.yandexCalendar}`}
              {selectedEvent.status === 'proposed' && ` · ${copy.proposedLumi}`}
            </p>
            {selectedEvent.location && (
              <div className="flex items-start gap-2 text-[14px] leading-relaxed text-ink">
                <MapPin size={16} className="mt-0.5 shrink-0 text-hint" />
                <span className="min-w-0">{selectedEvent.location}</span>
              </div>
            )}
            {(selectedEvent.organizer || selectedEvent.attendee_count > 0) && (
              <div className="space-y-2.5 rounded-xl bg-[var(--secondary-bg)] px-3.5 py-3">
                <div className="flex items-center gap-2 text-[13px] font-medium text-hint">
                  <Users size={15} />
                  <span>{copy.participants}{selectedEvent.attendee_count ? ` · ${selectedEvent.attendee_count}` : ''}</span>
                </div>
                {selectedEvent.organizer && (
                  <ParticipantRow person={selectedEvent.organizer} labels={[copy.organizer]} onContact={openContactAction} locale={locale} />
                )}
                <div className="space-y-1.5">
                  {(showAllAttendees ? selectedEvent.attendees : selectedEvent.attendees.slice(0, 5)).map((attendee) => {
                    const label = responseLabel(attendee.response_status, locale);
                    return (
                      <ParticipantRow
                        key={`${attendee.email ?? attendee.name}-${attendee.response_status ?? ''}`}
                        person={attendee}
                        labels={[label ?? '', attendee.optional ? copy.optional : '', attendee.resource ? copy.resource : '']}
                        onContact={openContactAction}
                        locale={locale}
                      />
                    );
                  })}
                </div>
                {selectedEvent.attendees.length > 5 && (
                  <button
                    type="button"
                    onClick={() => setShowAllAttendees((v) => !v)}
                    className="text-[13px] font-medium text-accent-text"
                  >
                    {showAllAttendees ? copy.hide : copy.showAll(selectedEvent.attendees.length)}
                  </button>
                )}
              </div>
            )}
            {selectedEvent.description && (
              <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{selectedEvent.description}</p>
            )}
            <PrivateNoteSection
              event={selectedEvent}
              editing={noteEditing}
              expanded={noteExpanded}
              draft={noteDraft}
              error={noteError}
              saving={updatePrivateNote.isPending || deletePrivateNote.isPending}
              deleting={deletePrivateNote.isPending}
              onEdit={() => {
                setNoteDraft(selectedEvent.private_note ?? '');
                setNoteError(null);
                setNoteEditing(true);
              }}
              onCancel={() => {
                setNoteDraft(selectedEvent.private_note ?? '');
                setNoteError(null);
                setNoteEditing(false);
              }}
              onDelete={removePrivateNote}
              onDraftChange={setNoteDraft}
              onExpandedChange={setNoteExpanded}
              onSave={savePrivateNote}
            />
            {(selectedEvent.meeting_url || selectedEvent.external_url || visibleLinks(selectedEvent).length > 0) && (
              <div className="flex flex-wrap gap-2.5">
                {selectedEvent.meeting_url && (
                  <Button
                    variant="primary"
                    icon={<Video size={15} />}
                    onClick={() => openExternalLink(selectedEvent.meeting_url!)}
                  >
                    {copy.meeting}
                  </Button>
                )}
                {visibleLinks(selectedEvent).map((link) => (
                  <Button
                    key={link}
                    variant="secondary"
                    icon={<ExternalLink size={15} />}
                    onClick={() => openExternalLink(link)}
                  >
                    {linkLabel(link, locale)}
                  </Button>
                ))}
                {selectedEvent.external_url && selectedEvent.source !== 'internal' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<ExternalLink size={14} />}
                    onClick={() => openExternalLink(selectedEvent.external_url!)}
                  >
                    {copy.openOriginal}
                  </Button>
                )}
              </div>
            )}
            {selectedEvent.source !== 'internal' ? (
              <p className="text-[13px] leading-relaxed text-hint">
                {copy.externalManaged}
              </p>
            ) : (
              <div className="flex gap-2.5">
                {selectedEvent.status === 'proposed' && (
                  <Button
                    busy={confirmBlock.isPending}
                    onClick={() =>
                      confirmBlock.mutate(selectedEvent.id, {
                        onSuccess: () => {
                          show(copy.blockConfirmed, 'success');
                          setSelectedEvent(null);
                        },
                        onError: () => show(copy.confirmFailed, 'error'),
                      })
                    }
                  >
                    {copy.accept}
                  </Button>
                )}
                <Button
                  variant="danger"
                  busy={deleteEvent.isPending}
                  onClick={() =>
                    deleteEvent.mutate(selectedEvent.id, {
                      onSuccess: () => {
                        show(copy.removed, 'success');
                        setSelectedEvent(null);
                      },
                      onError: () => show(copy.removeFailed, 'error'),
                    })
                  }
                >
                  {selectedEvent.status === 'proposed' ? copy.reject : copy.remove}
                </Button>
              </div>
            )}
          </div>
        )}
      </Sheet>

      {/* FAB: new internal block */}
      <motion.button
        type="button"
        aria-label={copy.createBlock}
        whileTap={reduceMotion ? undefined : { scale: 0.92 }}
        transition={{ type: 'spring', stiffness: 420, damping: 22 }}
        onClick={() => {
          haptic('light');
          setPrefill(null);
          setSheetOpen(true);
        }}
        className="shell-fab calendar-fab fixed z-40 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-[var(--accent-foreground)] shadow-[0_8px_24px_var(--accent-shadow)]"
      >
        <Plus size={24} />
      </motion.button>

      <CreateBlockSheet open={sheetOpen} onClose={() => setSheetOpen(false)} day={day} prefill={prefill} locale={locale} />
      <ContactActionSheet
        contact={contactAction}
        onClose={() => setContactAction(null)}
        onCopy={copyContactEmail}
        locale={locale}
      />
    </Stagger>
  );
}
