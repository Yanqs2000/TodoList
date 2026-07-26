import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import type {
  AssistantProposal,
  AssistantProposalBatch,
  ProposalBatchResolveResult,
  TodoApi,
} from '@/shared/api/contracts';
import type { AssistantState } from '../hooks/useAssistant';
import AssistantDrawer from '../components/AssistantDrawer';

function proposal(overrides: Partial<AssistantProposal> = {}): AssistantProposal {
  return {
    id: 'p1', messageId: 'm2', batchId: 'b1', action: 'create',
    targetTaskId: null, beforeSnapshot: null,
    payload: {
      text: '买菜', priority: 'medium', category: 'life',
      time_start: null, time_end: null, notes: null,
    },
    resultTaskId: null, status: 'pending', lastError: null, createdAt: 3,
    ...overrides,
  };
}

function proposalBatch(
  proposals: AssistantProposal[] = [proposal()],
  overrides: Partial<AssistantProposalBatch> = {},
): AssistantProposalBatch {
  return {
    id: 'b1', messageId: 'm2', status: 'pending', supersedesBatchId: null,
    proposals, createdAt: 3, resolvedAt: null, ...overrides,
  };
}

function state(overrides: Partial<AssistantState> = {}): AssistantState {
  return {
    conversations: [], activeId: 'c1', sending: false, streamingStep: null,
    messages: [
      { id: 'm1', turnId: 'turn-1', role: 'user', content: '安排明天', attachments: [], status: 'done', createdAt: 1 },
      { id: 'm2', turnId: 'turn-1', role: 'assistant', content: '提议如下', attachments: [], status: 'done', createdAt: 2 },
    ],
    proposalBatches: [proposalBatch()],
    submittingBatchIds: new Set<string>(),
    settingsView: { hasApiKey: true, chatModel: 'chat', audioModel: 'audio', baseUrl: 'https://ark.cn-beijing.volces.com/api/v3', voiceMode: 'transcribe' as const },
    selectConversation: vi.fn(), startNewConversation: vi.fn(),
    deleteConversation: vi.fn(), send: vi.fn(), retry: vi.fn(),
    confirmBatch: vi.fn().mockResolvedValue(undefined),
    rejectBatch: vi.fn().mockResolvedValue(undefined), saveSettings: vi.fn(),
    ...overrides,
  };
}

function renderDrawer(assistant: AssistantState, onApplyProposal = vi.fn()) {
  return {
    onApplyProposal,
    ...render(
      <I18nProvider language="zh-CN">
        <AssistantDrawer
          open onClose={vi.fn()} assistant={assistant}
          api={{} as unknown as TodoApi}
          onApplyProposal={onApplyProposal} onError={vi.fn()}
        />
      </I18nProvider>,
    ),
  };
}

describe('AssistantDrawer', () => {
  it('renders messages and a pending proposal batch card', () => {
    renderDrawer(state());

    expect(screen.getByText('安排明天')).toBeTruthy();
    expect(screen.getByDisplayValue('买菜')).toBeTruthy();
    expect(screen.getByText('新建任务')).toBeTruthy();
    expect(screen.getByRole('button', { name: '确认全部 1 项' })).toBeTruthy();
  });

  it('confirms once and notifies the parent for every accepted item', async () => {
    const first = proposal({ id: 'p1', status: 'accepted', resultTaskId: 't1' });
    const second = proposal({ id: 'p2', status: 'accepted', resultTaskId: 't2' });
    const result: ProposalBatchResolveResult = {
      batch: proposalBatch([first, second], { status: 'accepted', resolvedAt: 4 }),
      items: [
        { proposal: first, task: null, error: null },
        { proposal: second, task: null, error: null },
      ],
    };
    const assistant = state({
      confirmBatch: vi.fn().mockResolvedValue(result),
    });
    const { onApplyProposal } = renderDrawer(assistant);

    fireEvent.click(screen.getByRole('button', { name: '确认全部 1 项' }));

    expect(assistant.confirmBatch).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(onApplyProposal).toHaveBeenCalledTimes(2));
    expect(onApplyProposal).toHaveBeenNthCalledWith(1, result.items[0]);
    expect(onApplyProposal).toHaveBeenNthCalledWith(2, result.items[1]);
    expect(assistant.send).not.toHaveBeenCalled();
  });

  it('does not notify the parent for a rejected result item', async () => {
    const rejected = proposal({ status: 'rejected' });
    const result: ProposalBatchResolveResult = {
      batch: proposalBatch([rejected], { status: 'rejected', resolvedAt: 4 }),
      items: [{ proposal: rejected, task: null, error: null }],
    };
    const assistant = state({
      confirmBatch: vi.fn().mockResolvedValue(result),
    });
    const { onApplyProposal } = renderDrawer(assistant);

    fireEvent.click(screen.getByRole('button', { name: '确认全部 1 项' }));

    await waitFor(() => expect(assistant.confirmBatch).toHaveBeenCalled());
    expect(onApplyProposal).not.toHaveBeenCalled();
  });

  it('passes the failed assistant turn id to retry', () => {
    const assistant = state({
      messages: [
        { id: 'm9', turnId: 'turn-9', role: 'assistant', content: '', attachments: [], status: 'failed', createdAt: 9 },
      ],
      proposalBatches: [],
    });
    renderDrawer(assistant);

    fireEvent.click(screen.getByText('重试'));

    expect(assistant.retry).toHaveBeenCalledWith('turn-9');
  });

  it('does not offer retry when a failed history message has no turn id', () => {
    renderDrawer(state({
      messages: [
        { id: 'm9', turnId: null, role: 'assistant', content: '', attachments: [], status: 'failed', createdAt: 9 },
      ],
      proposalBatches: [],
    }));

    expect(screen.getByText('这条回复失败了，可以重试。')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '重试' })).toBeNull();
  });

  it('shows the setup panel when the key is missing', () => {
    renderDrawer(state({ settingsView: { hasApiKey: false, chatModel: 'c', audioModel: 'a', baseUrl: 'https://ark.cn-beijing.volces.com/api/v3', voiceMode: 'transcribe' as const } }));

    expect(screen.getByText('还没有配置模型服务')).toBeTruthy();
  });

  it('send button forwards composer content', () => {
    const assistant = state();
    renderDrawer(assistant);

    fireEvent.change(screen.getByPlaceholderText('描述你的安排，或发送语音/文件…'), {
      target: { value: '明天下午三点开会' },
    });
    fireEvent.click(screen.getByText('发送'));

    expect(assistant.send).toHaveBeenCalledWith('明天下午三点开会', []);
  });
});
