import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TodoApi } from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import { useTodos } from '../useTodos';

function task(id: string, text: string, start?: string): Todo {
  return {
    id,
    text,
    completed: false,
    priority: 'low',
    createdAt: 1,
    category: 'other',
    time: start ? { start } : undefined,
  };
}

function fakeApi(): TodoApi {
  return {
    bootstrap: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    deleteTask: vi.fn(),
    replaceTaskOrder: vi.fn(),
    setTaskCompletion: vi.fn(),
    claimReminder: vi.fn(),
    updateSettings: vi.fn(),
    listAssistantConversations: vi.fn(),
    createAssistantConversation: vi.fn(),
    getAssistantConversation: vi.fn(),
    deleteAssistantConversation: vi.fn(),
    sendAssistantMessage: vi.fn(),
    uploadAssistantFile: vi.fn(),
    transcribeAssistantAudio: vi.fn(),
    acceptAssistantProposal: vi.fn(),
    rejectAssistantProposal: vi.fn(),
    getAssistantSettings: vi.fn(),
    updateAssistantSettings: vi.fn(),
  };
}

describe('useTodos sort modes', () => {
  it('manual mode preserves snapshot order and time mode sorts by start', () => {
    const initial = [
      task('a', 'A', '2026-06-15T10:00'),
      task('b', 'B', '2026-06-15T08:00'),
    ];
    const { result } = renderHook(() => useTodos(initial, fakeApi(), vi.fn()));

    expect(result.current.tasks.map(item => item.text)).toEqual(['A', 'B']);
    act(() => { result.current.setSortMode('time'); });
    expect(result.current.tasks.map(item => item.text)).toEqual(['B', 'A']);
    act(() => { result.current.setSortMode('manual'); });
    expect(result.current.tasks.map(item => item.text)).toEqual(['A', 'B']);
  });
});
