import { useState, useEffect, useCallback } from 'react';
import { safeSetItem, safeGetItem } from '../utils/storage';

export type Theme = 'light' | 'dark';
const STORAGE_KEY = 'todo-theme';

function getInitialTheme(): Theme {
  const stored = safeGetItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    safeSetItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState(prev => (prev === 'light' ? 'dark' : 'light'));
  }, []);

  return { theme, toggleTheme };
}
