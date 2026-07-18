import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, type AppSettings, type TodoApi } from '@/shared/api/contracts';
import { useLanguage } from '../useLanguage';

const SETTINGS: AppSettings = {
  theme: 'workspace-light',
  muted: false,
  shortcut: 'Cmd+Alt+KeyT',
  language: 'zh-CN',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => { resolve = res; });
  return { promise, resolve };
}

describe('useLanguage', () => {
  it('publishes a language only after persistence succeeds', async () => {
    const request = deferred<AppSettings>();
    const api = { updateSettings: vi.fn(() => request.promise) } as unknown as TodoApi;
    const { result } = renderHook(() => useLanguage('zh-CN', api, vi.fn()));

    let change!: Promise<boolean>;
    act(() => { change = result.current.setLanguage('en'); });
    expect(result.current.language).toBe('zh-CN');
    expect(result.current.pending).toBe(true);

    await act(async () => request.resolve({ ...SETTINGS, language: 'en' }));

    await expect(change).resolves.toBe(true);
    expect(result.current.language).toBe('en');
    expect(result.current.pending).toBe(false);
  });

  it('keeps the loaded language when persistence fails', async () => {
    const failure = new ApiError('business', 'INVALID_REQUEST', 'Invalid language', 422);
    const onError = vi.fn();
    const api = { updateSettings: vi.fn().mockRejectedValue(failure) } as unknown as TodoApi;
    const { result } = renderHook(() => useLanguage('zh-CN', api, onError));

    await act(async () => {
      await expect(result.current.setLanguage('en')).resolves.toBe(false);
    });

    expect(result.current.language).toBe('zh-CN');
    expect(onError).toHaveBeenCalledWith(failure);
  });
});
