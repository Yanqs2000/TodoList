import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAchievements } from '../useAchievements';

describe('useAchievements', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should initialize with no achievements unlocked', () => {
    const { result } = renderHook(() => useAchievements());
    expect(result.current.achievements.unlocked).toEqual([]);
  });

  it('should unlock first-task achievement', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      result.current.recordCompletion();
    });

    expect(result.current.achievements.unlocked).toContain('first-task');
  });

  it('should show toast on achievement unlock', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      result.current.recordCompletion();
    });

    expect(result.current.toast).not.toBeNull();
    expect(result.current.toast?.id).toBe('first-task');
  });

  it('should dismiss toast', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      result.current.recordCompletion();
    });

    act(() => {
      result.current.dismissToast();
    });

    expect(result.current.toast).toBeNull();
  });

  it('should track today completed count', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      result.current.recordCompletion();
      result.current.recordCompletion();
    });

    expect(result.current.achievements.todayCompleted).toBe(2);
  });

  it('should unlock speed-demon after 10 completions', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      for (let i = 0; i < 10; i++) {
        result.current.recordCompletion();
      }
    });

    expect(result.current.achievements.unlocked).toContain('speed-demon');
  });

  it('should persist achievements to localStorage', () => {
    const { result } = renderHook(() => useAchievements());

    act(() => {
      result.current.recordCompletion();
    });

    const stored = JSON.parse(localStorage.getItem('todo-achievements') || '{}');
    expect(stored.unlocked).toContain('first-task');
  });
});
