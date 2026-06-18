import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTheme } from '../useTheme';

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('should default to workspace-light theme', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('workspace-light');
  });

  it('should set explicit theme id', () => {
    const { result } = renderHook(() => useTheme());
    act(() => {
      result.current.setTheme('paper-dark');
    });
    expect(result.current.theme).toBe('paper-dark');
  });

  it('should persist theme to localStorage', () => {
    const { result } = renderHook(() => useTheme());
    act(() => {
      result.current.setTheme('editor-light');
    });
    expect(localStorage.getItem('todo-theme')).toBe('editor-light');
  });

  it('should set data-theme attribute', () => {
    const { result } = renderHook(() => useTheme());
    act(() => {
      result.current.setTheme('paper-dark');
    });
    expect(document.documentElement.getAttribute('data-theme')).toBe('paper-dark');
  });

  it('should load saved theme from localStorage', () => {
    localStorage.setItem('todo-theme', 'editor-dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('editor-dark');
  });

  it('should migrate legacy "light" value to workspace-light', () => {
    localStorage.setItem('todo-theme', 'light');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('workspace-light');
  });

  it('should migrate legacy "dark" value to workspace-dark', () => {
    localStorage.setItem('todo-theme', 'dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('workspace-dark');
  });
});
