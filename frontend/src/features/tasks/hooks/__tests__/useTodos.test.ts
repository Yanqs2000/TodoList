import { act, renderHook } from '@testing-library/react';
import { createElement, StrictMode, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  InfrastructureError,
  type CompletionResult,
  type TodoApi,
} from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import { useTodos } from '../useTodos';

function task(overrides: Partial<Todo> = {}): Todo {
  return {
    id: 'task-1',
    text: 'Initial task',
    completed: false,
    priority: 'low',
    createdAt: 1,
    category: 'other',
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function fakeApi(overrides: Partial<TodoApi> = {}): TodoApi {
  return {
    bootstrap: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    deleteTask: vi.fn(),
    replaceTaskOrder: vi.fn(),
    setTaskCompletion: vi.fn(),
    claimReminder: vi.fn(),
    updateSettings: vi.fn(),
    ...overrides,
  };
}

function strictMode({ children }: { children: ReactNode }) {
  return createElement(StrictMode, null, children);
}

describe('useTodos database-first mutations', () => {
  it('uses the bootstrap snapshot and keeps UI-only filters local', () => {
    const api = fakeApi();
    const initial = [
      task({ id: 'work', text: 'Learn React', category: 'work' }),
      task({ id: 'life', text: 'Buy groceries', category: 'life' }),
    ];
    const { result } = renderHook(() => useTodos(initial, api, vi.fn()));

    expect(result.current.allTasks).toEqual(initial);
    act(() => {
      result.current.setCategoryFilter('work');
      result.current.setSearchQuery('react');
    });
    expect(result.current.tasks.map(item => item.id)).toEqual(['work']);
    expect(api.updateTask).not.toHaveBeenCalled();
  });

  it('does not add a task until the backend returns its authoritative task', async () => {
    const pending = deferred<Todo>();
    const created = task({ id: 'server-id', text: 'Created by server', createdAt: 99 });
    const api = fakeApi({ createTask: vi.fn(() => pending.promise) });
    const { result } = renderHook(() => useTodos([], api, vi.fn()));

    let request!: Promise<Todo | undefined>;
    act(() => {
      request = result.current.addTask('  Created by server  ');
    });

    expect(result.current.allTasks).toEqual([]);
    expect(result.current.pending.create).toBe(true);
    expect(api.createTask).toHaveBeenCalledWith({
      text: 'Created by server',
      priority: 'low',
      category: 'other',
    });

    await act(async () => {
      pending.resolve(created);
      await request;
    });

    expect(result.current.allTasks).toEqual([created]);
    expect(result.current.pending.create).toBe(false);
    expect(localStorage.getItem('todo-tasks')).toBeNull();
  });

  it('ignores empty creates without calling the backend', async () => {
    const api = fakeApi();
    const { result } = renderHook(() => useTodos([], api, vi.fn()));

    await act(async () => {
      await result.current.addTask('  ');
    });

    expect(api.createTask).not.toHaveBeenCalled();
    expect(result.current.allTasks).toEqual([]);
  });

  it('keeps the task unchanged until an edit succeeds', async () => {
    const pending = deferred<Todo>();
    const original = task();
    const updated = task({ text: 'Updated task' });
    const api = fakeApi({ updateTask: vi.fn(() => pending.promise) });
    const { result } = renderHook(() => useTodos([original], api, vi.fn()));

    let request!: Promise<boolean>;
    act(() => {
      request = result.current.editTask(original.id, { text: updated.text });
    });

    expect(result.current.allTasks).toEqual([original]);
    expect(result.current.pending.taskMutations.get(original.id)?.has('edit')).toBe(true);

    await act(async () => {
      pending.resolve(updated);
      await request;
    });

    expect(result.current.allTasks).toEqual([updated]);
  });

  it('keeps state and exposes feedback for a business failure', async () => {
    const original = task();
    const api = fakeApi({
      updateTask: vi.fn().mockRejectedValue(
        new ApiError('business', 'INVALID_TASK', '任务内容无效', 422),
      ),
    });
    const onInfrastructureError = vi.fn();
    const { result } = renderHook(() => useTodos([original], api, onInfrastructureError));

    await act(async () => {
      await result.current.editTask(original.id, { text: 'Rejected' });
    });

    expect(result.current.allTasks).toEqual([original]);
    expect(result.current.businessError).toBe('INVALID_TASK');
    expect(onInfrastructureError).not.toHaveBeenCalled();
  });

  it('reports infrastructure failures without changing state', async () => {
    const original = task();
    const failure = new InfrastructureError('network', 'NETWORK_ERROR', 'offline');
    const api = fakeApi({ deleteTask: vi.fn().mockRejectedValue(failure) });
    const onInfrastructureError = vi.fn();
    const { result } = renderHook(() => useTodos([original], api, onInfrastructureError));

    await act(async () => {
      await result.current.removeTask(original.id);
    });

    expect(result.current.allTasks).toEqual([original]);
    expect(onInfrastructureError).toHaveBeenCalledWith(failure);
  });

  it('updates completion only after the completion transaction succeeds', async () => {
    const pending = deferred<CompletionResult>();
    const original = task();
    const completed = task({ completed: true });
    const response: CompletionResult = {
      task: completed,
      achievementState: {
        unlocked: [],
        streakDays: 1,
        lastActiveDate: '2026-07-13',
        todayCompleted: 1,
        todayDate: '2026-07-13',
      },
      newlyUnlocked: [],
    };
    const api = fakeApi({ setTaskCompletion: vi.fn(() => pending.promise) });
    const { result } = renderHook(() => useTodos([original], api, vi.fn()));

    let request!: Promise<CompletionResult | undefined>;
    act(() => {
      request = result.current.toggleTask(original.id);
    });
    expect(result.current.allTasks[0].completed).toBe(false);

    await act(async () => {
      pending.resolve(response);
      await request;
    });

    expect(api.setTaskCompletion).toHaveBeenCalledWith(original.id, {
      completed: true,
      localDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    });
    expect(result.current.allTasks).toEqual([completed]);
  });

  it('deletes only after backend success', async () => {
    const pending = deferred<void>();
    const original = task();
    const api = fakeApi({ deleteTask: vi.fn(() => pending.promise) });
    const { result } = renderHook(() => useTodos([original], api, vi.fn()));

    let request!: Promise<boolean>;
    act(() => {
      request = result.current.removeTask(original.id);
    });
    expect(result.current.allTasks).toEqual([original]);

    await act(async () => {
      pending.resolve();
      await request;
    });
    expect(result.current.allTasks).toEqual([]);
  });

  it('persists server ordering before replacing local state', async () => {
    const pending = deferred<Todo[]>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const api = fakeApi({ replaceTaskOrder: vi.fn(() => pending.promise) });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let request!: Promise<boolean>;
    act(() => {
      request = result.current.reorderTasks(first.id, second.id);
    });
    expect(result.current.allTasks.map(item => item.id)).toEqual(['first', 'second']);

    await act(async () => {
      pending.resolve([second, first]);
      await request;
    });
    expect(api.replaceTaskOrder).toHaveBeenCalledWith(['second', 'first']);
    expect(result.current.allTasks.map(item => item.id)).toEqual(['second', 'first']);
    expect(result.current.sortMode).toBe('manual');
  });

  it('prevents a second mutation for the same task while one is pending', async () => {
    const pending = deferred<Todo>();
    const original = task();
    const updateTask = vi.fn(() => pending.promise);
    const api = fakeApi({ updateTask });
    const { result } = renderHook(() => useTodos([original], api, vi.fn()));

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.editTask(original.id, { text: 'First edit' });
      second = result.current.editTask(original.id, { text: 'Stale edit' });
    });

    await expect(second).resolves.toBe(false);
    expect(updateTask).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(task({ text: 'First edit' }));
      await first;
    });
    expect(result.current.allTasks[0].text).toBe('First edit');
  });

  it('does not let a pending create and reorder overwrite each other', async () => {
    const create = deferred<Todo>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const replaceTaskOrder = vi.fn();
    const api = fakeApi({
      createTask: vi.fn(() => create.promise),
      replaceTaskOrder,
    });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let createRequest!: Promise<Todo | undefined>;
    act(() => {
      createRequest = result.current.addTask('New task');
    });

    await expect(result.current.reorderTasks(first.id, second.id)).resolves.toBe(false);
    expect(replaceTaskOrder).not.toHaveBeenCalled();
    await act(async () => {
      create.resolve(task({ id: 'new', text: 'New task' }));
      await createRequest;
    });
    expect(result.current.allTasks.map(item => item.id)).toEqual(['new', 'first', 'second']);
  });

  it('clears completed tasks only after each delete succeeds', async () => {
    const active = task({ id: 'active' });
    const completedOne = task({ id: 'done-1', completed: true });
    const completedTwo = task({ id: 'done-2', completed: true });
    const api = fakeApi({ deleteTask: vi.fn().mockResolvedValue(undefined) });
    const { result } = renderHook(() => (
      useTodos([active, completedOne, completedTwo], api, vi.fn())
    ));

    let cleared = 0;
    await act(async () => {
      cleared = await result.current.clearCompleted();
    });

    expect(cleared).toBe(2);
    expect(api.deleteTask).toHaveBeenNthCalledWith(1, 'done-1');
    expect(api.deleteTask).toHaveBeenNthCalledWith(2, 'done-2');
    expect(result.current.allTasks).toEqual([active]);
  });

  it('does not publish a late response after unmount', async () => {
    const pending = deferred<Todo>();
    const api = fakeApi({ createTask: vi.fn(() => pending.promise) });
    const onInfrastructureError = vi.fn();
    const { result, unmount } = renderHook(() => useTodos([], api, onInfrastructureError));

    let request!: Promise<Todo | undefined>;
    act(() => {
      request = result.current.addTask('Late task');
    });
    unmount();
    pending.resolve(task({ id: 'late' }));
    await request;

    expect(onInfrastructureError).not.toHaveBeenCalled();
  });

  it('publishes successful mutations and releases pending state in StrictMode', async () => {
    const pending = deferred<Todo>();
    const original = task();
    const api = fakeApi({ updateTask: vi.fn(() => pending.promise) });
    const { result } = renderHook(
      () => useTodos([original], api, vi.fn()),
      { wrapper: strictMode },
    );

    let request!: Promise<boolean>;
    act(() => {
      request = result.current.editTask(original.id, { text: 'Strict update' });
    });
    expect(result.current.pending.taskMutations.get(original.id)?.has('edit')).toBe(true);

    await act(async () => {
      pending.resolve(task({ text: 'Strict update' }));
      await request;
    });

    expect(result.current.allTasks[0].text).toBe('Strict update');
    expect(result.current.pending.taskMutations.has(original.id)).toBe(false);
  });

  it('publishes StrictMode errors and releases their pending state', async () => {
    const original = task();
    const api = fakeApi({
      updateTask: vi.fn().mockRejectedValue(
        new ApiError('business', 'INVALID_TASK', 'Strict failure', 422),
      ),
    });
    const { result } = renderHook(
      () => useTodos([original], api, vi.fn()),
      { wrapper: strictMode },
    );

    await act(async () => {
      await result.current.editTask(original.id, { text: 'Rejected' });
    });

    expect(result.current.businessError).toBe('INVALID_TASK');
    expect(result.current.pending.taskMutations.has(original.id)).toBe(false);
    expect(result.current.allTasks).toEqual([original]);
  });

  it('allows edit and completion on one task and merges out-of-order responses', async () => {
    const edit = deferred<Todo>();
    const completion = deferred<CompletionResult>();
    const original = task();
    const api = fakeApi({
      updateTask: vi.fn(() => edit.promise),
      setTaskCompletion: vi.fn(() => completion.promise),
    });
    const { result } = renderHook(() => useTodos([original], api, vi.fn()));

    let editRequest!: Promise<boolean>;
    let completionRequest!: Promise<CompletionResult | undefined>;
    act(() => {
      editRequest = result.current.editTask(original.id, { text: 'Edited' });
      completionRequest = result.current.toggleTask(original.id);
    });
    await act(async () => Promise.resolve());
    expect(api.updateTask).toHaveBeenCalledOnce();
    expect(api.setTaskCompletion).toHaveBeenCalledOnce();

    await act(async () => {
      edit.resolve(task({ text: 'Edited', completed: false }));
      await editRequest;
    });
    await act(async () => {
      completion.resolve({
        task: task({ text: 'Initial task', completed: true }),
        achievementState: {
          unlocked: [],
          streakDays: 1,
          lastActiveDate: '2026-07-13',
          todayCompleted: 1,
          todayDate: '2026-07-13',
        },
        newlyUnlocked: [],
      });
      await completionRequest;
    });

    expect(result.current.allTasks[0]).toMatchObject({ text: 'Edited', completed: true });
  });

  it('serializes different task completions so achievement snapshots apply in database order', async () => {
    const firstCompletion = deferred<CompletionResult>();
    const secondCompletion = deferred<CompletionResult>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const api = fakeApi({
      setTaskCompletion: vi.fn()
        .mockReturnValueOnce(firstCompletion.promise)
        .mockReturnValueOnce(secondCompletion.promise),
    });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let firstRequest!: Promise<CompletionResult | undefined>;
    let secondRequest!: Promise<CompletionResult | undefined>;
    act(() => {
      firstRequest = result.current.toggleTask(first.id);
      secondRequest = result.current.toggleTask(second.id);
    });
    await act(async () => Promise.resolve());
    expect(api.setTaskCompletion).toHaveBeenCalledTimes(1);
    const firstAchievementState = {
      unlocked: [],
      streakDays: 1,
      lastActiveDate: '2026-07-13',
      todayCompleted: 1,
      todayDate: '2026-07-13',
    };
    const secondAchievementState = {
      ...firstAchievementState,
      unlocked: ['first-task'],
      todayCompleted: 2,
    };
    secondCompletion.resolve({
      task: { ...second, completed: true },
      achievementState: secondAchievementState,
      newlyUnlocked: ['first-task'],
    });
    await act(async () => {
      firstCompletion.resolve({
        task: { ...first, completed: true },
        achievementState: firstAchievementState,
        newlyUnlocked: [],
      });
      await firstRequest;
    });
    expect(api.setTaskCompletion).toHaveBeenCalledTimes(2);
    const secondResult = await secondRequest;

    expect(result.current.allTasks.map(item => item.completed)).toEqual([true, true]);
    expect(secondResult?.achievementState).toEqual(secondAchievementState);
    expect(secondResult?.newlyUnlocked).toEqual(['first-task']);
  });

  it('releases the completion queue after a failed request', async () => {
    const firstCompletion = deferred<CompletionResult>();
    const secondCompletion = deferred<CompletionResult>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const api = fakeApi({
      setTaskCompletion: vi.fn()
        .mockReturnValueOnce(firstCompletion.promise)
        .mockReturnValueOnce(secondCompletion.promise),
    });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let firstRequest!: Promise<CompletionResult | undefined>;
    let secondRequest!: Promise<CompletionResult | undefined>;
    act(() => {
      firstRequest = result.current.toggleTask(first.id);
      secondRequest = result.current.toggleTask(second.id);
    });
    await act(async () => Promise.resolve());
    expect(api.setTaskCompletion).toHaveBeenCalledTimes(1);

    await act(async () => {
      firstCompletion.reject(new ApiError('business', 'INVALID_REQUEST', 'Rejected', 422));
      await firstRequest;
    });
    expect(api.setTaskCompletion).toHaveBeenCalledTimes(2);

    await act(async () => {
      secondCompletion.resolve({
        task: { ...second, completed: true },
        achievementState: {
          unlocked: [],
          streakDays: 1,
          lastActiveDate: '2026-07-13',
          todayCompleted: 1,
          todayDate: '2026-07-13',
        },
        newlyUnlocked: [],
      });
      await secondRequest;
    });
    expect(result.current.allTasks.map(item => item.completed)).toEqual([false, true]);
  });

  it('allows edit and completion during reorder without overwriting task fields', async () => {
    const reorder = deferred<Todo[]>();
    const edit = deferred<Todo>();
    const completion = deferred<CompletionResult>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const api = fakeApi({
      replaceTaskOrder: vi.fn(() => reorder.promise),
      updateTask: vi.fn(() => edit.promise),
      setTaskCompletion: vi.fn(() => completion.promise),
    });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let reorderRequest!: Promise<boolean>;
    let editRequest!: Promise<boolean>;
    let completionRequest!: Promise<CompletionResult | undefined>;
    act(() => {
      reorderRequest = result.current.reorderTasks(first.id, second.id);
      editRequest = result.current.editTask(first.id, { text: 'Edited first' });
      completionRequest = result.current.toggleTask(second.id);
    });
    await act(async () => Promise.resolve());
    expect(api.replaceTaskOrder).toHaveBeenCalledOnce();
    expect(api.updateTask).toHaveBeenCalledOnce();
    expect(api.setTaskCompletion).toHaveBeenCalledOnce();

    await act(async () => {
      edit.resolve({ ...first, text: 'Edited first' });
      await editRequest;
    });
    await act(async () => {
      completion.resolve({
        task: { ...second, completed: true },
        achievementState: {
          unlocked: [],
          streakDays: 1,
          lastActiveDate: '2026-07-13',
          todayCompleted: 1,
          todayDate: '2026-07-13',
        },
        newlyUnlocked: [],
      });
      await completionRequest;
    });
    await act(async () => {
      reorder.resolve([second, first]);
      await reorderRequest;
    });

    expect(result.current.allTasks.map(item => item.id)).toEqual(['second', 'first']);
    expect(result.current.allTasks[0].completed).toBe(true);
    expect(result.current.allTasks[1].text).toBe('Edited first');
  });

  it('blocks collection mutations while reorder is pending but still allows field mutations', async () => {
    const reorder = deferred<Todo[]>();
    const edit = deferred<Todo>();
    const first = task({ id: 'first', text: 'First' });
    const second = task({ id: 'second', text: 'Second' });
    const api = fakeApi({
      replaceTaskOrder: vi.fn(() => reorder.promise),
      updateTask: vi.fn(() => edit.promise),
    });
    const { result } = renderHook(() => useTodos([first, second], api, vi.fn()));

    let reorderRequest!: Promise<boolean>;
    act(() => {
      reorderRequest = result.current.reorderTasks(first.id, second.id);
    });

    await expect(result.current.addTask('Blocked create')).resolves.toBeUndefined();
    await expect(result.current.removeTask(first.id)).resolves.toBe(false);
    expect(api.createTask).not.toHaveBeenCalled();
    expect(api.deleteTask).not.toHaveBeenCalled();

    let editRequest!: Promise<boolean>;
    act(() => {
      editRequest = result.current.editTask(first.id, { text: 'Allowed edit' });
    });
    expect(api.updateTask).toHaveBeenCalledOnce();
    await act(async () => {
      edit.resolve({ ...first, text: 'Allowed edit' });
      await editRequest;
      reorder.resolve([second, first]);
      await reorderRequest;
    });
    expect(result.current.allTasks[1].text).toBe('Allowed edit');
  });

  it('keeps partial clear success and releases all pending state after a later failure', async () => {
    const active = task({ id: 'active' });
    const completedOne = task({ id: 'done-1', completed: true });
    const completedTwo = task({ id: 'done-2', completed: true });
    const api = fakeApi({
      deleteTask: vi.fn()
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new ApiError('business', 'DELETE_FAILED', '无法删除', 409)),
    });
    const { result } = renderHook(() => (
      useTodos([active, completedOne, completedTwo], api, vi.fn())
    ));

    let cleared = 0;
    await act(async () => {
      cleared = await result.current.clearCompleted();
    });

    expect(cleared).toBe(1);
    expect(result.current.allTasks.map(item => item.id)).toEqual(['active', 'done-2']);
    expect(result.current.businessError).toBe('DELETE_FAILED');
    expect(result.current.pending.clearCompleted).toBe(false);
    expect(result.current.pending.taskMutations.size).toBe(0);
  });
});
