import { useCallback, useEffect, useRef } from 'react';
import { ApiError, type TodoApi } from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';

const CHECK_INTERVAL_MS = 30_000;
const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

export interface ReminderEvent {
  taskId: string;
  text: string;
  time: string;
}

function parseTimeStart(iso: string): number | null {
  const timestamp = new Date(iso).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function reminderKey(task: Todo): string | null {
  return task.time?.start ? `${task.id}|${task.time.start}` : null;
}

export function useReminders(
  tasks: Todo[],
  api: TodoApi,
  onReminder: (event: ReminderEvent) => void,
  onError: (error: unknown) => void,
) {
  const tasksRef = useRef(tasks);
  const onReminderRef = useRef(onReminder);
  const onErrorRef = useRef(onError);
  const pendingRef = useRef(new Set<string>());
  const processedRef = useRef(new Set<string>());
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const apiRef = useRef(api);

  if (apiRef.current !== api) {
    apiRef.current = api;
    generationRef.current += 1;
  }

  tasksRef.current = tasks;
  onReminderRef.current = onReminder;
  onErrorRef.current = onError;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const claim = useCallback(async (task: Todo, key: string) => {
    const generation = generationRef.current;
    pendingRef.current.add(key);
    try {
      const claimed = await api.claimReminder({
        taskId: task.id,
        scheduledStart: task.time!.start,
      });
      if (generation !== generationRef.current) return;
      processedRef.current.add(key);
      const stillCurrent = tasksRef.current.some(current => (
        current.id === task.id
        && !current.completed
        && current.time?.start === task.time!.start
      ));
      if (claimed && mountedRef.current && stillCurrent) {
        onReminderRef.current({
          taskId: task.id,
          text: task.text,
          time: task.time!.start,
        });
      }
    } catch (error) {
      if (generation !== generationRef.current) return;
      if (error instanceof ApiError && error.kind === 'business') {
        processedRef.current.add(key);
      }
      if (mountedRef.current) onErrorRef.current(error);
    } finally {
      pendingRef.current.delete(key);
    }
  }, [api]);

  const check = useCallback(() => {
    const now = Date.now();
    const activeKeys = new Set(tasksRef.current.flatMap(task => {
      const key = reminderKey(task);
      return key ? [key] : [];
    }));
    for (const key of processedRef.current) {
      if (!activeKeys.has(key)) processedRef.current.delete(key);
    }

    for (const task of tasksRef.current) {
      if (task.completed || !task.time?.start) continue;
      const key = reminderKey(task)!;
      if (pendingRef.current.has(key) || processedRef.current.has(key)) continue;

      const due = parseTimeStart(task.time.start);
      if (due === null || due > now) continue;
      if (now - due > STALE_THRESHOLD_MS) {
        processedRef.current.add(key);
        continue;
      }
      void claim(task, key);
    }
  }, [claim]);

  useEffect(() => {
    check();
    const interval = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [check]);

  useEffect(() => {
    check();
  }, [tasks, check]);
}
