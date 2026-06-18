import type { ThemeId } from '@/features/theme/hooks/useTheme';
import '../styles/Header.css';
import '../styles/ThemeToggle.css';

interface HeaderProps {
  theme: ThemeId;
  onOpenThemeSwitcher: () => void;
  onOpenAchievements: () => void;
  onOpenCreateModal: () => void;
  muted: boolean;
  onToggleMuted: () => void;
  onExport: () => void;
  onImport: () => void;
}

function Header({
  theme,
  onOpenThemeSwitcher,
  onOpenAchievements,
  onOpenCreateModal,
  muted,
  onToggleMuted,
  onExport,
  onImport,
}: HeaderProps) {
  const isDark = theme.endsWith('-dark');

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <span className="app-header__logo" aria-hidden>✓</span>
        <span className="app-header__title">Todo List</span>
      </div>

      <button
        className="app-header__new-btn"
        onClick={onOpenCreateModal}
        title="新建任务 (Cmd+N)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        <span>新建任务</span>
        <kbd className="app-header__kbd">⌘N</kbd>
      </button>

      <div className="app-header__actions">
        <button
          className="icon-btn"
          onClick={onToggleMuted}
          aria-label={muted ? '开启音效' : '关闭音效'}
          title={muted ? '开启音效' : '关闭音效'}
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
          aria-label="成就"
          title="成就"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-4.5A3.375 3.375 0 0 0 19.875 10.875 3.375 3.375 0 0 0 16.5 7.5h0a3.375 3.375 0 0 0-3.375 3.375v0A3.375 3.375 0 0 1 9.75 7.5h0a3.375 3.375 0 0 0-3.375 3.375 3.375 3.375 0 0 0-3.375 3.375V18.75m9 0h-9" />
          </svg>
        </button>

        <button className="icon-btn" onClick={onExport} aria-label="导出" title="导出任务">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
        </button>

        <button className="icon-btn" onClick={onImport} aria-label="导入" title="导入任务">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 7.5m0 0L7.5 12m4.5-4.5V21" />
          </svg>
        </button>

        <button
          className="icon-btn theme-toggle"
          onClick={onOpenThemeSwitcher}
          aria-label="切换主题"
          title="主题选择"
        >
          {isDark ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  );
}

export default Header;
