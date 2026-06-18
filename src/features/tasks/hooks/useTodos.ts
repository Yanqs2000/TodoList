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
    return validateTodoArray(parsed);
  } catch {
    return [];
  }
}

export function useTodos() {
  const [tasks, setTasks] = useState<Todo[]>(loadInitialTasks);

  const [filter, setFilter] = useState<FilterType>('all');
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
      category,
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

  const clearCompleted = useCallback(() => {
    setTasks(prev => persist(prev.filter(t => !t.completed)));
  }, []);

  const exportTasks = useCallback(() => {
    const data = {
      version: 1,
      exportedAt: new Date().toISOString(),
      tasks,
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `todo-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [tasks]);

  const importTasks = useCallback((file: File) => {
    return new Promise<{ added: number; skipped: number }>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target?.result as string);
          if (!data || !Array.isArray(data.tasks)) {
            reject(new Error('Invalid file format'));
            return;
          }
          const valid = validateTodoArray(data.tasks);
          const skipped = data.tasks.length - valid.length;
          setTasks(prev => {
            const existingIds = new Set(prev.map(t => t.id));
            const newTasks = valid.filter(t => !existingIds.has(t.id));
            return persist([...prev, ...newTasks]);
          });
          resolve({ added: valid.length, skipped });
        } catch (err) {
          reject(err);
        }
      };
      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsText(file);
    });
  }, []);

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
    exportTasks,
    importTasks,
    setFilter,
    setPriority,
    setCategoryFilter,
    setSearchQuery,
    setSortMode,
    categories: CATEGORIES,
    categoryLabels: CATEGORY_LABELS,
  };
}
