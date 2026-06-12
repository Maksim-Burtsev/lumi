import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CloudOff,
  ExternalLink,
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
  useDeleteEvent,
} from '../api/hooks';
import type { CalendarEvent } from '../api/types';
import { DayGrid } from '../components/calendar/DayGrid';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Sheet } from '../components/ui/Sheet';
import { FieldLabel, Input, Textarea } from '../components/ui/Field';
import { SkeletonTimeline } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { addDays, formatDateParam, formatDayLabel, formatRelative, formatTime, formatTimeRange, isSameDay, startOfDay } from '../lib/format';
import { haptic, openExternalLink } from '../telegram/webapp';

interface SheetPrefill {
  start: string; // "HH:MM"
  end: string;
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
  const [location, setLocation] = useState('');
  const [linksText, setLinksText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createEvent = useCreateEvent();
  const { show } = useToast();

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
    setError(null);
    createEvent.mutate(
      {
        title: trimmed,
        start_at: startDate.toISOString(),
        end_at: endDate.toISOString(),
        ...(description.trim() ? { description: description.trim() } : {}),
        ...(location.trim() ? { location: location.trim() } : {}),
        ...(parseLinks(linksText).length ? { links: parseLinks(linksText) } : {}),
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
      <p className="mb-4 text-[13px] text-hint">{formatDayLabel(day)} · внутренний календарь Lumi</p>
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

  const rangeStart = day.toISOString();
  const rangeEnd = addDays(day, 1).toISOString();
  const eventsQuery = useCalendarEvents(rangeStart, rangeEnd);
  const confirmBlock = useConfirmBlock();
  const deleteEvent = useDeleteEvent();

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
  const dayStart = useMemo(() => startOfDay(day), [day]);
  const events = eventsQuery.data?.items ?? [];
  const syncState = eventsQuery.data?.sync;

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
            <p className="tnum text-[15px] font-semibold text-ink">{formatDayLabel(day)}</p>
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
              ? `Последний sync: ${formatRelative(syncState.last_sync_at)}.`
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
              onEventTap={(e) => setSelectedEvent(e)}
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
      <Sheet open={selectedEvent !== null} onClose={() => setSelectedEvent(null)} title={selectedEvent?.title ?? ''}>
        {selectedEvent && (
          <div className="space-y-4">
            <p className="tnum text-[14px] text-hint">
              {formatTimeRange(selectedEvent.start_at, selectedEvent.end_at)}
              {selectedEvent.source === 'google' && ' · Google Calendar'}
              {selectedEvent.source === 'yandex' && ' · Яндекс.Календарь'}
              {selectedEvent.status === 'proposed' && ' · предложение Lumi'}
            </p>
            {selectedEvent.last_synced_at && selectedEvent.source !== 'internal' && (
              <p className="text-[12.5px] text-hint">Обновлено {formatRelative(selectedEvent.last_synced_at)}</p>
            )}
            {selectedEvent.location && (
              <div className="flex items-start gap-2 text-[14px] leading-relaxed text-ink">
                <MapPin size={16} className="mt-0.5 shrink-0 text-hint" />
                <span className="min-w-0">{selectedEvent.location}</span>
              </div>
            )}
            {selectedEvent.description && (
              <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{selectedEvent.description}</p>
            )}
            {(selectedEvent.meeting_url || selectedEvent.external_url || selectedEvent.links.length > 0) && (
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
                {selectedEvent.external_url && (
                  <Button
                    variant="secondary"
                    icon={<ExternalLink size={15} />}
                    onClick={() => openExternalLink(selectedEvent.external_url!)}
                  >
                    В календаре
                  </Button>
                )}
                {selectedEvent.links.map((link) => (
                  <Button
                    key={link}
                    variant="secondary"
                    icon={<ExternalLink size={15} />}
                    onClick={() => openExternalLink(link)}
                  >
                    {linkLabel(link)}
                  </Button>
                ))}
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
    </Stagger>
  );
}
