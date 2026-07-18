import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { localeFor, translate, translationForError, type Language, type TranslationKey } from './translations';

interface I18nValue {
  language: Language;
  locale: string;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  errorText: (code: string) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ language, children }: { language: Language; children: ReactNode }) {
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo<I18nValue>(() => ({
    language,
    locale: localeFor(language),
    t: (key, params) => translate(language, key, params),
    errorText: code => translationForError(language, code),
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error('useI18n must be used inside I18nProvider');
  return value;
}
