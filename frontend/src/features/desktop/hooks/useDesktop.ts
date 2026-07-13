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
  toggleAutostart: () => Promise<void>;
}

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
    void (async () => {
      try {
        const { isEnabled } = await import('@tauri-apps/plugin-autostart');
        const enabled = await isEnabled();
        if (mountedRef.current) setAutostartEnabled(enabled);
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
          message.includes('BACKEND_UNAVAILABLE')
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

  const toggleAutostart = useCallback(async () => {
    if (!desktop) return;
    try {
      const { enable, disable, isEnabled } = await import('@tauri-apps/plugin-autostart');
      const current = await isEnabled();
      if (current) await disable();
      else await enable();
      if (mountedRef.current) setAutostartEnabled(!current);
    } catch {
      // Keep the last known operating-system state.
    }
  }, [desktop]);

  return {
    isDesktop: desktop,
    shortcut,
    setShortcut,
    autostartEnabled,
    toggleAutostart,
  };
}
