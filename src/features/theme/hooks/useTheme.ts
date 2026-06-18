import { useState, useEffect, useCallback } from 'react';
import { safeSetItem, safeGetItem } from '@/shared/lib/storage';

export type ThemeStyle = 'workspace' | 'mint' | 'paper';
export type ThemeMode = 'light' | 'dark';
export type ThemeId = `${ThemeStyle}-${ThemeMode}`;

const STORAGE_KEY = 'todo-theme';

export const THEME_IDS: ThemeId[] = [
  'workspace-light',
  'mint-light',
  'paper-light',
  'workspace-dark',
  'mint-dark',
  'paper-dark',
];

export interface ThemeMeta {
  id: ThemeId;
  name: string;
  description: string;
  swatch: { bg: string; card: string; accent: string };
}

export const THEMES: Record<ThemeId, ThemeMeta> = {
  'workspace-light': {
    id: 'workspace-light',
    name: '工作台 · 浅',
    description: '暖白底，适合日常办公',
    swatch: { bg: '#FAFAF7', card: '#FFFFFF', accent: '#0D9488' },
  },
  'mint-light': {
    id: 'mint-light',
    name: '薄荷 · 浅',
    description: '浅绿底，清新自然',
    swatch: { bg: '#F0FDFA', card: '#FFFFFF', accent: '#0D9488' },
  },
  'paper-light': {
    id: 'paper-light',
    name: '纸笺 · 浅',
    description: '米色纸感，Notion 风',
    swatch: { bg: '#F7F6F3', card: '#FFFDF8', accent: '#0D9488' },
  },
  'workspace-dark': {
    id: 'workspace-dark',
    name: '工作台 · 深',
    description: '深色，适合夜间办公',
    swatch: { bg: '#0E0E10', card: '#18181B', accent: '#2DD4BF' },
  },
  'mint-dark': {
    id: 'mint-dark',
    name: '薄荷 · 深',
    description: '深绿底，护眼舒适',
    swatch: { bg: '#0A1F1C', card: '#13302C', accent: '#2DD4BF' },
  },
  'paper-dark': {
    id: 'paper-dark',
    name: '纸笺 · 深',
    description: '深色，纸感延续',
    swatch: { bg: '#0E0E10', card: '#1A1814', accent: '#2DD4BF' },
  },
};

function isValidThemeId(value: string | null): value is ThemeId {
  return value !== null && THEME_IDS.includes(value as ThemeId);
}

function migrateLegacy(value: string | null): ThemeId | null {
  if (value === 'light') return 'workspace-light';
  if (value === 'dark') return 'workspace-dark';
  if (value === 'editor-light') return 'mint-light';
  if (value === 'editor-dark') return 'mint-dark';
  return null;
}

function getInitialTheme(): ThemeId {
  const stored = safeGetItem(STORAGE_KEY);
  if (isValidThemeId(stored)) return stored;
  const migrated = migrateLegacy(stored);
  if (migrated) return migrated;
  try {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'workspace-dark' : 'workspace-light';
  } catch {
    return 'workspace-light';
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeId>(getInitialTheme);

  // Sync data-theme attribute on every theme change. We do NOT persist here:
  // persistence is reserved for explicit user actions in setTheme below, so
  // a `prefers-color-scheme` probe on first launch does not get baked into
  // localStorage (which would break system-theme follow-along).
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // One-time migration: if storage holds a legacy value, normalize it on mount.
  useEffect(() => {
    const stored = safeGetItem(STORAGE_KEY);
    if (stored !== null && !isValidThemeId(stored) && migrateLegacy(stored)) {
      safeSetItem(STORAGE_KEY, theme);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id);
    safeSetItem(STORAGE_KEY, id);
  }, []);

  return { theme, setTheme };
}
