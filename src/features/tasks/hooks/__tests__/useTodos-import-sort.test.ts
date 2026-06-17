import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTodos } from '../useTodos';

describe('useTodos — import validation & sortMode', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('import drops invalid tasks and counts skipped', async () => {
    const { result } = renderHook(() => useTodos());
    const payload = {
      tasks: [
        { id: 'good-1', text: 'valid', completed: false, priority: 'low', createdAt: 1 },
        { id: 'bad-1', text: 'invalid', completed: 'yes', priority: 'low', createdAt: 1 },
        { id: 'bad-2', text: 'no priority', completed: false, createdAt: 1 },
        null,
      ],
    };
    const file = new File([JSON.stringify(payload)], 'backup.json', { type: 'application/json' });

    let outcome: { added: number; skipped: number } | null = null;
    await act(async () => {
      outcome = await result.current.importTasks(file);
    });

    expect(outcome).toEqual({ added: 1, skipped: 3 });
    expect(result.current.allTasks).toHaveLength(1);
    expect(result.current.allTasks[0].id).toBe('good-1');
  });

  it('import rejects non-array tasks', async () => {
    const { result } = renderHook(() => useTodos());
    const file = new File([JSON.stringify({ tasks: 'nope' })], 'bad.json', { type: 'application/json' });

    await expect(act(async () => {
      await result.current.importTasks(file);
    })).rejects.toThrow();
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
