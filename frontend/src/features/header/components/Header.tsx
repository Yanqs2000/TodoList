import '../styles/Header.css';
import '../styles/ThemeToggle.css';
import { useI18n } from '@/features/i18n/I18nProvider';

interface HeaderProps {
  onOpenAchievements: () => void;
  onOpenCreateModal: () => void;
  onOpenSettings: () => void;
  muted: boolean;
  onToggleMuted: () => void;
  onToggleLanguage: () => void;
  languagePending: boolean;
}

function Header({
  onOpenAchievements,
  onOpenCreateModal,
  onOpenSettings,
  muted,
  onToggleMuted,
  onToggleLanguage,
  languagePending,
}: HeaderProps) {
  const { language, t } = useI18n();
  return (
    <header className="app-header">
      <div className="app-header__brand">
        <span className="app-header__logo" aria-hidden>✓</span>
        <span className="app-header__title">Todo List</span>
      </div>

      <button
        className="app-header__new-btn"
        onClick={onOpenCreateModal}
        title={t('header.newTaskTitle')}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        <span>{t('header.newTask')}</span>
        <kbd className="app-header__kbd">⌘N</kbd>
      </button>

      <div className="app-header__actions">
        <button
          className="app-header__language-btn"
          onClick={onToggleLanguage}
          disabled={languagePending}
          aria-label={language === 'zh-CN' ? t('header.switchToEnglish') : t('header.switchToChinese')}
          title={language === 'zh-CN' ? t('header.switchToEnglish') : t('header.switchToChinese')}
        >
          {language === 'zh-CN' ? 'EN' : t('header.chineseLabel')}
        </button>
        <button
          className="icon-btn"
          onClick={onToggleMuted}
          aria-label={muted ? t('header.soundOn') : t('header.soundOff')}
          title={muted ? t('header.soundOn') : t('header.soundOff')}
        >
          {muted ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75 19.5 12m0 0 2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6 4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 0 1 2.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75Z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 0 1 0 12.728M16.463 8.288a5.25 5.25 0 0 1 0 7.424M6.75 8.25l4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 0 1 2.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75Z" />
            </svg>
          )}
        </button>

        <button
          className="icon-btn"
          onClick={onOpenAchievements}
          aria-label={t('header.achievements')}
          title={t('header.achievements')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-4.5A3.375 3.375 0 0 0 19.875 10.875 3.375 3.375 0 0 0 16.5 7.5h0a3.375 3.375 0 0 0-3.375 3.375v0A3.375 3.375 0 0 1 9.75 7.5h0a3.375 3.375 0 0 0-3.375 3.375 3.375 3.375 0 0 0-3.375 3.375V18.75m9 0h-9" />
          </svg>
        </button>

        <button
          className="icon-btn"
          onClick={onOpenSettings}
          aria-label={t('header.settings')}
          title={t('header.settingsTitle')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
          </svg>
        </button>
      </div>
    </header>
  );
}

export default Header;
