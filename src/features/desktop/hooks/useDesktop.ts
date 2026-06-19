import { useEffect, useCallback, useState, useRef } from 'react';
import { safeSetItem, safeGetItem } from '@/shared/lib/storage';

const SHORTCUT_KEY = 'todo-shortcut';
export const DEFAULT_SHORTCUT = 'Alt+Space';

/**
 * Detects whether the app is running inside Tauri. We avoid hard-importing the
 * Tauri APIs at module top-level so the web build still works (e.g. `npm run dev`
 * in a regular browser, or running tests under jsdom).
 */
function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

interface DesktopApi {
  isDesktop: boolean;
  shortcut: string;
  setShortcut: (s: string) => Promise<{ ok: true } | { ok: false; error: string }>;
  autostartEnabled: boolean;
  toggleAutostart: () => Promise<void>;
}

/**
 * Bridges renderer <-> Tauri for desktop-only features:
 * - listens for the `open-create-modal` event (fired by the global shortcut and tray menu)
 * - reads/writes the configured global shortcut
 * - reads/writes the auto-start preference
 *
 * On non-Tauri environments (web preview / tests), `isDesktop` is false and all
 * mutators are no-ops. The hook still returns sensible defaults so callers don't
 * need null checks for every field.
 */
export function useDesktop(onOpenCreateModal: () => void): DesktopApi {
  const desktop = isTauri();
  const [shortcut, setShortcutState] = useState<string>(
    () => safeGetItem(SHORTCUT_KEY) ?? DEFAULT_SHORTCUT,
  );
  const [autostartEnabled, setAutostartEnabled] = useState(false);

  const onOpenRef = useRef(onOpenCreateModal);
  onOpenRef.current = onOpenCreateModal;

  // Listen for the open-create-modal event from Rust.
  useEffect(() => {
    if (!desktop) return;
    let unlisten: (() => void) | undefined;
    (async () => {
      const { listen } = await import('@tauri-apps/api/event');
      unlisten = await listen('open-create-modal', () => {
        onOpenRef.current();
      });
    })();
    return () => {
      unlisten?.();
    };
  }, [desktop]);

  // Read current autostart state on mount.
  useEffect(() => {
    if (!desktop) return;
    (async () => {
      try {
        const { isEnabled } = await import('@tauri-apps/plugin-autostart');
        setAutostartEnabled(await isEnabled());
      } catch {
        // ignore — plugin not available
      }
    })();
  }, [desktop]);

  // If the user has a stored shortcut different from the default, apply it on launch.
  useEffect(() => {
    if (!desktop) return;
    const stored = safeGetItem(SHORTCUT_KEY);
    if (!stored || stored === DEFAULT_SHORTCUT) return;
    (async () => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        await invoke('set_global_shortcut', { shortcut: stored });
      } catch {
        // fall back to default; surface no error since it's startup
      }
    })();
  }, [desktop]);

  const setShortcut = useCallback(async (next: string): Promise<{ ok: true } | { ok: false; error: string }> => {
    if (!desktop) {
      setShortcutState(next);
      safeSetItem(SHORTCUT_KEY, next);
      return { ok: true };
    }
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('set_global_shortcut', { shortcut: next });
      setShortcutState(next);
      safeSetItem(SHORTCUT_KEY, next);
      return { ok: true };
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  }, [desktop]);

  const toggleAutostart = useCallback(async () => {
    if (!desktop) return;
    try {
      const { enable, disable, isEnabled } = await import('@tauri-apps/plugin-autostart');
      const current = await isEnabled();
      if (current) {
        await disable();
      } else {
        await enable();
      }
      setAutostartEnabled(!current);
    } catch {
      // ignore
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
