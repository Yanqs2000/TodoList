import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { THEME_IDS, THEMES } from '@/features/theme/hooks/useTheme';
import type { ThemeId } from '@/features/theme/hooks/useTheme';
import '../styles/ThemeSwitcher.css';

interface ThemeSwitcherProps {
  open: boolean;
  currentTheme: ThemeId;
  onClose: () => void;
  onSelect: (id: ThemeId) => void;
}

function ThemeSwitcher({ open, currentTheme, onClose, onSelect }: ThemeSwitcherProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Esc to close
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  // Focus the current theme card when the modal opens
  useEffect(() => {
    if (!open) return;
    const modal = modalRef.current;
    if (!modal) return;
    const active = modal.querySelector<HTMLButtonElement>(
      `[data-theme-id="${currentTheme}"]`
    );
    const target = active ?? modal.querySelector<HTMLButtonElement>('[data-card]');
    target?.focus();
  }, [open, currentTheme]);

  if (!open) return null;

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  const handleModalKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab' || !modalRef.current) return;
    const focusables = Array.from(
      modalRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter(el => !el.hasAttribute('disabled'));
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement as HTMLElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div className="theme-switcher">
      <div className="theme-switcher__overlay" onClick={handleOverlayClick} />
      <div
        className="theme-switcher__modal"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="选择主题"
        onKeyDown={handleModalKeyDown}
      >
        <div className="theme-switcher__header">
          <h2 className="theme-switcher__title">选择主题</h2>
          <button
            type="button"
            className="theme-switcher__close"
            onClick={onClose}
            aria-label="关闭"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p className="theme-switcher__subtitle">3 种风格 × 2 种明暗</p>
        <div className="theme-switcher__grid">
          {THEME_IDS.map(id => {
            const meta = THEMES[id];
            const isActive = id === currentTheme;
            return (
              <button
                key={id}
                type="button"
                data-card
                data-theme-id={id}
                className={`theme-switcher__card${isActive ? ' theme-switcher__card--active' : ''}`}
                onClick={() => onSelect(id)}
                aria-pressed={isActive}
                aria-label={`${meta.name}，${meta.description}`}
              >
                <div className="theme-switcher__swatch">
                  <span
                    className="theme-switcher__swatch-bg"
                    style={{ background: meta.swatch.bg }}
                  />
                  <span
                    className="theme-switcher__swatch-dot theme-switcher__swatch-dot--card"
                    style={{ background: meta.swatch.card }}
                  />
                  <span
                    className="theme-switcher__swatch-dot"
                    style={{ background: meta.swatch.accent }}
                  />
                </div>
                <span className="theme-switcher__name">{meta.name}</span>
                <span className="theme-switcher__desc">{meta.description}</span>
                {isActive && (
                  <span className="theme-switcher__check" aria-hidden="true">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <p className="theme-switcher__hint">选择会立即生效并保存</p>
      </div>
    </div>,
    document.body
  );
}

export default ThemeSwitcher;
