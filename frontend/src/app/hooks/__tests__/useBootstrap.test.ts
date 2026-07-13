import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BootstrapSnapshot } from '@/shared/api/contracts';
import { isTauriRuntime, useBootstrap } from '../useBootstrap';

const tauriMocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({ invoke: tauriMocks.invoke }));
vi.mock('@tauri-apps/api/event', () => ({ listen: tauriMocks.listen }));

const FIRST_SNAPSHOT: BootstrapSnapshot = {
  tasks: [{
    id: 'first',
    text: 'first snapshot',
    completed: false,
    priority: 'medium',
    createdAt: 1,
    category: 'other',
  }],
  settings: {
    theme: 'workspace-dark',
    muted: false,
    shortcut: 'Cmd+Alt+KeyT',
  },
  achievementState: {
    unlocked: [],
    streakDays: 0,
    lastActiveDate: '',
    todayCompleted: 0,
    todayDate: '',
  },
};

const RETRY_SNAPSHOT: BootstrapSnapshot = {
  ...FIRST_SNAPSHOT,
  tasks: [{
    id: 'retry',
    text: 'replacement snapshot',
    completed: true,
    priority: 'high',
    createdAt: 2,
    category: 'work',
  }],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setTauriRuntime(enabled: boolean): void {
  if (enabled) {
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      configurable: true,
      value: {},
    });
  } else {
    Reflect.deleteProperty(window, '__TAURI_INTERNALS__');
  }
}

describe('useBootstrap', () => {
  let backendUnavailable: (() => void) | undefined;

  beforeEach(() => {
    vi.restoreAllMocks();
    tauriMocks.invoke.mockReset();
    tauriMocks.listen.mockReset();
    backendUnavailable = undefined;
    setTauriRuntime(false);
    tauriMocks.listen.mockImplementation(async (
      event: string,
      handler: () => void,
    ) => {
      if (event === 'backend-unavailable') backendUnavailable = handler;
      return vi.fn();
    });
  });

  it('detects Tauri only when its runtime internals are present', () => {
    expect(isTauriRuntime()).toBe(false);
    setTauriRuntime(true);
    expect(isTauriRuntime()).toBe(true);
  });

  it('returns unsupported in an ordinary browser without invoking desktop commands', () => {
    const { result } = renderHook(() => useBootstrap());

    expect(result.current.state).toEqual({ status: 'unsupported' });
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
  });

  it('discovers the connection and bootstraps with the system dark preference', async () => {
    setTauriRuntime(true);
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList);
    tauriMocks.invoke.mockResolvedValue({
      baseUrl: 'http://127.0.0.1:43123',
      token: 'first-token',
    });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(FIRST_SNAPSHOT));

    const { result } = renderHook(() => useBootstrap(fetcher));

    expect(result.current.state).toEqual({ status: 'loading' });
    await waitFor(() => expect(result.current.state.status).toBe('ready'));
    expect(tauriMocks.invoke).toHaveBeenCalledWith('get_backend_connection');
    expect(fetcher).toHaveBeenCalledWith(
      'http://127.0.0.1:43123/api/v1/bootstrap',
      expect.objectContaining({
        body: JSON.stringify({ preferredTheme: 'workspace-dark' }),
      }),
    );
    expect(result.current.state).toMatchObject({
      status: 'ready',
      snapshot: FIRST_SNAPSHOT,
    });
  });

  it('blocks immediately when the sidecar-unavailable event arrives', async () => {
    setTauriRuntime(true);
    tauriMocks.invoke.mockResolvedValue({
      baseUrl: 'http://127.0.0.1:43123',
      token: 'first-token',
    });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(FIRST_SNAPSHOT));
    const { result } = renderHook(() => useBootstrap(fetcher));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    act(() => backendUnavailable?.());

    expect(result.current.state).toEqual({
      status: 'blocked',
      message: '本地后端不可用，请重试。',
    });
  });

  it('retries through Tauri and replaces the complete in-memory snapshot', async () => {
    setTauriRuntime(true);
    tauriMocks.invoke.mockImplementation(async (command: string) => (
      command === 'retry_backend'
        ? { baseUrl: 'http://127.0.0.1:43124', token: 'retry-token' }
        : { baseUrl: 'http://127.0.0.1:43123', token: 'first-token' }
    ));
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(FIRST_SNAPSHOT))
      .mockResolvedValueOnce(jsonResponse(RETRY_SNAPSHOT));
    const { result } = renderHook(() => useBootstrap(fetcher));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));
    act(() => backendUnavailable?.());

    await act(async () => {
      await result.current.retry();
    });

    expect(tauriMocks.invoke).toHaveBeenLastCalledWith('retry_backend');
    expect(result.current.state).toMatchObject({
      status: 'ready',
      snapshot: RETRY_SNAPSHOT,
    });
    if (result.current.state.status === 'ready') {
      expect(result.current.state.snapshot.tasks.map(task => task.id)).toEqual(['retry']);
    }
    expect(fetcher.mock.calls[1]?.[0]).toBe('http://127.0.0.1:43124/api/v1/bootstrap');
  });
});
