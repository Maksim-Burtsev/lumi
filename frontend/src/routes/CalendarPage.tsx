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
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Sheet } from '../components/ui/Sheet';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SkeletonTimeline } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { addDays, formatDateParam, formatDayLabel, formatRelative, formatTime, formatTimeRange, isSameDay, startOfDay } from '../lib/format';
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

function linkLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'Ссылка';
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

function personLabel(person: { name?: string; email?: string }): string {
  return person.name || person.email || 'Участник';
}

function responseLabel(status?: string | null): string | null {
  if (status === 'declined') return 'отказался';
  if (status === 'tentative') return 'возможно';
  if (status === 'needsAction') return 'ждёт ответа';
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
}: {
  contact: ContactAction | null;
  onClose: () => void;
  onCopy: (email: string) => void;
}) {
  const reduceMotion = useReducedMotion();
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
        Скопировать email
      </button>
    </>
  );

  const content = (
    <div className="fixed inset-0 z-[90]">
      <button type="button" aria-label="Закрыть контакт" className="absolute inset-0 cursor-default" onClick={onClose} />
      <motion.div
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="absolute inset-x-3 bottom-[calc(env(safe-area-inset-bottom)+14px)] overflow-hidden rounded-[22px] border border-hairline bg-[var(--surface-strong)] shadow-card sm:hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Контакт участника"
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
        aria-label="Контакт участника"
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
}: {
  person: CalendarPerson | CalendarAttendee;
  labels: string[];
  onContact: (person: CalendarPerson | CalendarAttendee, anchor: DOMRect) => void;
}) {
  const label = personLabel(person);
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
      aria-label={`Открыть контакт: ${label}`}
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
}: {
  open: boolean;
  onClose: () => void;
  day: Date;
  prefill: SheetPrefill | null;
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

  // Re-seed fields each time the sheet opens (keyed remount from parent)
  const [seeded, setSeeded] = useState(false);
  if (open && !seeded) {
    setSeeded(true);
    if (prefill) {
      setStart(prefill.start);
      setEnd(prefill.end);
      setTitle('Фокус-блок');
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
      setError('Назови блок — например, «Архитектура Lumi»');
      return;
    }
    const startDate = combine(day, start);
    const endDate = combine(day, end);
    if (!startDate || !endDate || endDate.getTime() <= startDate.getTime()) {
      setError('Время окончания должно быть позже начала');
      return;
    }
    if (privateNote.length > PRIVATE_NOTE_MAX_CHARS) {
      setError(`Личная заметка — до ${PRIVATE_NOTE_MAX_CHARS} символов`);
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
          show('Блок создан', 'success');
          onClose();
        },
        onError: () => show('Не удалось создать блок', 'error'),
      },
    );
  };

  return (
    <Sheet open={open} onClose={onClose} title="Новый блок">
      <p className="mb-4 text-[13px] text-hint">{formatDayLabel(day, timeDisplay)} · внутренний календарь Lumi</p>
      <label className="block">
        <FieldLabel>Название</FieldLabel>
        <Input value={title} onChange={setTitle} placeholder="Фокус: архитектура Lumi" />
      </label>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <FieldLabel>Начало</FieldLabel>
          <Input type="time" value={start} onChange={setStart} />
        </label>
        <label className="block">
          <FieldLabel>Конец</FieldLabel>
          <Input type="time" value={end} onChange={setEnd} />
        </label>
      </div>
      <label className="mt-4 block">
        <FieldLabel>Описание (необязательно)</FieldLabel>
        <Textarea value={description} onChange={setDescription} rows={2} placeholder="Что нужно сделать в этом блоке" />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Личная заметка (необязательно)</FieldLabel>
        <Textarea value={privateNote} onChange={setPrivateNote} rows={3} placeholder="Контекст только для себя" />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Место (необязательно)</FieldLabel>
        <Input value={location} onChange={setLocation} placeholder="Офис, Zoom, дом" />
      </label>
      <label className="mt-4 block">
        <FieldLabel>Ссылки (необязательно)</FieldLabel>
        <Textarea value={linksText} onChange={setLinksText} rows={2} placeholder="https://..." />
      </label>
      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
      <Button fullWidth className="mt-5" busy={createEvent.isPending} onClick={submit}>
        Создать блок
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
    successMessage: 'Календарь синхронизирован',
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
    successMessage: 'План готов',
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
        show('Скопировано', 'success');
        setContactAction(null);
      })
      .catch(() => show('Не удалось скопировать', 'error'));
  };

  const closeEventSheet = () => {
    setShowAllAttendees(false);
    setContactAction(null);
    setSelectedEvent(null);
  };

  const savePrivateNote = () => {
    if (!selectedEvent) return;
    if (noteDraft.length > PRIVATE_NOTE_MAX_CHARS) {
      setNoteError(`Личная заметка — до ${PRIVATE_NOTE_MAX_CHARS} символов`);
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
          show('Заметка удалена', 'success');
          setSelectedEvent(event);
          setNoteEditing(false);
        },
        onError: () => show('Не удалось удалить заметку', 'error'),
      });
      return;
    }
    updatePrivateNote.mutate(
      { id: selectedEvent.id, input: { note } },
      {
        onSuccess: ({ event }) => {
          haptic('success');
          show('Заметка сохранена', 'success');
          setSelectedEvent(event);
          setNoteEditing(false);
          setNoteExpanded(false);
        },
        onError: () => show('Не удалось сохранить заметку', 'error'),
      },
    );
  };

  const removePrivateNote = () => {
    if (!selectedEvent?.private_note) return;
    deletePrivateNote.mutate(selectedEvent.id, {
      onSuccess: ({ event }) => {
        haptic('success');
        show('Заметка удалена', 'success');
        setSelectedEvent(event);
        setNoteEditing(false);
      },
      onError: () => show('Не удалось удалить заметку', 'error'),
    });
  };

  return (
    <Stagger>
      {/* Day switcher */}
      <Rise>
        <div className="card card-strong flex items-center justify-between px-2 py-1.5">
          <button
            type="button"
            aria-label="Предыдущий день"
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
                Вернуться к сегодня
              </button>
            )}
          </div>
          <button
            type="button"
            aria-label="Следующий день"
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
            Синхронизировать
          </Button>
          <Button variant="primary" icon={<Sparkles size={15} />} busy={planAction.isRunning} onClick={planAction.trigger}>
            Спланировать день
          </Button>
        </div>
        <p className="mt-2 px-1 text-[12px] leading-snug text-hint">
          {syncState?.stale && syncState.refresh_queued
            ? 'Календарь обновляется из внешнего источника.'
            : syncState?.last_sync_at
              ? `Последний sync: ${formatRelative(syncState.last_sync_at, timeDisplay)}.`
              : 'Внешний календарь обновится после подключения или ручного sync.'}
        </p>
      </Rise>

      {/* Google-not-connected calm hint */}
      {googleHint && (
        <Rise>
          <div className="card mt-3 px-4 py-3.5">
            <div className="flex items-start gap-3">
              <CloudOff size={18} className="mt-0.5 shrink-0 text-hint" strokeWidth={1.8} />
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-medium text-ink">Google Calendar не подключен</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-hint">
                  Lumi уже ведёт внутренний календарь. После подключения Google он будет учитывать и рабочие встречи.
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/settings')}
                  className="relative mt-2 text-[13px] font-medium text-accent-text after:absolute after:-inset-1.5 after:content-['']"
                >
                  Открыть настройки →
                </button>
              </div>
              <button
                type="button"
                aria-label="Скрыть подсказку"
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
          <ErrorState message="Не удалось загрузить календарь." onRetry={() => void eventsQuery.refetch()} />
        ) : events.filter((e) => e.status !== 'cancelled').length === 0 ? (
          <EmptyState
            icon={CalendarDays}
            title="День свободен"
            hint="Тапни по сетке, чтобы создать блок, или нажми «Спланировать день» — Lumi разложит твои задачи по свободным окнам."
          />
        ) : (
          <div className="card card-strong px-4 py-4">
            <DayGrid
              events={events}
              dayStart={dayStart}
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
              {selectedEvent.source === 'yandex' && ' · Яндекс.Календарь'}
              {selectedEvent.status === 'proposed' && ' · предложение Lumi'}
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
                  <span>Участники{selectedEvent.attendee_count ? ` · ${selectedEvent.attendee_count}` : ''}</span>
                </div>
                {selectedEvent.organizer && (
                  <ParticipantRow person={selectedEvent.organizer} labels={['организатор']} onContact={openContactAction} />
                )}
                <div className="space-y-1.5">
                  {(showAllAttendees ? selectedEvent.attendees : selectedEvent.attendees.slice(0, 5)).map((attendee) => {
                    const label = responseLabel(attendee.response_status);
                    return (
                      <ParticipantRow
                        key={`${attendee.email ?? attendee.name}-${attendee.response_status ?? ''}`}
                        person={attendee}
                        labels={[label ?? '', attendee.optional ? 'опц.' : '', attendee.resource ? 'ресурс' : '']}
                        onContact={openContactAction}
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
                    {showAllAttendees ? 'Скрыть' : `Показать всех (${selectedEvent.attendees.length})`}
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
                    Встреча
                  </Button>
                )}
                {visibleLinks(selectedEvent).map((link) => (
                  <Button
                    key={link}
                    variant="secondary"
                    icon={<ExternalLink size={15} />}
                    onClick={() => openExternalLink(link)}
                  >
                    {linkLabel(link)}
                  </Button>
                ))}
                {selectedEvent.external_url && selectedEvent.source !== 'internal' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<ExternalLink size={14} />}
                    onClick={() => openExternalLink(selectedEvent.external_url!)}
                  >
                    Открыть оригинал
                  </Button>
                )}
              </div>
            )}
            {selectedEvent.source !== 'internal' ? (
              <p className="text-[13px] leading-relaxed text-hint">
                Событие из внешнего календаря — управляется там, Lumi его только читает.
              </p>
            ) : (
              <div className="flex gap-2.5">
                {selectedEvent.status === 'proposed' && (
                  <Button
                    busy={confirmBlock.isPending}
                    onClick={() =>
                      confirmBlock.mutate(selectedEvent.id, {
                        onSuccess: () => {
                          show('Блок подтверждён', 'success');
                          setSelectedEvent(null);
                        },
                        onError: () => show('Не удалось подтвердить', 'error'),
                      })
                    }
                  >
                    Принять
                  </Button>
                )}
                <Button
                  variant="danger"
                  busy={deleteEvent.isPending}
                  onClick={() =>
                    deleteEvent.mutate(selectedEvent.id, {
                      onSuccess: () => {
                        show('Убрано из расписания', 'success');
                        setSelectedEvent(null);
                      },
                      onError: () => show('Не удалось убрать', 'error'),
                    })
                  }
                >
                  {selectedEvent.status === 'proposed' ? 'Отклонить' : 'Убрать'}
                </Button>
              </div>
            )}
          </div>
        )}
      </Sheet>

      {/* FAB: new internal block */}
      <motion.button
        type="button"
        aria-label="Создать блок"
        whileTap={reduceMotion ? undefined : { scale: 0.92 }}
        transition={{ type: 'spring', stiffness: 420, damping: 22 }}
        onClick={() => {
          haptic('light');
          setPrefill(null);
          setSheetOpen(true);
        }}
        className="fixed right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-white shadow-[0_8px_24px_rgba(46,99,231,0.4)]"
        style={{ bottom: 'calc(env(safe-area-inset-bottom) + 92px)' }}
      >
        <Plus size={24} />
      </motion.button>

      <CreateBlockSheet open={sheetOpen} onClose={() => setSheetOpen(false)} day={day} prefill={prefill} />
      <ContactActionSheet
        contact={contactAction}
        onClose={() => setContactAction(null)}
        onCopy={copyContactEmail}
      />
    </Stagger>
  );
}
