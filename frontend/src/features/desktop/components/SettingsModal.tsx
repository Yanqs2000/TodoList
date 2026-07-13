import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { DEFAULT_SHORTCUT } from '../hooks/useDesktop';
import { THEME_IDS, THEMES, type ThemeId } from '@/features/theme/hooks/useTheme';
import '../styles/SettingsModal.css';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  isDesktop: boolean;
  shortcut: string;
  onSetShortcut: (s: string) => Promise<{ ok: true } | { ok: false; error: string }>;
  autostartEnabled: boolean;
  onToggleAutostart: () => Promise<{ ok: true } | { ok: false; error: string }>;
  currentTheme: ThemeId;
  onSelectTheme: (id: ThemeId) => void;
}

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

/**
 * Convert a Tauri accelerator string ("CmdOrCtrl+Alt+KeyT") into a human-readable
 * label. On macOS: ⌘⌥⇧⌃; on Windows/Linux: spelled-out modifiers.
 */
function formatShortcut(accel: string): string {
  if (!accel) return '';
  return accel
    .split('+')
    .map(part => {
      const norm = part.trim();
      if (IS_MAC) {
        switch (norm) {
          case 'CmdOrCtrl':
          case 'Cmd':
          case 'Command':
          case 'Super':
            return '⌘';
          case 'Ctrl':
          case 'Control':
            return '⌃';
          case 'Alt':
          case 'Option':
            return '⌥';
          case 'Shift':
            return '⇧';
        }
      } else {
        switch (norm) {
          case 'CmdOrCtrl': return 'Ctrl';
          case 'Cmd':
          case 'Command':
          case 'Super':
            return 'Win';
          case 'Alt':
          case 'Option':
            return 'Alt';
        }
      }
      // Strip Key/Digit prefixes for display.
      if (norm.startsWith('Key') && norm.length === 4) return norm.slice(3);
      if (norm.startsWith('Digit') && norm.length === 6) return norm.slice(5);
      return norm;
    })
    .join(IS_MAC ? '' : '+');
}

/**
 * Build a Tauri accelerator string from a native KeyboardEvent. Uses code-prefixed
 * names (KeyT, Digit1) so the parser unambiguously routes through global-hotkey's
 * Code map. Returns null if only modifiers are pressed.
 */
function eventToAccelerator(e: KeyboardEvent): string | null {
  const parts: string[] = [];
  if (e.metaKey) parts.push('Cmd');
  if (e.ctrlKey) parts.push('Ctrl');
  if (e.altKey) parts.push('Alt');
  if (e.shiftKey) parts.push('Shift');

  const code = e.code;
  if (
    code === 'MetaLeft' || code === 'MetaRight' ||
    code === 'ControlLeft' || code === 'ControlRight' ||
    code === 'AltLeft' || code === 'AltRight' ||
    code === 'ShiftLeft' || code === 'ShiftRight' ||
    !code
  ) {
    return null;
  }

  // Need at least one modifier for a global shortcut to be useful.
  if (parts.length === 0) return null;

  parts.push(code);
  return parts.join('+');
}

function SettingsModal({
  open,
  onClose,
  isDesktop,
  shortcut,
  onSetShortcut,
  autostartEnabled,
  onToggleAutostart,
  currentTheme,
  onSelectTheme,
}: SettingsModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [recording, setRecording] = useState(false);
  const [pendingShortcut, setPendingShortcut] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recordingRef = useRef(recording);
  recordingRef.current = recording;

  // Document-level capture: we MUST swallow the keys before the browser/OS
  // processes them (Cmd+T would otherwise trigger "new tab" intercept etc.).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (recordingRef.current) {
        // Ignore pure-modifier presses; wait for a primary key.
        const accel = eventToAccelerator(e);
        e.preventDefault();
        e.stopPropagation();
        if (accel) {
          setPendingShortcut(accel);
          setRecording(false);
          setError(null);
        }
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    // capture: true → run before any inline React handler / browser default
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      setRecording(false);
      setPendingShortcut(null);
      setError(null);
    }
  }, [open]);

  const handleOverlayMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const handleApply = useCallback(async () => {
    if (!pendingShortcut) return;
    setError(null);
    const result = await onSetShortcut(pendingShortcut);
    if (result.ok) {
      setPendingShortcut(null);
    } else {
      setError(result.error);
    }
  }, [pendingShortcut, onSetShortcut]);

  const handleReset = useCallback(async () => {
    setError(null);
    const result = await onSetShortcut(DEFAULT_SHORTCUT);
    if (result.ok) {
      setPendingShortcut(null);
    } else {
      setError(result.error);
    }
  }, [onSetShortcut]);

  const handleToggleAutostart = useCallback(async () => {
    setError(null);
    const result = await onToggleAutostart();
    if (!result.ok) setError(result.error);
  }, [onToggleAutostart]);

  if (!open) return null;

  const displayShortcut = pendingShortcut ?? shortcut;
  const hasPending = pendingShortcut !== null && pendingShortcut !== shortcut;

  return createPortal(
    <div className="settings-modal__overlay" onMouseDown={handleOverlayMouseDown}>
      <div
        className="settings-modal__card"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="设置"
      >
        <header className="settings-modal__header">
          <h2 className="settings-modal__title">设置</h2>
          <button
            type="button"
            className="settings-modal__close"
            onClick={onClose}
            aria-label="关闭"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        {/* ---------- 主题 ---------- */}
        <section className="settings-modal__section">
          <div className="settings-modal__section-title">外观主题</div>
          <div className="settings-modal__section-desc">3 种风格 × 2 种明暗 = 6 套主题</div>
          <div className="settings-modal__theme-grid">
            {THEME_IDS.map((id) => {
              const meta = THEMES[id];
              const active = currentTheme === id;
              return (
                <button
                  key={id}
                  type="button"
                  className={`settings-modal__theme-card${active ? ' settings-modal__theme-card--active' : ''}`}
                  onClick={() => onSelectTheme(id)}
                  aria-pressed={active}
                >
                  <div
                    className="settings-modal__theme-swatch"
                    style={{ background: meta.swatch.bg }}
                  >
                    <span
                      className="settings-modal__theme-dot"
                      style={{ background: meta.swatch.card, right: 26 }}
                    />
                    <span
                      className="settings-modal__theme-dot"
                      style={{ background: meta.swatch.accent, right: 8 }}
                    />
                  </div>
                  <div className="settings-modal__theme-name">{meta.name}</div>
                  <div className="settings-modal__theme-desc">{meta.description}</div>
                  {active && (
                    <span className="settings-modal__theme-check">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </section>

        {/* ---------- 桌面 ---------- */}
        <section className="settings-modal__section">
          <div className="settings-modal__section-title">桌面</div>
          {!isDesktop && (
            <p className="settings-modal__hint">
              桌面专属设置仅在 Tauri 桌面版本中可用。当前为 Web 版，下方设置已禁用。
            </p>
          )}

          <div className="settings-modal__row">
            <div>
              <div className="settings-modal__label">全局快捷键</div>
              <div className="settings-modal__desc">
                在任意应用按下此组合，可快速弹出新建任务
                {IS_MAC && '（macOS 的 Option = ⌥）'}
              </div>
            </div>
            <div className="settings-modal__shortcut">
              <button
                type="button"
                className={`settings-modal__kbd${recording ? ' settings-modal__kbd--recording' : ''}`}
                onClick={() => isDesktop && setRecording(true)}
                disabled={!isDesktop}
              >
                {recording ? '请按下组合键…' : formatShortcut(displayShortcut)}
              </button>
              {hasPending && (
                <button type="button" className="settings-modal__btn" onClick={handleApply}>
                  应用
                </button>
              )}
              <button
                type="button"
                className="settings-modal__btn settings-modal__btn--ghost"
                onClick={handleReset}
                disabled={!isDesktop || (shortcut === DEFAULT_SHORTCUT && !pendingShortcut)}
              >
                恢复默认
              </button>
            </div>
          </div>
          {error && <div className="settings-modal__error">{error}</div>}

          <div className="settings-modal__row">
            <div>
              <div className="settings-modal__label">开机自动启动</div>
              <div className="settings-modal__desc">登录系统时自动后台运行 Todo List</div>
            </div>
            <label className={`settings-modal__switch${autostartEnabled ? ' settings-modal__switch--on' : ''}${!isDesktop ? ' settings-modal__switch--disabled' : ''}`}>
              <input
                type="checkbox"
                checked={autostartEnabled}
                onChange={() => { void handleToggleAutostart(); }}
                disabled={!isDesktop}
                aria-label="开机自启动"
              />
              <span className="settings-modal__switch-knob" />
            </label>
          </div>
        </section>
      </div>
    </div>,
    document.body,
  );
}

export default SettingsModal;
