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
}

type BackendCommand = 'get_backend_connection' | 'retry_backend';

const BACKEND_UNAVAILABLE_MESSAGE = '本地后端不可用，请重试。';
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

  useEffect(() => {
    mountedRef.current = true;
    if (!isTauriRuntime()) return;
    let active = true;
    let unlisten: (() => void) | undefined;

    void (async () => {
      const { listen } = await import('@tauri-apps/api/event');
      const stopListening = await listen('backend-unavailable', () => {
        operationRef.current += 1;
        if (mountedRef.current) {
          setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
        }
      });
      if (!active) {
        stopListening();
        return;
      }
      unlisten = stopListening;
      await bootstrap('get_backend_connection');
    })().catch(() => {
      if (active) {
        setState({ status: 'blocked', message: BACKEND_UNAVAILABLE_MESSAGE });
      }
    });

    return () => {
      active = false;
      mountedRef.current = false;
      operationRef.current += 1;
      unlisten?.();
    };
  }, [bootstrap]);

  const retry = useCallback(
    () => bootstrap('retry_backend'),
    [bootstrap],
  );

  return { state, retry };
}
