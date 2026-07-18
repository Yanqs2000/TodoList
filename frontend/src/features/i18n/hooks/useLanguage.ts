import { useCallback, useEffect, useRef, useState } from 'react';
import type { TodoApi } from '@/shared/api/contracts';
import type { Language } from '../translations';

export function useLanguage(
  initialLanguage: Language,
  api: TodoApi,
  onError: (error: unknown) => void,
) {
  const [language, setLanguageState] = useState(initialLanguage);
  const [pending, setPending] = useState(false);
  const mountedRef = useRef(true);
  const committedRef = useRef(initialLanguage);
  const generationRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    committedRef.current = initialLanguage;
    generationRef.current += 1;
    queueRef.current = Promise.resolve();
    setLanguageState(initialLanguage);
    setPending(false);
  }, [api, initialLanguage]);

  const setLanguage = useCallback((next: Language): Promise<boolean> => {
    const generation = generationRef.current;
    if (next === committedRef.current) return Promise.resolve(true);
    setPending(true);
    const operation = queueRef.current.then(async () => {
      try {
        const settings = await api.updateSettings({ language: next });
        if (mountedRef.current && generation === generationRef.current) {
          committedRef.current = settings.language;
          setLanguageState(settings.language);
          return true;
        }
      } catch (error) {
        if (mountedRef.current && generation === generationRef.current) onError(error);
      } finally {
        if (mountedRef.current && generation === generationRef.current) setPending(false);
      }
      return false;
    });
    queueRef.current = operation.then(() => undefined);
    return operation;
  }, [api, onError]);

  return { language, setLanguage, pending };
}
