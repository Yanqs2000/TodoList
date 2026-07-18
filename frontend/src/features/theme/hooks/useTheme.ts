import { useCallback, useEffect, useRef, useState } from 'react';
import type { TodoApi } from '@/shared/api/contracts';
import type { TranslationKey } from '@/features/i18n/translations';

export type ThemeStyle = 'workspace' | 'mint' | 'paper';
export type ThemeMode = 'light' | 'dark';
export type ThemeId = `${ThemeStyle}-${ThemeMode}`;

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
  name: TranslationKey;
  description: TranslationKey;
  swatch: { bg: string; card: string; accent: string };
}

export const THEMES: Record<ThemeId, ThemeMeta> = {
  'workspace-light': {
    id: 'workspace-light',
    name: 'theme.workspaceLight.name', description: 'theme.workspaceLight.desc',
    swatch: { bg: '#FAFAF7', card: '#FFFFFF', accent: '#0D9488' },
  },
  'mint-light': {
    id: 'mint-light',
    name: 'theme.mintLight.name', description: 'theme.mintLight.desc',
    swatch: { bg: '#F7FAF9', card: '#FFFFFF', accent: '#0D9488' },
  },
  'paper-light': {
    id: 'paper-light',
    name: 'theme.paperLight.name', description: 'theme.paperLight.desc',
    swatch: { bg: '#F7F6F3', card: '#FFFDF8', accent: '#0D9488' },
  },
  'workspace-dark': {
    id: 'workspace-dark',
    name: 'theme.workspaceDark.name', description: 'theme.workspaceDark.desc',
    swatch: { bg: '#0E0E10', card: '#18181B', accent: '#2DD4BF' },
  },
  'mint-dark': {
    id: 'mint-dark',
    name: 'theme.mintDark.name', description: 'theme.mintDark.desc',
    swatch: { bg: '#1A1D1C', card: '#25292B', accent: '#2DD4BF' },
  },
  'paper-dark': {
    id: 'paper-dark',
    name: 'theme.paperDark.name', description: 'theme.paperDark.desc',
    swatch: { bg: '#0E0E10', card: '#1A1814', accent: '#2DD4BF' },
  },
};

export function useTheme(
  initialTheme: ThemeId,
  api: TodoApi,
  onError: (error: unknown) => void,
) {
  const [theme, setThemeState] = useState<ThemeId>(initialTheme);
  const mountedRef = useRef(true);
  const committedRef = useRef(initialTheme);
  const latestIntentRef = useRef(0);
  const generationRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    committedRef.current = initialTheme;
    latestIntentRef.current += 1;
    generationRef.current += 1;
    queueRef.current = Promise.resolve();
    setThemeState(initialTheme);
  }, [api, initialTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const setTheme = useCallback((id: ThemeId): Promise<boolean> => {
    const intent = ++latestIntentRef.current;
    const generation = generationRef.current;
    const operation = queueRef.current.then(async () => {
      let succeeded = false;
      try {
        const settings = await api.updateSettings({ theme: id });
        if (mountedRef.current && generation === generationRef.current) {
          committedRef.current = settings.theme;
          succeeded = true;
        }
      } catch (error) {
        if (mountedRef.current && generation === generationRef.current) onError(error);
      }
      if (
        mountedRef.current
        && generation === generationRef.current
        && intent === latestIntentRef.current
      ) {
        setThemeState(committedRef.current);
      }
      return succeeded;
    });
    queueRef.current = operation.then(() => undefined);
    return operation;
  }, [api, onError]);

  return { theme, setTheme };
}
