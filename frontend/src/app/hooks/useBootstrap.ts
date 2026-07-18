import { useCallback, useEffect, useRef, useState } from 'react';
import { createTodoApi } from '@/shared/api/client';
import type {
  BackendConnection,
  BootstrapSnapshot,
  SystemTheme,
  TodoApi,
} from '@/shared/api/contracts';

export type BootstrapState =
  | { status: 'loading' }
  | { status: 'unsupported' }
  | { status: 'blocked'; message: string }
  | { status: 'ready'; api: TodoApi; snapshot: BootstrapSnapshot };

interface BootstrapController {
  state: BootstrapState;
  retry: () => Promise<void>;
  block: () => void;
}

type BackendCommand = 'get_backend_connection' | 'retry_backend';

const BACKEND_UNAVAILABLE_MESSAGE = 'BACKEND_UNAVAILABLE';
const defaultFetch: typeof fetch = (...args) => fetch(...args);

export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

function preferredSystemTheme(): SystemTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'workspace-dark'
    : 'workspace-light';
}

export function useBootstrap(fetcher: typeof fetch = defaultFetch): BootstrapController {
  const [state, setState] = useState<BootstrapState>(() => (
    isTauriRuntime() ? { status: 'loading' } : { status: 'unsupported' }
  ));
  const operationRef = useRef(0);
  const mountedRef = useRef(true);
  const listenerGenerationRef = useRef(0);
  const listenerRef = useRef<(() => void) | undefined>(undefined);
  const listenerPromiseRef = useRef<Promise<void> | null>(null);

  const bootstrap = useCallback(async (command: BackendCommand) => {
    if (!isTauriRuntime()) {
      setState({ status: 'unsupported' });
      return;
    }
    const operation = ++operationRef.current;
    setState({ status: 'loading' });
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const connection = await invoke<BackendConnection>(command);
      const api = createTodoApi(connection, fetcher);
      const snapshot = await api.bootstrap(preferredSystemTheme());
      if (mountedRef.current && operationRef.current === operation) {
        setState({ status: 'ready', api, snapshot });
      }
    } catch {
      if (mountedRef.current && operationRef.current === operation) {
        setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
      }
    }
  }, [fetcher]);

  const ensureBackendListener = useCallback((): Promise<void> => {
    if (listenerRef.current) return Promise.resolve();
    if (listenerPromiseRef.current) return listenerPromiseRef.current;

    const generation = listenerGenerationRef.current;
    const registration = (async () => {
      const { listen } = await import('@tauri-apps/api/event');
      const unlisten = await listen('backend-unavailable', () => {
        if (!mountedRef.current || listenerGenerationRef.current !== generation) return;
        operationRef.current += 1;
        setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
      });
      if (!mountedRef.current || listenerGenerationRef.current !== generation) {
        unlisten();
        return;
      }
      listenerRef.current = unlisten;
    })();
    listenerPromiseRef.current = registration;
    void registration.then(
      () => {
        if (listenerPromiseRef.current === registration) listenerPromiseRef.current = null;
      },
      () => {
        if (listenerPromiseRef.current === registration) listenerPromiseRef.current = null;
      },
    );
    return registration;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!isTauriRuntime()) return;
    const generation = ++listenerGenerationRef.current;
    let active = true;

    void (async () => {
      await ensureBackendListener();
      if (!active || listenerGenerationRef.current !== generation) return;
      await bootstrap('get_backend_connection');
    })().catch(() => {
      if (active && listenerGenerationRef.current === generation) {
        setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
      }
    });

    return () => {
      active = false;
      mountedRef.current = false;
      operationRef.current += 1;
      listenerGenerationRef.current += 1;
      listenerPromiseRef.current = null;
      const unlisten = listenerRef.current;
      listenerRef.current = undefined;
      unlisten?.();
    };
  }, [bootstrap, ensureBackendListener]);

  const retry = useCallback(async () => {
    if (!isTauriRuntime()) {
      setState({ status: 'unsupported' });
      return;
    }
    const generation = listenerGenerationRef.current;
    try {
      await ensureBackendListener();
      if (!mountedRef.current || listenerGenerationRef.current !== generation) return;
      await bootstrap('retry_backend');
    } catch {
      if (mountedRef.current && listenerGenerationRef.current === generation) {
        setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
      }
    }
  }, [bootstrap, ensureBackendListener]);

  const block = useCallback(() => {
    operationRef.current += 1;
    setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
  }, []);

  return { state, retry, block };
}
