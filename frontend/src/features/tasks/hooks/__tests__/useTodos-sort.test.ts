import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTodos } from '../useTodos';

describe('useTodos — sortMode & resilience', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('manual mode keeps insertion order; time mode sorts by start', () => {
    const { result } = renderHook(() => useTodos());
    act(() => {
      result.current.addTask('A', { start: '2026-06-15T10:00' });
      result.current.addTask('B', { start: '2026-06-15T08:00' });
    });

    expect(result.current.sortMode).toBe('manual');
    expect(result.current.tasks.map(t => t.text)).toEqual(['B', 'A']);

    act(() => { result.current.setSortMode('time'); });
    expect(result.current.tasks.map(t => t.text)).toEqual(['B', 'A']);

    act(() => { result.current.setSortMode('manual'); });
    expect(result.current.tasks.map(t => t.text)).toEqual(['B', 'A']);
  });

  it('reorder switches sortMode back to manual', () => {
    const { result } = renderHook(() => useTodos());
    act(() => {
      result.current.addTask('A', { start: '2026-06-15T10:00' });
      result.current.addTask('B', { start: '2026-06-15T08:00' });
    });
    act(() => { result.current.setSortMode('time'); });

    const fromId = result.current.tasks[1].id;
    const toId = result.current.tasks[0].id;
    act(() => { result.current.reorderTasks(fromId, toId); });

    expect(result.current.sortMode).toBe('manual');
  });

  it('does not crash when localStorage has malformed JSON', () => {
    localStorage.setItem('todo-tasks', '{not json');
    const { result } = renderHook(() => useTodos());
    expect(result.current.allTasks).toEqual([]);
  });
});
