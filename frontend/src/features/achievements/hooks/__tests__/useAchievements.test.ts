import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AchievementState } from '@/shared/types';
import { useAchievements } from '../useAchievements';

const INITIAL_STATE: AchievementState = {
  unlocked: ['first-task'],
  streakDays: 2,
  lastActiveDate: '2026-07-12',
  todayCompleted: 3,
  todayDate: '2026-07-13',
};

describe('useAchievements', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('initializes progress from the bootstrap snapshot', () => {
    const { result } = renderHook(() => useAchievements(INITIAL_STATE));

    expect(result.current.achievements).toEqual(INITIAL_STATE);
  });

  it('replaces progress with the completion response without recalculating it', () => {
    const serverState: AchievementState = {
      unlocked: ['first-task', 'streak-7'],
      streakDays: 7,
      lastActiveDate: '2026-07-13',
      todayCompleted: 42,
      todayDate: '2026-07-13',
    };
    const { result } = renderHook(() => useAchievements(INITIAL_STATE));

    act(() => result.current.applyCompletion(serverState, []));

    expect(result.current.achievements).toEqual(serverState);
    expect(result.current.toast).toBeNull();
  });

  it('shows feedback only for IDs newly unlocked by the server', () => {
    const playUnlock = vi.fn();
    const serverState = { ...INITIAL_STATE, unlocked: ['first-task', 'streak-7'] };
    const { result } = renderHook(() => useAchievements(INITIAL_STATE, playUnlock));

    act(() => result.current.applyCompletion(serverState, ['streak-7']));

    expect(result.current.toast?.id).toBe('streak-7');
    expect(playUnlock).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(3_000));
    expect(result.current.toast).toBeNull();
  });

  it('ignores unknown server achievement IDs for local presentation', () => {
    const playUnlock = vi.fn();
    const { result } = renderHook(() => useAchievements(INITIAL_STATE, playUnlock));

    act(() => result.current.applyCompletion(INITIAL_STATE, ['future-achievement']));

    expect(result.current.toast).toBeNull();
    expect(playUnlock).not.toHaveBeenCalled();
  });

  it('dismisses the active toast', () => {
    const { result } = renderHook(() => useAchievements(INITIAL_STATE));

    act(() => result.current.applyCompletion(INITIAL_STATE, ['first-task']));
    act(() => result.current.dismissToast());

    expect(result.current.toast).toBeNull();
  });

  it('replaces progress and clears stale feedback on a new bootstrap snapshot', () => {
    const replacement = { ...INITIAL_STATE, todayCompleted: 9 };
    const { result, rerender } = renderHook(
      ({ state }) => useAchievements(state),
      { initialProps: { state: INITIAL_STATE } },
    );
    act(() => result.current.applyCompletion(INITIAL_STATE, ['first-task']));

    rerender({ state: replacement });

    expect(result.current.achievements).toEqual(replacement);
    expect(result.current.toast).toBeNull();
  });
});
