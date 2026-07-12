import { useEffect, useRef } from 'react';
import { useFocusState } from '../../api/hooks';
import { useAppLocale } from '../../lib/useAppLocale';
import { haptic } from '../../telegram/webapp';
import { useToast } from '../ui/Toast';

const ALARM_SILENCE_PREFIX = 'lumi-focus-alarm-silenced:';
const ALARM_STATE_EVENT = 'lumi-focus-alarm-state';
const ALARM_REPEAT_MS = 1_800;
const MAX_TIMEOUT_MS = 2_147_000_000;

const STATE_ERROR_COPY = {
  en: 'Could not check the active focus timer. Reopen Sessions or check your connection.',
  ru: 'Не удалось проверить активный фокус-таймер. Откройте Сессии или проверьте соединение.',
};

const memorySilencedSessions = new Set<string>();
let preparedAudioContext: AudioContext | null = null;

function audioContextConstructor(): typeof AudioContext | undefined {
  return window.AudioContext
    ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

/** Call synchronously from the user gesture that starts a focus session. */
export function prepareFocusAlarm(): void {
  try {
    if (!preparedAudioContext || preparedAudioContext.state === 'closed') {
      const AudioContextClass = audioContextConstructor();
      if (!AudioContextClass) return;
      preparedAudioContext = new AudioContextClass();
    }
    if (preparedAudioContext.state === 'suspended') {
      void preparedAudioContext.resume().catch(() => undefined);
    }
  } catch {
    preparedAudioContext = null;
  }
}

export function isFocusAlarmSilenced(sessionId: string): boolean {
  if (memorySilencedSessions.has(sessionId)) return true;
  try {
    return sessionStorage.getItem(`${ALARM_SILENCE_PREFIX}${sessionId}`) === '1';
  } catch {
    return false;
  }
}

export function silenceFocusAlarm(sessionId: string): void {
  memorySilencedSessions.add(sessionId);
  try {
    sessionStorage.setItem(`${ALARM_SILENCE_PREFIX}${sessionId}`, '1');
  } catch {
    /* Some embedded browsers may reject storage writes. */
  }
  window.dispatchEvent(new CustomEvent(ALARM_STATE_EVENT, { detail: { sessionId } }));
}

function playPreparedFocusAlarm(): void {
  const context = preparedAudioContext;
  if (!context || context.state !== 'running') return;

  try {
    const startAt = context.currentTime;
    for (const [index, frequency] of [720, 880].entries()) {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const noteAt = startAt + index * 0.16;
      oscillator.type = 'sine';
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, noteAt);
      gain.gain.exponentialRampToValueAtTime(0.075, noteAt + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.0001, noteAt + 0.22);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(noteAt);
      oscillator.stop(noteAt + 0.24);
    }
  } catch {
    /* Alarm remains visible and haptic when WebAudio is unavailable. */
  }
}

/** Keeps the active-session alarm alive while the user navigates around the Mini App. */
export function FocusTimerCoordinator() {
  const focusState = useFocusState();
  const locale = useAppLocale();
  const { show } = useToast();
  const notifiedSessionsRef = useRef(new Set<string>());
  const stateErrorNotifiedRef = useRef(false);
  const session = focusState.data?.active_session ?? null;
  const sessionId = session?.id ?? null;
  const targetEndAt = session?.target_end_at ?? null;
  const intention = session?.intention ?? '';

  useEffect(() => {
    if (!focusState.isError) {
      stateErrorNotifiedRef.current = false;
      return;
    }
    if (focusState.data || stateErrorNotifiedRef.current) return;
    stateErrorNotifiedRef.current = true;
    show(STATE_ERROR_COPY[locale], 'error');
  }, [focusState.data, focusState.isError, locale, show]);

  useEffect(() => {
    if (!sessionId || !targetEndAt) return undefined;
    const targetAt = new Date(targetEndAt).getTime();
    if (!Number.isFinite(targetAt)) return undefined;

    let dueTimer: number | null = null;
    let alarmTimer: number | null = null;
    let alarmStarted = false;

    const stopAlarm = () => {
      if (alarmTimer !== null) window.clearInterval(alarmTimer);
      alarmTimer = null;
      alarmStarted = false;
    };

    const ring = () => {
      if (isFocusAlarmSilenced(sessionId)) {
        stopAlarm();
        return;
      }
      playPreparedFocusAlarm();
    };

    const startAlarm = () => {
      if (alarmStarted || isFocusAlarmSilenced(sessionId)) return;
      alarmStarted = true;
      if (!notifiedSessionsRef.current.has(sessionId)) {
        notifiedSessionsRef.current.add(sessionId);
        haptic('success');
        show(
          locale === 'ru'
            ? `«${intention}»: время вышло — завершите сессию или продолжайте считать.`
            : `“${intention}”: time is up — finish the session or keep counting.`,
          'info',
        );
      }
      ring();
      alarmTimer = window.setInterval(ring, ALARM_REPEAT_MS);
    };

    const scheduleAlarm = () => {
      const remaining = targetAt - Date.now();
      if (remaining <= 0) {
        startAlarm();
        return;
      }
      dueTimer = window.setTimeout(scheduleAlarm, Math.min(remaining, MAX_TIMEOUT_MS));
    };

    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && Date.now() >= targetAt) startAlarm();
    };

    const handleAlarmState = (event: Event) => {
      const detail = (event as CustomEvent<{ sessionId?: string }>).detail;
      if (detail?.sessionId === sessionId) stopAlarm();
    };

    scheduleAlarm();
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener(ALARM_STATE_EVENT, handleAlarmState);
    return () => {
      if (dueTimer !== null) window.clearTimeout(dueTimer);
      stopAlarm();
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener(ALARM_STATE_EVENT, handleAlarmState);
    };
  }, [intention, locale, sessionId, show, targetEndAt]);

  return null;
}
