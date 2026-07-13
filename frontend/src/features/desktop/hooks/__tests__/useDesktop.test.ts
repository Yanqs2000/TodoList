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

  it.each([
    'BACKEND_UNAVAILABLE',
    'SHORTCUT_ROLLBACK_FAILED',
    'SHORTCUT_CLEANUP_FAILED',
  ])('blocks on fatal shortcut error %s and keeps the prior shortcut', async (code) => {
    tauriMocks.invoke.mockRejectedValueOnce(code);
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

  it('does not let a late initial autostart read overwrite a confirmed toggle', async () => {
    const initial = deferred<boolean>();
    tauriMocks.isEnabled
      .mockReset()
      .mockReturnValueOnce(initial.promise)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    tauriMocks.enable.mockResolvedValue(undefined);
    const { result } = renderHook(() => useDesktop('Cmd+Alt+KeyT', vi.fn(), vi.fn()));
    await waitFor(() => expect(tauriMocks.isEnabled).toHaveBeenCalledTimes(1));

    let toggle!: Promise<{ ok: true } | { ok: false; error: string }>;
    act(() => { toggle = result.current.toggleAutostart(); });
    await act(async () => { await toggle; });
    initial.resolve(false);
    await Promise.resolve();

    expect(tauriMocks.enable).toHaveBeenCalledTimes(1);
    expect(tauriMocks.isEnabled).toHaveBeenCalledTimes(3);
    expect(result.current.autostartEnabled).toBe(true);
  });

  it('serializes autostart toggles, rereads OS state, and keeps the last confirmed value on failure', async () => {
    const enabling = deferred<void>();
    tauriMocks.isEnabled
      .mockReset()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(true);
    tauriMocks.enable.mockReturnValueOnce(enabling.promise);
    tauriMocks.disable.mockRejectedValueOnce(new Error('disable failed'));
    const { result } = renderHook(() => useDesktop('Cmd+Alt+KeyT', vi.fn(), vi.fn()));
    await waitFor(() => expect(tauriMocks.isEnabled).toHaveBeenCalledTimes(1));

    let first!: Promise<{ ok: true } | { ok: false; error: string }>;
    let second!: Promise<{ ok: true } | { ok: false; error: string }>;
    act(() => {
      first = result.current.toggleAutostart();
      second = result.current.toggleAutostart();
    });
    await waitFor(() => expect(tauriMocks.enable).toHaveBeenCalledTimes(1));
    expect(tauriMocks.disable).not.toHaveBeenCalled();

    enabling.resolve();
    await act(async () => { await Promise.all([first, second]); });

    expect(tauriMocks.disable).toHaveBeenCalledTimes(1);
    expect(result.current.autostartEnabled).toBe(true);
    await expect(first).resolves.toEqual({ ok: true });
    await expect(second).resolves.toEqual({ ok: false, error: 'Error: disable failed' });
  });
});
