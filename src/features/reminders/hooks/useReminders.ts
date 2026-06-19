import { useEffect, useRef, useCallback } from 'react';
import type { Todo } from '@/shared/types';
import { safeSetItem, safeGetItem } from '@/shared/lib/storage';

const STORAGE_KEY = 'todo-reminded';
const CHECK_INTERVAL_MS = 30_000;
const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

export interface ReminderEvent {
  taskId: string;
  text: string;
  time: string;
}

function loadReminded(): Set<string> {
  const raw = safeGetItem(STORAGE_KEY);
  if (!raw) return new Set();
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? new Set(arr.filter(x => typeof x === 'string')) : new Set();
  } catch {
    return new Set();
  }
}

function persistReminded(set: Set<string>) {
  safeSetItem(STORAGE_KEY, JSON.stringify([...set]));
}

function parseTimeStart(iso: string): number | null {
  // ISO format: "YYYY-MM-DDTHH:mm" (interpreted as local time per app convention)
  const ts = new Date(iso).getTime();
  return Number.isFinite(ts) ? ts : null;
}

/**
 * Watches todos with `time.start` set, fires `onReminder` when their reminder time
 * passes. De-duplicates via localStorage so a task is reminded at most once even
 * across app restarts. Skips reminders that are >24h late to avoid spam on launch.
 *
 * Pruning: when a task is removed or its time is changed/cleared, its entry is
 * removed from the reminded set so a re-set can fire again.
 */
export function useReminders(
  tasks: Todo[],
  onReminder: (event: ReminderEvent) => void,
) {
  const remindedRef = useRef<Set<string>>(loadReminded());
  const onReminderRef = useRef(onReminder);
  onReminderRef.current = onReminder;
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;

  const check = useCallback(() => {
    const now = Date.now();
    const reminded = remindedRef.current;
    let dirty = false;

    // Reminder key: `${id}|${time.start}` — changes if user re-schedules.
    const activeKeys = new Set<string>();
    for (const task of tasksRef.current) {
      if (!task.time?.start) continue;
      activeKeys.add(`${task.id}|${task.time.start}`);
    }

    // Prune entries that no longer correspond to any task's current schedule.
    for (const key of [...reminded]) {
      if (!activeKeys.has(key)) {
        reminded.delete(key);
        dirty = true;
      }
    }

    for (const task of tasksRef.current) {
      if (task.completed) continue;
      if (!task.time?.start) continue;

      const key = `${task.id}|${task.time.start}`;
      if (reminded.has(key)) continue;

      const due = parseTimeStart(task.time.start);
      if (due === null) continue;
      if (due > now) continue;
      if (now - due > STALE_THRESHOLD_MS) {
        // Mark stale ones as reminded silently to avoid repeated checks.
        reminded.add(key);
        dirty = true;
        continue;
      }

      reminded.add(key);
      dirty = true;
      onReminderRef.current({ taskId: task.id, text: task.text, time: task.time.start });
    }

    if (dirty) persistReminded(reminded);
  }, []);

  useEffect(() => {
    check();
    const id = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [check]);

  // Also check when tasks change (e.g., user just edited a time).
  useEffect(() => {
    check();
  }, [tasks, check]);
}
