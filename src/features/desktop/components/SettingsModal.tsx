import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { DEFAULT_SHORTCUT } from '../hooks/useDesktop';
import '../styles/SettingsModal.css';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  isDesktop: boolean;
  shortcut: string;
  onSetShortcut: (s: string) => Promise<{ ok: true } | { ok: false; error: string }>;
  autostartEnabled: boolean;
  onToggleAutostart: () => void;
}

/**
 * Builds a Tauri-compatible accelerator string from a KeyboardEvent. Returns
 * null if only modifiers are pressed (i.e. user hasn't picked a primary key
 * yet). Tauri uses "Alt+Space", "CmdOrCtrl+Shift+N", etc.
 */
function eventToAccelerator(e: React.KeyboardEvent): string | null {
  const parts: string[] = [];
  if (e.metaKey) parts.push('CmdOrCtrl');
  if (e.ctrlKey && !e.metaKey) parts.push('CmdOrCtrl');
  if (e.altKey) parts.push('Alt');
  if (e.shiftKey) parts.push('Shift');

  // Skip pure-modifier keys.
  const code = e.code;
  if (
    code === 'MetaLeft' || code === 'MetaRight' ||
    code === 'ControlLeft' || code === 'ControlRight' ||
    code === 'AltLeft' || code === 'AltRight' ||
    code === 'ShiftLeft' || code === 'ShiftRight'
  ) {
    return null;
  }

  // Tauri accepts e.g. Space, KeyA → A, Digit1 → 1, F1, Enter, Escape, ArrowUp …
  let key = code;
  if (key.startsWith('Key')) key = key.slice(3);
  else if (key.startsWith('Digit')) key = key.slice(5);
  parts.push(key);
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
}: SettingsModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [recording, setRecording] = useState(false);
  const [pendingShortcut, setPendingShortcut] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !recording) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose, recording]);

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

  const handleRecordKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!recording) return;
    e.preventDefault();
    e.stopPropagation();
    const accel = eventToAccelerator(e);
    if (!accel) return;
    setPendingShortcut(accel);
    setRecording(false);
  }, [recording]);

  const handleApply = async () => {
    if (!pendingShortcut) return;
    setError(null);
    const result = await onSetShortcut(pendingShortcut);
    if (result.ok) {
      setPendingShortcut(null);
    } else {
      setError(result.error);
    }
  };

  const handleReset = async () => {
    setError(null);
    const result = await onSetShortcut(DEFAULT_SHORTCUT);
    if (result.ok) {
      setPendingShortcut(null);
    } else {
      setError(result.error);
    }
  };

  if (!open) return null;

  return createPortal(
    <div className="settings-modal__overlay" onMouseDown={handleOverlayMouseDown}>
      <div
        className="settings-modal__card"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="桌面设置"
      >
        <header className="settings-modal__header">
          <h2 className="settings-modal__title">桌面设置</h2>
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

        {!isDesktop && (
          <p className="settings-modal__hint">
            桌面专属设置仅在 Tauri 桌面版本中可用。当前为 Web 版，下方设置已禁用。
          </p>
        )}

        <section className="settings-modal__section">
          <div className="settings-modal__row">
            <div>
              <div className="settings-modal__label">全局快捷键</div>
              <div className="settings-modal__desc">在任意应用按下此组合，可快速弹出新建任务</div>
            </div>
            <div className="settings-modal__shortcut">
              <button
                type="button"
                className={`settings-modal__kbd${recording ? ' settings-modal__kbd--recording' : ''}`}
                onClick={() => isDesktop && setRecording(true)}
                onKeyDown={handleRecordKeyDown}
                disabled={!isDesktop}
              >
                {recording ? '请按下组合键…' : (pendingShortcut ?? shortcut)}
              </button>
              {pendingShortcut && pendingShortcut !== shortcut && (
                <button type="button" className="settings-modal__btn" onClick={handleApply}>
                  应用
                </button>
              )}
              <button
                type="button"
                className="settings-modal__btn settings-modal__btn--ghost"
                onClick={handleReset}
                disabled={!isDesktop || shortcut === DEFAULT_SHORTCUT}
              >
                恢复默认
              </button>
            </div>
          </div>
          {error && <div className="settings-modal__error">{error}</div>}
        </section>

        <section className="settings-modal__section">
          <div className="settings-modal__row">
            <div>
              <div className="settings-modal__label">开机自动启动</div>
              <div className="settings-modal__desc">登录系统时自动后台运行 Todo List</div>
            </div>
            <label className={`settings-modal__switch${autostartEnabled ? ' settings-modal__switch--on' : ''}${!isDesktop ? ' settings-modal__switch--disabled' : ''}`}>
              <input
                type="checkbox"
                checked={autostartEnabled}
                onChange={onToggleAutostart}
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
