import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTodos } from '../useTodos';

describe('useTodos', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should initialize with empty tasks', () => {
    const { result } = renderHook(() => useTodos());
    expect(result.current.tasks).toEqual([]);
    expect(result.current.stats.total).toBe(0);
  });

  it('should add a task', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Test task');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Test task');
    expect(result.current.tasks[0].completed).toBe(false);
  });

  it('should not add empty task', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('  ');
    });

    expect(result.current.tasks).toHaveLength(0);
  });

  it('should toggle task completion', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Test task');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.toggleTask(taskId);
    });

    expect(result.current.allTasks[0].completed).toBe(true);
  });

  it('should remove a task', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Test task');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.removeTask(taskId);
    });

    expect(result.current.tasks).toHaveLength(0);
  });

  it('should edit a task', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Original text');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.editTask(taskId, { text: 'Updated text' });
    });

    expect(result.current.tasks[0].text).toBe('Updated text');
  });

  it('should filter by status', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Task 1');
      result.current.addTask('Task 2');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.toggleTask(taskId);
    });

    act(() => {
      result.current.setFilter('completed');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].completed).toBe(true);
  });

  it('should filter by category', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Work task', undefined, 'work');
      result.current.addTask('Study task', undefined, 'study');
    });

    act(() => {
      result.current.setCategoryFilter('work');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].category).toBe('work');
  });

  it('should search tasks', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Learn React');
      result.current.addTask('Buy groceries');
    });

    act(() => {
      result.current.setSearchQuery('React');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Learn React');
  });

  it('should clear completed tasks', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Task 1');
      result.current.addTask('Task 2');
    });

    act(() => {
      result.current.toggleTask(result.current.tasks[0].id);
    });

    act(() => {
      result.current.clearCompleted();
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Task 1');
  });

  it('should persist to localStorage', () => {
    const { result } = renderHook(() => useTodos());

    act(() => {
      result.current.addTask('Persistent task');
    });

    const stored = JSON.parse(localStorage.getItem('todo-tasks') || '[]');
    expect(stored).toHaveLength(1);
    expect(stored[0].text).toBe('Persistent task');
  });

  it('should load from localStorage', () => {
    localStorage.setItem('todo-tasks', JSON.stringify([
      { id: '1', text: 'Loaded task', completed: false, priority: 'low', createdAt: Date.now() }
    ]));

    const { result } = renderHook(() => useTodos());
    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Loaded task');
  });
});
