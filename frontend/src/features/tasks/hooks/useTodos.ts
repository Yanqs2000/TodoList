import { useState, useCallback } from 'react';
import { Todo, TimeField, Priority, FilterType, Category } from '@/shared/types';
import { CATEGORIES, CATEGORY_LABELS } from '@/shared/constants';
import { safeSetItem, safeGetItem } from '@/shared/lib/storage';
import { generateId } from '../lib/id';
import { validateTodoArray } from '../lib/validateTodo';

const STORAGE_KEY = 'todo-tasks';

function loadInitialTasks(): Todo[] {
  const raw = safeGetItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    // Normalize legacy tasks that have no category: default to 'other' so they
    // show up under the 其他 filter (otherwise they only appear under 全部).
    return validateTodoArray(parsed).map(t => (t.category ? t : { ...t, category: 'other' }));
  } catch {
    return [];
  }
}

export function useTodos() {
  const [tasks, setTasks] = useState<Todo[]>(loadInitialTasks);

  const [filter, setFilter] = useState<FilterType>('active');
  const [priority, setPriority] = useState<Priority>('low');
  const [categoryFilter, setCategoryFilter] = useState<Category | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMode, setSortMode] = useState<'manual' | 'time'>('manual');

  const persist = (next: Todo[]) => {
    safeSetItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  };

  const addTask = useCallback((text: string, time?: TimeField, category?: Category, notes?: string, priorityOverride?: Priority) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const newTask: Todo = {
      id: generateId(),
      text: trimmed,
      completed: false,
      priority: priorityOverride ?? priority,
      createdAt: Date.now(),
      time,
      category: category ?? 'other',
      notes: notes?.trim() || undefined,
    };

    setTasks(prev => persist([newTask, ...prev]));
  }, [priority]);

  const toggleTask = useCallback((id: string) => {
    setTasks(prev => persist(
      prev.map(t => t.id === id ? { ...t, completed: !t.completed } : t)
    ));
  }, []);

  const removeTask = useCallback((id: string) => {
    setTasks(prev => persist(prev.filter(t => t.id !== id)));
  }, []);

  const editTask = useCallback((id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => {
    setTasks(prev => persist(
      prev.map(t => t.id === id ? { ...t, ...updates } : t)
    ));
  }, []);

  const reorderTasks = useCallback((fromId: string, toId: string) => {
    setTasks(prev => {
      const fromIdx = prev.findIndex(t => t.id === fromId);
      const toIdx = prev.findIndex(t => t.id === toId);
      if (fromIdx === -1 || toIdx === -1) return prev;
      const updated = [...prev];
      const [moved] = updated.splice(fromIdx, 1);
      updated.splice(toIdx, 0, moved);
      return persist(updated);
    });
    setSortMode('manual');
  }, []);

  const clearCompleted = useCallback((): number => {
    const cleared = tasks.filter(t => t.completed).length;
    setTasks(prev => persist(prev.filter(t => !t.completed)));
    return cleared;
  }, [tasks]);

  const stats = {
    total: tasks.length,
    active: tasks.filter(t => !t.completed).length,
    completed: tasks.filter(t => t.completed).length,
  };

  const filteredTasks = (() => {
    const filtered = tasks.filter(t => {
      if (filter === 'active' && t.completed) return false;
      if (filter === 'completed' && !t.completed) return false;
      if (categoryFilter !== 'all' && t.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const inText = t.text.toLowerCase().includes(query);
        const inCategory = t.category && t.category.toLowerCase().includes(query);
        const inNotes = t.notes && t.notes.toLowerCase().includes(query);
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
