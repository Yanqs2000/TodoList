import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  InfrastructureError,
  type AssistantConversationDetail,
  type AssistantConversationSummary,
  type AssistantProposal,
  type AssistantProposalBatch,
  type ConfirmProposalItemInput,
  type ProposalBatchResolveResult,
  type TodoApi,
} from '@/shared/api/contracts';
import { useAssistant } from '../hooks/useAssistant';

const summary: AssistantConversationSummary = {
  id: 'c1', title: '你好', createdAt: 1, updatedAt: 1,
};

const proposal: AssistantProposal = {
  id: 'p1',
  messageId: 'm2',
  batchId: 'b1',
  action: 'create',
  targetTaskId: null,
  beforeSnapshot: null,
  payload: {
    text: '买菜',
    priority: 'medium',
    category: 'life',
    time_start: null,
    time_end: null,
    notes: null,
  },
  resultTaskId: null,
  status: 'pending',
  lastError: null,
  createdAt: 3,
};

const batch: AssistantProposalBatch = {
  id: 'b1',
  messageId: 'm2',
  status: 'pending',
  supersedesBatchId: null,
  proposals: [proposal],
  createdAt: 3,
  resolvedAt: null,
};

const detail: AssistantConversationDetail = {
  conversation: summary,
  messages: [
    {
      id: 'm1', turnId: 'turn-1', role: 'user', content: '你好',
      attachments: [], status: 'done', createdAt: 1,
    },
    {
      id: 'm2', turnId: 'turn-1', role: 'assistant', content: '你好！',
      attachments: [], status: 'done', createdAt: 2,
    },
  ],
  proposalBatches: [batch],
};

const editedItems: ConfirmProposalItemInput[] = [{
  proposalId: 'p1',
  payload: {
    text: '卡片编辑后',
    priority: 'high',
    category: 'work',
    time_start: null,
    time_end: null,
    notes: null,
  },
}];

function batchResolveResult(
  status: 'partially_applied' | 'accepted' | 'rejected',
): ProposalBatchResolveResult {
  const resolvedProposal: AssistantProposal = {
    ...proposal,
    resultTaskId: status === 'rejected' ? null : 't1',
    status: status === 'rejected' ? 'rejected' : 'accepted',
  };
  return {
    batch: {
      ...batch,
      status,
      proposals: [resolvedProposal],
      resolvedAt: 4,
    },
    items: [{ proposal: resolvedProposal, task: null, error: null }],
  };
}

function detailWithFailedTurn(turnId: string): AssistantConversationDetail {
  return {
    conversation: summary,
    messages: [
      {
        id: 'm-failed-user', turnId, role: 'user', content: '新建买菜任务',
        attachments: [], status: 'done', createdAt: 5,
      },
      {
        id: 'm-failed-assistant', turnId, role: 'assistant', content: '',
        attachments: [], status: 'failed', createdAt: 6,
      },
    ],
    proposalBatches: [],
  };
}

function fakeApi(): TodoApi {
  return {
    getAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat', audioModel: 'audio', baseUrl: '',
    }),
    listAssistantConversations: vi.fn().mockResolvedValue([summary]),
    getAssistantConversation: vi.fn().mockResolvedValue(detail),
    createAssistantConversation: vi.fn().mockResolvedValue({
      id: 'c2', title: '', createdAt: 4, updatedAt: 4,
    }),
    sendAssistantMessage: vi.fn().mockResolvedValue({
      message: detail.messages[1], proposalBatches: detail.proposalBatches,
    }),
    deleteAssistantConversation: vi.fn().mockResolvedValue(undefined),
    confirmAssistantProposalBatch: vi.fn().mockResolvedValue(
      batchResolveResult('accepted'),
    ),
    rejectAssistantProposalBatch: vi.fn().mockResolvedValue(
      batchResolveResult('rejected'),
    ),
    updateAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat2', audioModel: 'audio', baseUrl: '',
    }),
  } as unknown as TodoApi;
}

describe('useAssistant', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads conversations and selects the newest on mount', async () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(fakeApi(), onError));

    await waitFor(() => expect(result.current.activeId).toBe('c1'));
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.proposalBatches).toEqual([batch]);
    expect(result.current.settingsView?.hasApiKey).toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });

  it('send creates a conversation when none is active', async () => {
    vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValue('00000000-0000-4000-8000-000000000002');
    const api = fakeApi();
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.settingsView).not.toBeNull());
    act(() => result.current.startNewConversation());
    expect(result.current.activeId).toBeNull();

    await act(() => result.current.send('安排明天', []));

    expect(api.createAssistantConversation).toHaveBeenCalled();
    expect(api.sendAssistantMessage).toHaveBeenCalledWith('c2', {
      turnId: '00000000-0000-4000-8000-000000000002',
      content: '安排明天',
      attachments: [],
    });
  });

  it('reuses the original turn id when retrying a failed message', async () => {
    const api = fakeApi();
    const failedDetail = detailWithFailedTurn('turn-retry-1');
    api.getAssistantConversation = vi.fn().mockResolvedValue(failedDetail);
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.retry('turn-retry-1'));

    expect(api.sendAssistantMessage).toHaveBeenCalledWith('c1', {
      turnId: 'turn-retry-1', content: '新建买菜任务', attachments: [],
    });
  });

  it('creates one stable turn id for a normal send', async () => {
    const uuid = vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValue('00000000-0000-4000-8000-000000000001');
    const api = fakeApi();
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.send('新建买菜任务', []));

    expect(uuid).toHaveBeenCalledTimes(1);
    expect(api.sendAssistantMessage).toHaveBeenCalledWith('c1', {
      turnId: '00000000-0000-4000-8000-000000000001',
      content: '新建买菜任务', attachments: [],
    });
  });

  it('confirms one batch and replaces it with the server state', async () => {
    const api = fakeApi();
    const resolved = batchResolveResult('partially_applied');
    api.confirmAssistantProposalBatch = vi.fn().mockResolvedValue(resolved);
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    const response = await act(() => result.current.confirmBatch('b1', editedItems));

    expect(response).toEqual(resolved);
    expect(api.confirmAssistantProposalBatch).toHaveBeenCalledWith('b1', {
      items: editedItems,
    });
    expect(result.current.proposalBatches[0]).toEqual(resolved.batch);
    expect(result.current.submittingBatchIds.has('b1')).toBe(false);
  });

  it('ignores duplicate confirmation while the batch is submitting', async () => {
    const api = fakeApi();
    const resolved = batchResolveResult('accepted');
    let settle = (_value: ProposalBatchResolveResult): void => undefined;
    const pending = new Promise<ProposalBatchResolveResult>((resolve) => {
      settle = resolve;
    });
    api.confirmAssistantProposalBatch = vi.fn().mockReturnValue(pending);
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    let first!: Promise<ProposalBatchResolveResult | undefined>;
    let duplicate!: Promise<ProposalBatchResolveResult | undefined>;
    act(() => {
      first = result.current.confirmBatch('b1', editedItems);
      duplicate = result.current.confirmBatch('b1', editedItems);
    });

    await expect(duplicate).resolves.toBeUndefined();
    expect(api.confirmAssistantProposalBatch).toHaveBeenCalledTimes(1);
    expect(result.current.submittingBatchIds.has('b1')).toBe(true);

    await act(async () => {
      settle(resolved);
      await first;
    });
    expect(result.current.submittingBatchIds.has('b1')).toBe(false);
  });

  it('rejects one batch and replaces it with the server state', async () => {
    const api = fakeApi();
    const resolved = batchResolveResult('rejected');
    api.rejectAssistantProposalBatch = vi.fn().mockResolvedValue(resolved);
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    const response = await act(() => result.current.rejectBatch('b1'));

    expect(response).toEqual(resolved);
    expect(api.rejectAssistantProposalBatch).toHaveBeenCalledWith('b1');
    expect(result.current.proposalBatches[0]).toEqual(resolved.batch);
  });

  it('reports an unknown retry turn without sending', async () => {
    const api = fakeApi();
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(api, onError));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.retry('turn-missing'));

    expect(api.sendAssistantMessage).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      name: 'ApiError',
      kind: 'business',
      code: 'ASSISTANT_TURN_NOT_FOUND',
      status: 404,
    }));
  });

  it('refreshes a persisted failed turn and allows retry after a send error', async () => {
    const turnId = '00000000-0000-4000-8000-000000000003';
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(turnId);
    const api = fakeApi();
    const failedDetail = detailWithFailedTurn(turnId);
    const sendError = new InfrastructureError(
      'infrastructure', 'INTERNAL_ERROR', 'Assistant failed', 500,
    );
    api.getAssistantConversation = vi.fn()
      .mockResolvedValueOnce(detail)
      .mockResolvedValue(failedDetail);
    api.sendAssistantMessage = vi.fn()
      .mockRejectedValueOnce(sendError)
      .mockResolvedValue({
        message: failedDetail.messages[1], proposalBatches: [],
      });
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(api, onError));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.send('新建买菜任务', []));

    expect(result.current.messages).toEqual(failedDetail.messages);
    expect(result.current.proposalBatches).toEqual([]);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(sendError);

    await act(() => result.current.retry(turnId));

    expect(api.sendAssistantMessage).toHaveBeenNthCalledWith(2, 'c1', {
      turnId, content: '新建买菜任务', attachments: [],
    });
    expect(onError).toHaveBeenCalledTimes(1);
    expect(result.current.sending).toBe(false);
  });
});
