import { useCallback, useEffect, useRef, useState } from 'react';
import { InfrastructureError } from '@/shared/api/contracts';

export const DEFAULT_SHORTCUT = 'Cmd+Alt+KeyT';

function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

interface ShortcutResult {
  ok: boolean;
  error?: string;
}

interface DesktopApi {
  isDesktop: boolean;
  shortcut: string;
  setShortcut: (shortcut: string) => Promise<{ ok: true } | { ok: false; error: string }>;
  autostartEnabled: boolean;
  toggleAutostart: () => Promise<{ ok: true } | { ok: false; error: string }>;
}

const FATAL_SHORTCUT_ERRORS = [
  'BACKEND_UNAVAILABLE',
  'SHORTCUT_ROLLBACK_FAILED',
  'SHORTCUT_CLEANUP_FAILED',
] as const;

export function useDesktop(
  initialShortcut: string,
  onOpenCreateModal: () => void,
  onInfrastructureError: (error: InfrastructureError) => void,
): DesktopApi {
  const desktop = isTauri();
  const [shortcut, setShortcutState] = useState(initialShortcut);
  const [autostartEnabled, setAutostartEnabled] = useState(false);
  const onOpenRef = useRef(onOpenCreateModal);
  const mountedRef = useRef(true);
  const committedRef = useRef(initialShortcut);
  const latestIntentRef = useRef(0);
  const generationRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const autostartCommittedRef = useRef(false);
  const autostartIntentRef = useRef(0);
  const autostartQueueRef = useRef<Promise<void>>(Promise.resolve());
  onOpenRef.current = onOpenCreateModal;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    committedRef.current = initialShortcut;
    latestIntentRef.current += 1;
    generationRef.current += 1;
    queueRef.current = Promise.resolve();
    setShortcutState(initialShortcut);
  }, [initialShortcut]);

  useEffect(() => {
    if (!desktop) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    void (async () => {
      const { listen } = await import('@tauri-apps/api/event');
      const stopListening = await listen('open-create-modal', () => onOpenRef.current());
      if (disposed) stopListening();
      else unlisten = stopListening;
    })();
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [desktop]);

  useEffect(() => {
    if (!desktop) return;
    const intent = autostartIntentRef.current;
    void (async () => {
      try {
        const { isEnabled } = await import('@tauri-apps/plugin-autostart');
        const enabled = await isEnabled();
        if (mountedRef.current && intent === autostartIntentRef.current) {
          autostartCommittedRef.current = enabled;
          setAutostartEnabled(enabled);
        }
      } catch {
        // Autostart remains an optional Tauri-only capability.
      }
    })();
  }, [desktop]);

  const setShortcut = useCallback((next: string) => {
    if (!desktop) {
      return Promise.resolve({ ok: false, error: 'Desktop app required' } as const);
    }
    const intent = ++latestIntentRef.current;
    const generation = generationRef.current;
    const operation = queueRef.current.then(async (): Promise<ShortcutResult> => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        await invoke('set_global_shortcut', { shortcut: next });
        if (mountedRef.current && generation === generationRef.current) {
          committedRef.current = next;
          return { ok: true };
        }
        return { ok: false, error: 'Shortcut request superseded' };
      } catch (error) {
        const message = String(error);
        if (
          FATAL_SHORTCUT_ERRORS.some(code => message.includes(code))
          && mountedRef.current
          && generation === generationRef.current
        ) {
          onInfrastructureError(new InfrastructureError(
            'infrastructure',
            'BACKEND_UNAVAILABLE',
            'Backend unavailable',
          ));
        }
        return { ok: false, error: message };
      } finally {
        if (
          mountedRef.current
          && generation === generationRef.current
          && intent === latestIntentRef.current
        ) {
          setShortcutState(committedRef.current);
        }
      }
    });
    queueRef.current = operation.then(() => undefined);
    return operation.then(result => (
      result.ok ? { ok: true } as const : { ok: false, error: result.error ?? 'Shortcut update failed' } as const
    ));
  }, [desktop, onInfrastructureError]);

  const toggleAutostart = useCallback(() => {
    if (!desktop) {
      return Promise.resolve({ ok: false, error: 'Desktop app required' } as const);
    }
    const intent = ++autostartIntentRef.current;
    const operation = autostartQueueRef.current.then(async () => {
      try {
        const { enable, disable, isEnabled } = await import('@tauri-apps/plugin-autostart');
        const current = await isEnabled();
        if (current) await disable();
        else await enable();
        const confirmed = await isEnabled();
        if (mountedRef.current) autostartCommittedRef.current = confirmed;
        if (mountedRef.current && intent === autostartIntentRef.current) {
          setAutostartEnabled(confirmed);
        }
        return { ok: true } as const;
      } catch (error) {
        if (mountedRef.current && intent === autostartIntentRef.current) {
          setAutostartEnabled(autostartCommittedRef.current);
        }
        return { ok: false, error: String(error) } as const;
      }
    });
    autostartQueueRef.current = operation.then(() => undefined);
    return operation;
  }, [desktop]);

  return {
    isDesktop: desktop,
    shortcut,
    setShortcut,
    autostartEnabled,
    toggleAutostart,
  };
}
