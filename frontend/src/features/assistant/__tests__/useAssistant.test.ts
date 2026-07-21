import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  AssistantConversationDetail,
  AssistantConversationSummary,
  ResolveProposalResult,
  TodoApi,
} from '@/shared/api/contracts';
import { useAssistant } from '../hooks/useAssistant';

const summary: AssistantConversationSummary = {
  id: 'c1', title: '你好', createdAt: 1, updatedAt: 1,
};

const detail: AssistantConversationDetail = {
  conversation: summary,
  messages: [
    { id: 'm1', role: 'user', content: '你好', attachments: [], status: 'done', createdAt: 1 },
    { id: 'm2', role: 'assistant', content: '你好！', attachments: [], status: 'done', createdAt: 2 },
  ],
  proposals: [
    { id: 'p1', messageId: 'm2', action: 'create', taskId: null,
      payload: { text: '买菜' }, status: 'pending', createdAt: 3 },
  ],
};

function fakeApi(): TodoApi {
  return {
    getAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat', audioModel: 'audio',
    }),
    listAssistantConversations: vi.fn().mockResolvedValue([summary]),
    getAssistantConversation: vi.fn().mockResolvedValue(detail),
    createAssistantConversation: vi.fn().mockResolvedValue({
      id: 'c2', title: '', createdAt: 4, updatedAt: 4,
    }),
    sendAssistantMessage: vi.fn().mockResolvedValue({
      message: detail.messages[1], proposals: [detail.proposals[0]],
    }),
    deleteAssistantConversation: vi.fn().mockResolvedValue(undefined),
    acceptAssistantProposal: vi.fn().mockResolvedValue({
      proposal: { ...detail.proposals[0], status: 'accepted' }, task: null,
    } satisfies ResolveProposalResult),
    rejectAssistantProposal: vi.fn().mockResolvedValue({
      ...detail.proposals[0], status: 'rejected',
    }),
    updateAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat2', audioModel: 'audio',
    }),
  } as unknown as TodoApi;
}

describe('useAssistant', () => {
  it('loads conversations and selects the newest on mount', async () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(fakeApi(), onError));

    await waitFor(() => expect(result.current.activeId).toBe('c1'));
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.settingsView?.hasApiKey).toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });

  it('send creates a conversation when none is active', async () => {
    const api = fakeApi();
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.settingsView).not.toBeNull());
    act(() => result.current.startNewConversation());
    expect(result.current.activeId).toBeNull();

    await act(() => result.current.send('安排明天', []));

    expect(api.createAssistantConversation).toHaveBeenCalled();
    expect(api.sendAssistantMessage).toHaveBeenCalledWith(
      'c2', { content: '安排明天', attachments: [] },
    );
  });

  it('resolving a proposal updates local state and returns the result', async () => {
    const { result } = renderHook(() => useAssistant(fakeApi(), vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    const resolved = await act(() => result.current.resolveProposal('p1', 'accept'));

    expect(resolved?.proposal.status).toBe('accepted');
    expect(result.current.proposals[0].status).toBe('accepted');
  });

  it('reports errors through onError', async () => {
    const api = fakeApi();
    api.sendAssistantMessage = vi.fn().mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(api, onError));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.send('hi', []));

    expect(onError).toHaveBeenCalled();
    expect(result.current.sending).toBe(false);
  });
});
