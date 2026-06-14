import { useState, useCallback } from 'react';
import { Todo, TimeField, Priority, FilterType, Category } from '../types';

const STORAGE_KEY = 'todo-tasks';

const CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];
const CATEGORY_LABELS: Record<Category, string> = {
  work: '工作',
  study: '学习',
  life: '生活',
  other: '其他',
};

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

export function useTodos() {
  const [tasks, setTasks] = useState<Todo[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const [filter, setFilter] = useState<FilterType>('all');
  const [priority, setPriority] = useState<Priority>('low');
  const [categoryFilter, setCategoryFilter] = useState<Category | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const addTask = useCallback((text: string, time?: TimeField, category?: Category) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const newTask: Todo = {
      id: generateId(),
      text: trimmed,
      completed: false,
      priority,
      createdAt: Date.now(),
      time,
      category,
    };

    setTasks(prev => {
      const updated = [newTask, ...prev];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, [priority]);

  const toggleTask = useCallback((id: string) => {
    setTasks(prev => {
      const updated = prev.map(t =>
        t.id === id ? { ...t, completed: !t.completed } : t
      );
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const removeTask = useCallback((id: string) => {
    setTasks(prev => {
      const updated = prev.filter(t => t.id !== id);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const editTask = useCallback((id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => {
    setTasks(prev => {
      const updated = prev.map(t =>
        t.id === id ? { ...t, ...updates } : t
      );
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const reorderTasks = useCallback((fromId: string, toId: string) => {
    setTasks(prev => {
      const fromIdx = prev.findIndex(t => t.id === fromId);
      const toIdx = prev.findIndex(t => t.id === toId);
      if (fromIdx === -1 || toIdx === -1) return prev;
      const updated = [...prev];
      const [moved] = updated.splice(fromIdx, 1);
      updated.splice(toIdx, 0, moved);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const clearCompleted = useCallback(() => {
    setTasks(prev => {
      const updated = prev.filter(t => !t.completed);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const exportTasks = useCallback(() => {
    const data = {
      version: 1,
      exportedAt: new Date().toISOString(),
      tasks: tasks,
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
    return new Promise<void>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target?.result as string);
          if (data.tasks && Array.isArray(data.tasks)) {
            setTasks(prev => {
              const existingIds = new Set(prev.map(t => t.id));
              const newTasks = data.tasks.filter((t: Todo) => !existingIds.has(t.id));
              const updated = [...prev, ...newTasks];
              localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
              return updated;
            });
            resolve();
          } else {
            reject(new Error('Invalid file format'));
          }
        } catch (err) {
          reject(err);
        }
      };
      reader.readAsText(file);
    });
  }, []);

  const stats = {
    total: tasks.length,
    active: tasks.filter(t => !t.completed).length,
    completed: tasks.filter(t => t.completed).length,
  };

  const filteredTasks = tasks.filter(t => {
    if (filter === 'active') return !t.completed;
    if (filter === 'completed') return t.completed;
    return true;
  }).filter(t => {
    if (categoryFilter === 'all') return true;
    return t.category === categoryFilter;
  }).filter(t => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      t.text.toLowerCase().includes(query) ||
      (t.category && t.category.toLowerCase().includes(query)) ||
      (t.notes && t.notes.toLowerCase().includes(query))
    );
  }).sort((a, b) => {
    if (a.time && b.time) return a.time.start.localeCompare(b.time.start);
    if (a.time && !b.time) return -1;
    if (!a.time && b.time) return 1;
    return 0;
  });

  return {
    tasks: filteredTasks,
    allTasks: tasks,
    filter,
    priority,
    categoryFilter,
    searchQuery,
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
    categories: CATEGORIES,
    categoryLabels: CATEGORY_LABELS,
  };
}
