import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useReminders, type ReminderEvent } from '../useReminders';
import type { Todo } from '@/shared/types';

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

function isoFromNow(deltaMs: number): string {
  const d = new Date(Date.now() + deltaMs);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

describe('useReminders', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-06-18T10:00:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fires onReminder for tasks past their time.start', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({ id: 't1', text: '过去任务', time: { start: isoFromNow(-60_000) } })];
    renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).toHaveBeenCalledTimes(1);
    expect(onReminder.mock.calls[0][0]).toMatchObject<Partial<ReminderEvent>>({
      taskId: 't1',
      text: '过去任务',
    });
  });

  it('does not fire for tasks scheduled in the future', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({ id: 't1', time: { start: isoFromNow(60 * 60 * 1000) } })];
    renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('does not fire for completed tasks', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({ completed: true, time: { start: isoFromNow(-60_000) } })];
    renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('does not fire for tasks without time', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({})];
    renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('does not fire twice for the same task across remounts (persisted)', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({ id: 't1', time: { start: isoFromNow(-60_000) } })];

    const { unmount } = renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).toHaveBeenCalledTimes(1);
    unmount();

    const onReminder2 = vi.fn();
    renderHook(() => useReminders(tasks, onReminder2));
    expect(onReminder2).not.toHaveBeenCalled();
  });

  it('skips stale reminders (>24h late) silently', () => {
    const onReminder = vi.fn();
    const tasks = [makeTask({ time: { start: isoFromNow(-25 * 60 * 60 * 1000) } })];
    renderHook(() => useReminders(tasks, onReminder));
    expect(onReminder).not.toHaveBeenCalled();
  });

  it('fires again if user reschedules to a different time after first reminder', () => {
    const onReminder = vi.fn();
    // Use distinct minutes so the reminder key (id|time) actually differs.
    const t1 = '2026-06-18T09:55';
    const t2 = '2026-06-18T09:58';

    const { rerender } = renderHook(
      ({ tasks }: { tasks: Todo[] }) => useReminders(tasks, onReminder),
      { initialProps: { tasks: [makeTask({ id: 't1', time: { start: t1 } })] } },
    );
    expect(onReminder).toHaveBeenCalledTimes(1);

    rerender({ tasks: [makeTask({ id: 't1', time: { start: t2 } })] });
    expect(onReminder).toHaveBeenCalledTimes(2);
  });
});
