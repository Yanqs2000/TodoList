import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { localeFor, translate, translationForError, type Language, type TranslationKey } from './translations';

interface I18nValue {
  language: Language;
  locale: string;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  errorText: (code: string) => string;
}

const defaultValue: I18nValue = {
  language: 'zh-CN',
  locale: localeFor('zh-CN'),
  t: (key, params) => translate('zh-CN', key, params),
  errorText: code => translationForError('zh-CN', code),
};

const I18nContext = createContext<I18nValue>(defaultValue);

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
  return useContext(I18nContext);
}
