import { useCallback, useEffect, useRef, useState } from 'react';
import { CATEGORIES, CATEGORY_LABELS } from '@/shared/constants';
import {
  ApiError,
  InfrastructureError,
  type CompletionResult,
  type TodoApi,
  type UpdateTaskInput,
} from '@/shared/api/contracts';
import type { Category, FilterType, Priority, TimeField, Todo } from '@/shared/types';

export interface PendingMutations {
  create: boolean;
  reorder: boolean;
  clearCompleted: boolean;
  taskIds: ReadonlySet<string>;
}

export interface TodoState {
  tasks: Todo[];
  allTasks: Todo[];
  filter: FilterType;
  priority: Priority;
  categoryFilter: Category | 'all';
  searchQuery: string;
  sortMode: 'manual' | 'time';
  stats: { total: number; active: number; completed: number };
  pending: PendingMutations;
  businessError: string | null;
  clearBusinessError: () => void;
  addTask: (
    text: string,
    time?: TimeField,
    category?: Category,
    notes?: string,
    priorityOverride?: Priority,
  ) => Promise<Todo | undefined>;
  toggleTask: (id: string) => Promise<CompletionResult | undefined>;
  removeTask: (id: string) => Promise<boolean>;
  editTask: (
    id: string,
    updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>,
  ) => Promise<boolean>;
  clearCompleted: () => Promise<number>;
  reorderTasks: (fromId: string, toId: string) => Promise<boolean>;
  setFilter: (value: FilterType) => void;
  setPriority: (value: Priority) => void;
  setCategoryFilter: (value: Category | 'all') => void;
  setSearchQuery: (value: string) => void;
  setSortMode: (value: 'manual' | 'time') => void;
  categories: Category[];
  categoryLabels: Record<Category, string>;
}

const EMPTY_PENDING: PendingMutations = {
  create: false,
  reorder: false,
  clearCompleted: false,
  taskIds: new Set(),
};

function localDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function toUpdateInput(
  updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>,
): UpdateTaskInput {
  const input: UpdateTaskInput = {};
  if ('text' in updates) input.text = updates.text;
  if ('priority' in updates) input.priority = updates.priority;
  if ('category' in updates) input.category = updates.category;
  if ('time' in updates) input.time = updates.time ?? null;
  if ('notes' in updates) input.notes = updates.notes ?? null;
  return input;
}

export function useTodos(
  initialTasks: Todo[],
  api: TodoApi,
  onInfrastructureError: (error: InfrastructureError) => void,
): TodoState {
  const [tasks, setTasks] = useState<Todo[]>(initialTasks);
  const [filter, setFilter] = useState<FilterType>('active');
  const [priority, setPriority] = useState<Priority>('low');
  const [categoryFilter, setCategoryFilter] = useState<Category | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMode, setSortMode] = useState<'manual' | 'time'>('manual');
  const [pending, setPending] = useState<PendingMutations>(EMPTY_PENDING);
  const [businessError, setBusinessError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const tasksRef = useRef(tasks);
  const createPendingRef = useRef(false);
  const reorderPendingRef = useRef(false);
  const clearPendingRef = useRef(false);
  const pendingTaskIdsRef = useRef(new Set<string>());

  tasksRef.current = tasks;

  useEffect(() => () => {
    mountedRef.current = false;
  }, []);

  const handleError = useCallback((error: unknown) => {
    if (!mountedRef.current) return;
    if (error instanceof InfrastructureError) {
      onInfrastructureError(error);
      return;
    }
    if (error instanceof ApiError && error.kind === 'business') {
      setBusinessError(error.message);
      return;
    }
    onInfrastructureError(new InfrastructureError(
      'infrastructure',
      'UNEXPECTED_CLIENT_ERROR',
      'Unexpected backend error',
    ));
  }, [onInfrastructureError]);

  const beginTaskMutation = useCallback((taskId: string): boolean => {
    if (reorderPendingRef.current || pendingTaskIdsRef.current.has(taskId)) return false;
    pendingTaskIdsRef.current.add(taskId);
    setBusinessError(null);
    setPending(current => ({
      ...current,
      taskIds: new Set(pendingTaskIdsRef.current),
    }));
    return true;
  }, []);

  const endTaskMutation = useCallback((taskId: string) => {
    pendingTaskIdsRef.current.delete(taskId);
    if (!mountedRef.current) return;
    setPending(current => ({
      ...current,
      taskIds: new Set(pendingTaskIdsRef.current),
    }));
  }, []);

  const addTask = useCallback(async (
    text: string,
    time?: TimeField,
    category?: Category,
    notes?: string,
    priorityOverride?: Priority,
  ): Promise<Todo | undefined> => {
    const trimmed = text.trim();
    if (!trimmed || createPendingRef.current || reorderPendingRef.current) return undefined;
    createPendingRef.current = true;
    setBusinessError(null);
    setPending(current => ({ ...current, create: true }));
    try {
      const created = await api.createTask({
        text: trimmed,
        priority: priorityOverride ?? priority,
        ...(time ? { time } : {}),
        category: category ?? 'other',
        ...(notes?.trim() ? { notes: notes.trim() } : {}),
      });
      if (!mountedRef.current) return undefined;
      setTasks(current => [created, ...current]);
      return created;
    } catch (error) {
      handleError(error);
      return undefined;
    } finally {
      createPendingRef.current = false;
      if (mountedRef.current) {
        setPending(current => ({ ...current, create: false }));
      }
    }
  }, [api, handleError, priority]);

  const toggleTask = useCallback(async (id: string): Promise<CompletionResult | undefined> => {
    const task = tasksRef.current.find(item => item.id === id);
    if (!task || !beginTaskMutation(id)) return undefined;
    try {
      const result = await api.setTaskCompletion(id, {
        completed: !task.completed,
        localDate: localDate(),
      });
      if (!mountedRef.current) return undefined;
      setTasks(current => current.map(item => item.id === id ? result.task : item));
      return result;
    } catch (error) {
      handleError(error);
      return undefined;
    } finally {
      endTaskMutation(id);
    }
  }, [api, beginTaskMutation, endTaskMutation, handleError]);

  const removeTask = useCallback(async (id: string): Promise<boolean> => {
    if (!tasksRef.current.some(item => item.id === id) || !beginTaskMutation(id)) return false;
    try {
      await api.deleteTask(id);
      if (!mountedRef.current) return false;
      setTasks(current => current.filter(item => item.id !== id));
      return true;
    } catch (error) {
      handleError(error);
      return false;
    } finally {
      endTaskMutation(id);
    }
  }, [api, beginTaskMutation, endTaskMutation, handleError]);

  const editTask = useCallback(async (
    id: string,
    updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>,
  ): Promise<boolean> => {
    if (!tasksRef.current.some(item => item.id === id) || !beginTaskMutation(id)) return false;
    try {
      const updated = await api.updateTask(id, toUpdateInput(updates));
      if (!mountedRef.current) return false;
      setTasks(current => current.map(item => item.id === id ? updated : item));
      return true;
    } catch (error) {
      handleError(error);
      return false;
    } finally {
      endTaskMutation(id);
    }
  }, [api, beginTaskMutation, endTaskMutation, handleError]);

  const reorderTasks = useCallback(async (fromId: string, toId: string): Promise<boolean> => {
    if (
      fromId === toId
      || reorderPendingRef.current
      || createPendingRef.current
      || pendingTaskIdsRef.current.size > 0
    ) return false;
    const fromIdx = tasksRef.current.findIndex(item => item.id === fromId);
    const toIdx = tasksRef.current.findIndex(item => item.id === toId);
    if (fromIdx === -1 || toIdx === -1) return false;

    const proposed = [...tasksRef.current];
    const [moved] = proposed.splice(fromIdx, 1);
    proposed.splice(toIdx, 0, moved);
    reorderPendingRef.current = true;
    setBusinessError(null);
    setPending(current => ({ ...current, reorder: true }));
    try {
      const ordered = await api.replaceTaskOrder(proposed.map(item => item.id));
      if (!mountedRef.current) return false;
      setTasks(ordered);
      setSortMode('manual');
      return true;
    } catch (error) {
      handleError(error);
      return false;
    } finally {
      reorderPendingRef.current = false;
      if (mountedRef.current) {
        setPending(current => ({ ...current, reorder: false }));
      }
    }
  }, [api, handleError]);

  const clearCompleted = useCallback(async (): Promise<number> => {
    const completed = tasksRef.current.filter(item => item.completed);
    if (
      completed.length === 0
      || clearPendingRef.current
      || reorderPendingRef.current
      || completed.some(item => pendingTaskIdsRef.current.has(item.id))
    ) return 0;

    clearPendingRef.current = true;
    completed.forEach(item => pendingTaskIdsRef.current.add(item.id));
    setBusinessError(null);
    setPending(current => ({
      ...current,
      clearCompleted: true,
      taskIds: new Set(pendingTaskIdsRef.current),
    }));
    let cleared = 0;
    try {
      for (const item of completed) {
        try {
          await api.deleteTask(item.id);
        } catch (error) {
          handleError(error);
          break;
        }
        if (!mountedRef.current) break;
        cleared += 1;
        setTasks(current => current.filter(taskItem => taskItem.id !== item.id));
      }
      return cleared;
    } finally {
      clearPendingRef.current = false;
      completed.forEach(item => pendingTaskIdsRef.current.delete(item.id));
      if (mountedRef.current) {
        setPending(current => ({
          ...current,
          clearCompleted: false,
          taskIds: new Set(pendingTaskIdsRef.current),
        }));
      }
    }
  }, [api, handleError]);

  const stats = {
    total: tasks.length,
    active: tasks.filter(item => !item.completed).length,
    completed: tasks.filter(item => item.completed).length,
  };

  const filteredTasks = (() => {
    const filtered = tasks.filter(task => {
      if (filter === 'active' && task.completed) return false;
      if (filter === 'completed' && !task.completed) return false;
      if (categoryFilter !== 'all' && task.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const inText = task.text.toLowerCase().includes(query);
        const inCategory = task.category?.toLowerCase().includes(query);
        const inNotes = task.notes?.toLowerCase().includes(query);
        if (!inText && !inCategory && !inNotes) return false;
      }
      return true;
    });

    if (sortMode === 'time') {
      return [...filtered].sort((a, b) => {
        if (a.time && b.time) return a.time.start.localeCompare(b.time.start);
        if (a.time) return -1;
        if (b.time) return 1;
        return 0;
      });
    }
    return filtered;
  })();

  return {
    tasks: filteredTasks,
    allTasks: tasks,
    filter,
    priority,
    categoryFilter,
    searchQuery,
    sortMode,
    stats,
    pending,
    businessError,
    clearBusinessError: () => setBusinessError(null),
    addTask,
    toggleTask,
    removeTask,
    editTask,
    clearCompleted,
    reorderTasks,
    setFilter,
    setPriority,
    setCategoryFilter,
    setSearchQuery,
    setSortMode,
    categories: CATEGORIES,
    categoryLabels: CATEGORY_LABELS,
  };
}
