import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import type { TodoApi } from '@/shared/api/contracts';
import type { AssistantState } from '../hooks/useAssistant';
import AssistantDrawer from '../components/AssistantDrawer';

function state(overrides: Partial<AssistantState> = {}): AssistantState {
  return {
    conversations: [], activeId: 'c1', sending: false,
    messages: [
      { id: 'm1', role: 'user', content: '安排明天', attachments: [], status: 'done', createdAt: 1 },
      { id: 'm2', role: 'assistant', content: '提议如下', attachments: [], status: 'done', createdAt: 2 },
    ],
    proposals: [
      { id: 'p1', messageId: 'm2', action: 'create', taskId: null,
        payload: { text: '买菜', priority: 'medium', time_start: '2026-07-21T09:00' },
        status: 'pending', createdAt: 3 },
    ],
    settingsView: { hasApiKey: true, chatModel: 'chat', audioModel: 'audio' },
    selectConversation: vi.fn(), startNewConversation: vi.fn(),
    deleteConversation: vi.fn(), send: vi.fn(), retry: vi.fn(),
    resolveProposal: vi.fn().mockResolvedValue(undefined), saveSettings: vi.fn(),
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
  it('renders messages and a pending proposal card', () => {
    renderDrawer(state());

    expect(screen.getByText('安排明天')).toBeTruthy();
    expect(screen.getByText('买菜')).toBeTruthy();
    expect(screen.getByText('新建任务')).toBeTruthy();
  });

  it('accepting a proposal resolves it and notifies the parent', async () => {
    const resolveResult = {
      proposal: { ...state().proposals[0], status: 'accepted' as const },
      task: null,
    };
    const assistant = state({
      resolveProposal: vi.fn().mockResolvedValue(resolveResult),
    });
    const { onApplyProposal } = renderDrawer(assistant);

    fireEvent.click(screen.getByText('接受'));

    expect(assistant.resolveProposal).toHaveBeenCalledWith('p1', 'accept');
    await screen.findByText('已接受');
    expect(onApplyProposal).toHaveBeenCalledWith(resolveResult);
  });

  it('shows a retry button on failed assistant messages', () => {
    const assistant = state({
      messages: [
        { id: 'm9', role: 'assistant', content: '', attachments: [], status: 'failed', createdAt: 9 },
      ],
      proposals: [],
    });
    renderDrawer(assistant);

    fireEvent.click(screen.getByText('重试'));

    expect(assistant.retry).toHaveBeenCalled();
  });

  it('shows the setup panel when the key is missing', () => {
    renderDrawer(state({ settingsView: { hasApiKey: false, chatModel: 'c', audioModel: 'a' } }));

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
