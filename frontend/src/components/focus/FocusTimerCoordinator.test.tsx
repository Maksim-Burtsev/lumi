import { act, render } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  focusState: vi.fn(),
  haptic: vi.fn(),
  show: vi.fn(),
}));

vi.mock('../../api/hooks', () => ({
  useFocusState: () => mocks.focusState(),
}));

vi.mock('../../lib/useAppLocale', () => ({
  useAppLocale: () => 'en',
}));

vi.mock('../../telegram/webapp', () => ({
  haptic: mocks.haptic,
}));

vi.mock('../ui/Toast', () => ({
  useToast: () => ({ show: mocks.show }),
}));

import {
  FocusTimerCoordinator,
  isFocusAlarmSilenced,
  prepareFocusAlarm,
  silenceFocusAlarm,
} from './FocusTimerCoordinator';

const oscillatorStart = vi.fn();
const oscillatorStop = vi.fn();
const resume = vi.fn();

class MockAudioContext {
  state: AudioContextState = 'suspended';
  currentTime = 0;
  destination = {} as AudioDestinationNode;

  constructor() {
    resume.mockImplementation(() => {
      this.state = 'running';
      return Promise.resolve();
    });
  }

  resume = resume;
  createOscillator = () => ({
    type: 'sine',
    frequency: { value: 0 },
    connect: vi.fn(),
    start: oscillatorStart,
    stop: oscillatorStop,
  });
  createGain = () => ({
    gain: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
  });
}

function activeState(id: string, targetEndAt: string) {
  return {
    data: {
      active_session: {
        id,
        intention: 'Write launch brief',
        target_end_at: targetEndAt,
      },
    },
  };
}

describe('FocusTimerCoordinator', () => {
  beforeAll(() => {
    vi.stubGlobal('AudioContext', MockAudioContext);
  });

  afterAll(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-12T08:00:00Z'));
    mocks.focusState.mockReset();
    mocks.haptic.mockReset();
    mocks.show.mockReset();
    oscillatorStart.mockReset();
    oscillatorStop.mockReset();
    resume.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a single global warning for an initial state failure and resets after recovery', () => {
    mocks.focusState.mockReturnValue({ data: undefined, isError: true });
    const view = render(<FocusTimerCoordinator />);

    expect(mocks.show).toHaveBeenCalledWith(expect.stringContaining('Could not check'), 'error');
    view.rerender(<FocusTimerCoordinator />);
    expect(mocks.show).toHaveBeenCalledTimes(1);

    mocks.focusState.mockReturnValue({ data: { active_session: null }, isError: false });
    view.rerender(<FocusTimerCoordinator />);
    mocks.focusState.mockReturnValue({ data: undefined, isError: true });
    view.rerender(<FocusTimerCoordinator />);

    expect(mocks.show).toHaveBeenCalledTimes(2);
  });

  it('keeps the prepared alarm active across route-content changes', async () => {
    prepareFocusAlarm();
    expect(resume).toHaveBeenCalledOnce();
    mocks.focusState.mockReturnValue(activeState('focus-route', '2026-07-12T08:00:05Z'));

    function Harness({ route }: { route: string }) {
      return (
        <>
          <FocusTimerCoordinator />
          <span>{route}</span>
        </>
      );
    }

    const view = render(<Harness route="sessions" />);
    view.rerender(<Harness route="tasks" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(mocks.haptic).toHaveBeenCalledWith('success');
    expect(mocks.show).toHaveBeenCalledWith(expect.stringContaining('time is up'), 'info');
    expect(oscillatorStart).toHaveBeenCalledTimes(2);
  });

  it('persists silence by session id and suppresses every alarm channel', async () => {
    silenceFocusAlarm('focus-silent');
    expect(isFocusAlarmSilenced('focus-silent')).toBe(true);
    expect(sessionStorage.getItem('lumi-focus-alarm-silenced:focus-silent')).toBe('1');
    mocks.focusState.mockReturnValue(activeState('focus-silent', '2026-07-12T08:00:01Z'));

    render(<FocusTimerCoordinator />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });

    expect(mocks.haptic).not.toHaveBeenCalled();
    expect(mocks.show).not.toHaveBeenCalled();
    expect(oscillatorStart).not.toHaveBeenCalled();
  });
});
