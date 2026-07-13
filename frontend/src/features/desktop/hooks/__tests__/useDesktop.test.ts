import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useDesktop } from '../useDesktop';

const tauriMocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn().mockResolvedValue(vi.fn()),
  isEnabled: vi.fn().mockResolvedValue(false),
  enable: vi.fn(),
  disable: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({ invoke: tauriMocks.invoke }));
vi.mock('@tauri-apps/api/event', () => ({ listen: tauriMocks.listen }));
vi.mock('@tauri-apps/plugin-autostart', () => ({
  isEnabled: tauriMocks.isEnabled,
  enable: tauriMocks.enable,
  disable: tauriMocks.disable,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => { resolve = res; });
  return { promise, resolve };
}

describe('useDesktop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      configurable: true,
      value: { invoke: tauriMocks.invoke },
    });
    tauriMocks.listen.mockResolvedValue(vi.fn());
    tauriMocks.isEnabled.mockResolvedValue(false);
  });

  it('initializes the shortcut from bootstrap without registering it again', async () => {
    const { result } = renderHook(() => useDesktop('Cmd+Shift+KeyK', vi.fn(), vi.fn()));

    expect(result.current.shortcut).toBe('Cmd+Shift+KeyK');
    await waitFor(() => expect(tauriMocks.listen).toHaveBeenCalled());
    expect(tauriMocks.invoke).not.toHaveBeenCalled();
  });

  it('publishes a shortcut only after the transactional Rust command succeeds', async () => {
    const request = deferred<void>();
    tauriMocks.invoke.mockReturnValueOnce(request.promise);
    const { result } = renderHook(() => useDesktop('Cmd+Alt+KeyT', vi.fn(), vi.fn()));

    let change!: Promise<{ ok: true } | { ok: false; error: string }>;
    act(() => { change = result.current.setShortcut('Cmd+Shift+KeyK'); });
    expect(result.current.shortcut).toBe('Cmd+Alt+KeyT');

    await act(async () => request.resolve());

    await expect(change).resolves.toEqual({ ok: true });
    expect(result.current.shortcut).toBe('Cmd+Shift+KeyK');
    expect(tauriMocks.invoke).toHaveBeenCalledWith('set_global_shortcut', {
      shortcut: 'Cmd+Shift+KeyK',
    });
  });

  it('keeps the prior shortcut when Rust rolls back a business failure', async () => {
    tauriMocks.invoke.mockRejectedValueOnce('invalid shortcut');
    const onInfrastructureError = vi.fn();
    const { result } = renderHook(() => useDesktop(
      'Cmd+Alt+KeyT',
      vi.fn(),
      onInfrastructureError,
    ));

    let response!: { ok: true } | { ok: false; error: string };
    await act(async () => { response = await result.current.setShortcut('bad'); });

    expect(response).toEqual({ ok: false, error: 'invalid shortcut' });
    expect(result.current.shortcut).toBe('Cmd+Alt+KeyT');
    expect(onInfrastructureError).not.toHaveBeenCalled();
  });

  it('blocks on backend failure and keeps the prior shortcut', async () => {
    tauriMocks.invoke.mockRejectedValueOnce('BACKEND_UNAVAILABLE');
    const onInfrastructureError = vi.fn();
    const { result } = renderHook(() => useDesktop(
      'Cmd+Alt+KeyT',
      vi.fn(),
      onInfrastructureError,
    ));

    await act(async () => { await result.current.setShortcut('Cmd+Shift+KeyK'); });

    expect(result.current.shortcut).toBe('Cmd+Alt+KeyT');
    expect(onInfrastructureError).toHaveBeenCalledTimes(1);
  });
});
