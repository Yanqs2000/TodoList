import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import './ConfirmDialog.css';
import { useI18n } from '@/features/i18n/I18nProvider';

export interface ConfirmOptions {
  title: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  /** When true, the confirm button uses the danger (red) accent. */
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

/**
 * Imperative confirm dialog. Returns a promise resolving to `true` if the user
 * confirmed, `false` otherwise (cancel / Esc / overlay click).
 *
 * Replaces `window.confirm`, which is silently dropped by some WebView hosts
 * (Tauri on certain configs, jsdom) — that was the root cause of the
 * "clear completed / delete button does nothing" bug.
 */
export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext);
}

interface PendingState extends ConfirmOptions {
  resolve: (v: boolean) => void;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [pending, setPending] = useState<PendingState | null>(null);
  const resolverRef = useRef<((v: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      // If a previous dialog is somehow still open, resolve it as cancelled.
      resolverRef.current?.(false);
      resolverRef.current = resolve;
      setPending({ ...opts, resolve });
    });
  }, []);

  const close = useCallback((result: boolean) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setPending(null);
  }, []);

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [pending, close]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && createPortal(
        <div
          className="confirm__overlay"
          onMouseDown={(e) => { if (e.target === e.currentTarget) close(false); }}
        >
          <div
            className="confirm__card"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <h3 id="confirm-title" className="confirm__title">{pending.title}</h3>
            {pending.message && <p className="confirm__message">{pending.message}</p>}
            <div className="confirm__actions">
              <button
                type="button"
                className="confirm__btn confirm__btn--cancel"
                onClick={() => close(false)}
              >
                {pending.cancelText ?? t('common.cancel')}
              </button>
              <button
                type="button"
                className={`confirm__btn confirm__btn--confirm${pending.danger ? ' confirm__btn--danger' : ''}`}
                onClick={() => close(true)}
                // Autofocus so Enter confirms; Esc cancels (handled above).
                ref={(el) => el?.focus()}
              >
                {pending.confirmText ?? t('common.confirm')}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </ConfirmContext.Provider>
  );
}
