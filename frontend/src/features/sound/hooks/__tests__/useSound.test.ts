import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, type AppSettings, type TodoApi } from '@/shared/api/contracts';
import { useSound } from '../useSound';

const SETTINGS: AppSettings = {
  theme: 'workspace-light',
  muted: true,
  shortcut: 'Cmd+Alt+KeyT',
  language: 'zh-CN',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => { resolve = res; });
  return { promise, resolve };
}

describe('useSound', () => {
  it('initializes muted state from bootstrap', () => {
    const api = { updateSettings: vi.fn() } as unknown as TodoApi;
    const { result } = renderHook(() => useSound(true, api, vi.fn()));

    expect(result.current.muted).toBe(true);
  });

  it('changes muted state only after the settings request succeeds', async () => {
    const request = deferred<AppSettings>();
    const api = { updateSettings: vi.fn(() => request.promise) } as unknown as TodoApi;
    const { result } = renderHook(() => useSound(false, api, vi.fn()));

    let toggle!: Promise<boolean>;
    act(() => { toggle = result.current.toggleMuted(); });
    expect(result.current.muted).toBe(false);

    await act(async () => request.resolve(SETTINGS));

    await expect(toggle).resolves.toBe(true);
    expect(result.current.muted).toBe(true);
    expect(api.updateSettings).toHaveBeenCalledWith({ muted: true });
  });

  it('keeps the previous value and reports a business failure', async () => {
    const failure = new ApiError('business', 'INVALID_REQUEST', 'Invalid setting', 422);
    const onError = vi.fn();
    const api = { updateSettings: vi.fn().mockRejectedValue(failure) } as unknown as TodoApi;
    const { result } = renderHook(() => useSound(false, api, onError));

    await act(async () => {
      await expect(result.current.toggleMuted()).resolves.toBe(false);
    });

    expect(result.current.muted).toBe(false);
    expect(onError).toHaveBeenCalledWith(failure);
  });
});
