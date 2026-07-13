import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type AppSettings, type TodoApi } from '@/shared/api/contracts';
import { useTheme, type ThemeId } from '../useTheme';

const SETTINGS: AppSettings = {
  theme: 'workspace-dark',
  muted: false,
  shortcut: 'Cmd+Alt+KeyT',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useTheme', () => {
  beforeEach(() => document.documentElement.removeAttribute('data-theme'));

  it('initializes theme and the document attribute from bootstrap', () => {
    const api = { updateSettings: vi.fn() } as unknown as TodoApi;
    const { result } = renderHook(() => useTheme('paper-dark', api, vi.fn()));

    expect(result.current.theme).toBe('paper-dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('paper-dark');
  });

  it('publishes a theme only after the settings request succeeds', async () => {
    const request = deferred<AppSettings>();
    const api = { updateSettings: vi.fn(() => request.promise) } as unknown as TodoApi;
    const { result } = renderHook(() => useTheme('workspace-light', api, vi.fn()));

    let change!: Promise<boolean>;
    act(() => { change = result.current.setTheme('paper-dark'); });
    expect(result.current.theme).toBe('workspace-light');

    await act(async () => request.resolve({ ...SETTINGS, theme: 'paper-dark' }));

    await expect(change).resolves.toBe(true);
    expect(result.current.theme).toBe('paper-dark');
    expect(api.updateSettings).toHaveBeenCalledWith({ theme: 'paper-dark' });
  });

  it('keeps the previous theme and reports a business failure', async () => {
    const onError = vi.fn();
    const failure = new ApiError('business', 'INVALID_REQUEST', 'Invalid theme', 422);
    const api = { updateSettings: vi.fn().mockRejectedValue(failure) } as unknown as TodoApi;
    const { result } = renderHook(() => useTheme('workspace-light', api, onError));

    await act(async () => {
      await expect(result.current.setTheme('mint-dark')).resolves.toBe(false);
    });

    expect(result.current.theme).toBe('workspace-light');
    expect(onError).toHaveBeenCalledWith(failure);
  });

  it('serializes concurrent changes and never lets an old response overwrite the latest intent', async () => {
    const first = deferred<AppSettings>();
    const second = deferred<AppSettings>();
    const api = {
      updateSettings: vi.fn()
        .mockImplementationOnce(() => first.promise)
        .mockImplementationOnce(() => second.promise),
    } as unknown as TodoApi;
    const { result } = renderHook(() => useTheme('workspace-light', api, vi.fn()));

    let firstChange!: Promise<boolean>;
    let secondChange!: Promise<boolean>;
    act(() => {
      firstChange = result.current.setTheme('mint-dark');
      secondChange = result.current.setTheme('paper-dark');
    });
    await act(async () => Promise.resolve());
    expect(api.updateSettings).toHaveBeenCalledTimes(1);

    await act(async () => first.resolve({ ...SETTINGS, theme: 'mint-dark' }));
    expect(result.current.theme).toBe('workspace-light');
    expect(api.updateSettings).toHaveBeenCalledTimes(2);

    await act(async () => second.resolve({ ...SETTINGS, theme: 'paper-dark' }));
    await Promise.all([firstChange, secondChange]);
    expect(result.current.theme).toBe('paper-dark');
  });

  it('ignores a response from before a replacement bootstrap snapshot', async () => {
    const oldRequest = deferred<AppSettings>();
    const oldApi = { updateSettings: vi.fn(() => oldRequest.promise) } as unknown as TodoApi;
    const newApi = {
      updateSettings: vi.fn().mockRejectedValue(
        new ApiError('business', 'INVALID_REQUEST', 'Invalid theme', 422),
      ),
    } as unknown as TodoApi;
    const { result, rerender } = renderHook(
      ({ theme, api }: { theme: ThemeId; api: TodoApi }) => useTheme(theme, api, vi.fn()),
      { initialProps: { theme: 'workspace-light' as ThemeId, api: oldApi } },
    );

    act(() => { void result.current.setTheme('mint-dark'); });
    await act(async () => Promise.resolve());
    rerender({ theme: 'paper-dark', api: newApi });
    await act(async () => oldRequest.resolve({ ...SETTINGS, theme: 'mint-dark' }));
    await act(async () => { await result.current.setTheme('workspace-dark'); });

    expect(result.current.theme).toBe('paper-dark');
  });
});
