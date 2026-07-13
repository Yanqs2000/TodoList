import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, StrictMode, type ReactNode } from 'react';
import {
  InfrastructureError,
  type TodoApi,
} from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import { useReminders } from '../useReminders';

function makeTask(overrides: Partial<Todo> = {}): Todo {
  return {
    id: 't1',
    text: 'task',
    completed: false,
    priority: 'low',
    createdAt: 0,
    ...overrides,
  };
}

function strictMode({ children }: { children: ReactNode }) {
  return createElement(StrictMode, null, children);
}

describe('useReminders', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-06-18T10:00:00'));
  });
  afterEach(() => vi.useRealTimers());

  it('notifies only after the backend atomically claims a due reminder', async () => {
    const api = { claimReminder: vi.fn().mockResolvedValue(true) } as unknown as TodoApi;
    const onReminder = vi.fn();
    const task = makeTask({ text: '过去任务', time: { start: '2026-06-18T09:59' } });

    renderHook(() => useReminders([task], api, onReminder, vi.fn()));

    await waitFor(() => expect(onReminder).toHaveBeenCalledWith({
      taskId: 't1',
      text: '过去任务',
      time: '2026-06-18T09:59',
    }));
    expect(api.claimReminder).toHaveBeenCalledWith({
      taskId: 't1',
      scheduledStart: '2026-06-18T09:59',
    });
  });

  it('notifies exactly once when the first claim resolves after StrictMode effect replay', async () => {
    let resolve!: (value: boolean) => void;
    const claim = new Promise<boolean>(res => { resolve = res; });
    const api = { claimReminder: vi.fn(() => claim) } as unknown as TodoApi;
    const onReminder = vi.fn();
    const task = makeTask({ time: { start: '2026-06-18T09:59' } });

    renderHook(() => useReminders([task], api, onReminder, vi.fn()), {
      wrapper: strictMode,
    });
    await waitFor(() => expect(api.claimReminder).toHaveBeenCalledTimes(1));
    resolve(true);
    await waitFor(() => expect(onReminder).toHaveBeenCalledTimes(1));

    expect(onReminder).toHaveBeenCalledWith({
      taskId: 't1',
      text: 'task',
      time: '2026-06-18T09:59',
    });
  });

  it('does not notify when another process already claimed the reminder', async () => {
    const api = { claimReminder: vi.fn().mockResolvedValue(false) } as unknown as TodoApi;
    const onReminder = vi.fn();
    const task = makeTask({ time: { start: '2026-06-18T09:59' } });

    renderHook(() => useReminders([task], api, onReminder, vi.fn()));

    await waitFor(() => expect(api.claimReminder).toHaveBeenCalledTimes(1));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('does not issue duplicate claims while a claim is pending or after it settles', async () => {
    let resolve!: (value: boolean) => void;
    const claim = new Promise<boolean>(res => { resolve = res; });
    const api = { claimReminder: vi.fn(() => claim) } as unknown as TodoApi;
    const task = makeTask({ time: { start: '2026-06-18T09:59' } });

    renderHook(() => useReminders([task], api, vi.fn(), vi.fn()));
    await waitFor(() => expect(api.claimReminder).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(60_000);
    expect(api.claimReminder).toHaveBeenCalledTimes(1);

    resolve(false);
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(api.claimReminder).toHaveBeenCalledTimes(1);
  });

  it('reports infrastructure claim failures without notifying', async () => {
    const failure = new InfrastructureError(
      'infrastructure',
      'DATABASE_UNAVAILABLE',
      'Database unavailable',
      503,
    );
    const api = { claimReminder: vi.fn().mockRejectedValue(failure) } as unknown as TodoApi;
    const onReminder = vi.fn();
    const onError = vi.fn();
    const task = makeTask({ time: { start: '2026-06-18T09:59' } });

    renderHook(() => useReminders([task], api, onReminder, onError));

    await waitFor(() => expect(onError).toHaveBeenCalledWith(failure));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('does not notify from a stale claim after the task is rescheduled', async () => {
    let resolve!: (value: boolean) => void;
    const claim = new Promise<boolean>(res => { resolve = res; });
    const api = { claimReminder: vi.fn(() => claim) } as unknown as TodoApi;
    const onReminder = vi.fn();
    const { rerender } = renderHook(
      ({ tasks }) => useReminders(tasks, api, onReminder, vi.fn()),
      {
        initialProps: {
          tasks: [makeTask({ time: { start: '2026-06-18T09:59' } })],
        },
      },
    );
    await waitFor(() => expect(api.claimReminder).toHaveBeenCalledTimes(1));

    rerender({ tasks: [makeTask({ time: { start: '2026-06-18T11:00' } })] });
    resolve(true);
    await Promise.resolve();

    expect(onReminder).not.toHaveBeenCalled();
  });

  it('ignores a failed claim from a replaced API session', async () => {
    let reject!: (reason: unknown) => void;
    const oldClaim = new Promise<boolean>((_, rej) => { reject = rej; });
    const oldApi = { claimReminder: vi.fn(() => oldClaim) } as unknown as TodoApi;
    const newApi = { claimReminder: vi.fn().mockResolvedValue(false) } as unknown as TodoApi;
    const onError = vi.fn();
    const task = makeTask({ time: { start: '2026-06-18T09:59' } });
    const { rerender } = renderHook(
      ({ api }) => useReminders([task], api, vi.fn(), onError),
      { initialProps: { api: oldApi } },
    );
    await waitFor(() => expect(oldApi.claimReminder).toHaveBeenCalledTimes(1));

    rerender({ api: newApi });
    reject(new InfrastructureError('network', 'NETWORK_ERROR', 'Network request failed'));
    await Promise.resolve();

    expect(onError).not.toHaveBeenCalled();
  });

  it('ignores completed, future, and stale tasks', async () => {
    const api = { claimReminder: vi.fn().mockResolvedValue(true) } as unknown as TodoApi;
    const tasks = [
      makeTask({ id: 'completed', completed: true, time: { start: '2026-06-18T09:59' } }),
      makeTask({ id: 'future', time: { start: '2026-06-18T11:00' } }),
      makeTask({ id: 'stale', time: { start: '2026-06-17T09:00' } }),
    ];

    renderHook(() => useReminders(tasks, api, vi.fn(), vi.fn()));
    await vi.advanceTimersByTimeAsync(1);

    expect(api.claimReminder).not.toHaveBeenCalled();
  });
});
