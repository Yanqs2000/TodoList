import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import type {
  AssistantProposal,
  AssistantProposalBatch,
  ConfirmProposalItemInput,
} from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import DeleteProposalCard from '../components/DeleteProposalCard';
import ProposalBatchCard from '../components/ProposalBatchCard';

const target: Todo = {
  id: 't1',
  text: '团队会议',
  completed: false,
  priority: 'high',
  createdAt: 1,
  time: { start: '2026-07-22T15:00', end: '2026-07-22T16:00' },
  category: 'work',
  notes: '准备议程',
};

function proposal(
  overrides: Partial<AssistantProposal> = {},
): AssistantProposal {
  return {
    id: 'p1',
    messageId: 'm1',
    batchId: 'b1',
    action: 'create',
    targetTaskId: null,
    beforeSnapshot: null,
    payload: {
      text: '第一项',
      priority: 'medium',
      category: 'other',
      time_start: null,
      time_end: null,
      notes: null,
    },
    resultTaskId: null,
    status: 'pending',
    lastError: null,
    createdAt: 1,
    ...overrides,
  };
}

function batch(
  proposals: AssistantProposal[],
  overrides: Partial<AssistantProposalBatch> = {},
): AssistantProposalBatch {
  return {
    id: 'b1',
    messageId: 'm1',
    status: 'pending',
    supersedesBatchId: null,
    proposals,
    createdAt: 1,
    resolvedAt: null,
    ...overrides,
  };
}

function editableBatchWithTwoItems(): AssistantProposalBatch {
  return batch([
    proposal(),
    proposal({
      id: 'p2',
      payload: {
        text: '第二项', priority: 'low', category: 'life',
        time_start: null, time_end: null, notes: null,
      },
    }),
  ]);
}

function updateBatch(): AssistantProposalBatch {
  return batch([proposal({
    action: 'update',
    targetTaskId: target.id,
    beforeSnapshot: target,
    payload: {
      text: '团队会议',
      priority: 'high',
      category: 'work',
      time_start: '2026-07-22T17:00',
      time_end: '2026-07-22T18:00',
      notes: '更新议程',
    },
  })]);
}

function partiallyAppliedBatch(): AssistantProposalBatch {
  return batch([
    proposal({ id: 'p-accepted', status: 'accepted', payload: {
      text: '已创建', priority: 'medium', category: 'other',
      time_start: null, time_end: null, notes: null,
    } }),
    proposal({ id: 'p-failed', lastError: 'TASK_CHANGED_SINCE_PROPOSAL' }),
  ], { status: 'partially_applied', resolvedAt: 2 });
}

function supersededBatch(): AssistantProposalBatch {
  return batch([
    proposal({ status: 'superseded' }),
  ], { status: 'superseded', resolvedAt: 2 });
}

function acceptedAndRejectedBatch(): AssistantProposalBatch {
  return batch([
    proposal({ id: 'p-accepted', status: 'accepted' }),
    proposal({ id: 'p-rejected', status: 'rejected' }),
  ], { status: 'partially_applied', resolvedAt: 2 });
}

function deleteBatch(): AssistantProposalBatch {
  return batch([proposal({
    action: 'delete',
    targetTaskId: target.id,
    beforeSnapshot: target,
    payload: null,
  })]);
}

function legacyDeleteBatch(
  overrides: Partial<AssistantProposal>,
): AssistantProposalBatch {
  return batch([proposal({
    action: 'delete',
    targetTaskId: target.id,
    beforeSnapshot: null,
    payload: null,
    ...overrides,
  })]);
}

const defaults = {
  submitting: false,
  onConfirm: vi.fn(),
  onReject: vi.fn(),
};

function renderCard(
  value: AssistantProposalBatch,
  overrides: Partial<typeof defaults> = {},
) {
  const props = { ...defaults, ...overrides };
  return render(
    <I18nProvider language="zh-CN">
      <ProposalBatchCard batch={value} {...props} />
    </I18nProvider>,
  );
}

function renderDeleteCard(
  value: AssistantProposalBatch,
  overrides: Partial<typeof defaults> = {},
) {
  const props = { ...defaults, ...overrides };
  return render(
    <I18nProvider language="zh-CN">
      <DeleteProposalCard batch={value} {...props} />
    </I18nProvider>,
  );
}

describe('proposal cards', () => {
  it('edits two proposals and confirms the batch once', () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderCard(editableBatchWithTwoItems(), { onConfirm });

    fireEvent.change(screen.getAllByLabelText('任务标题')[0], {
      target: { value: '修改后的第一项' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认全部 2 项' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith('b1', expect.arrayContaining([
      expect.objectContaining({
        proposalId: 'p1', payload: expect.objectContaining({ text: '修改后的第一项' }),
      }),
      expect.objectContaining({ proposalId: 'p2' }),
    ]));
  });

  it('shows update target and before-after values', () => {
    renderCard(updateBatch());
    expect(screen.getByText('目标：团队会议')).toBeTruthy();
    expect(screen.getByText('2026-07-22 15:00')).toBeTruthy();
    expect(screen.getByText('2026-07-22 17:00')).toBeTruthy();
  });

  it('locks accepted items and resubmits only pending failures', () => {
    const onConfirm = vi.fn();
    renderCard(partiallyAppliedBatch(), { onConfirm });
    expect(screen.getByDisplayValue('已创建')).toBeDisabled();
    expect(screen.getByText('此项未执行：任务已在其他位置发生变化，请重新生成提议。'))
      .toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '重新确认剩余 1 项' }));

    expect(onConfirm).toHaveBeenCalledWith('b1', [
      expect.objectContaining({ proposalId: 'p-failed' }),
    ]);
  });

  it('re-synchronizes a draft when the server batch status changes', () => {
    const view = renderCard(batch([proposal()]));
    fireEvent.change(screen.getByLabelText('任务标题'), {
      target: { value: '仅本地修改' },
    });
    const accepted = proposal({
      status: 'accepted',
      payload: {
        text: '服务端已接受', priority: 'high', category: 'work',
        time_start: null, time_end: null, notes: null,
      },
    });

    view.rerender(
      <I18nProvider language="zh-CN">
        <ProposalBatchCard
          batch={batch([accepted], { status: 'accepted', resolvedAt: 2 })}
          {...defaults}
        />
      </I18nProvider>,
    );

    expect(screen.getByDisplayValue('服务端已接受')).toBeDisabled();
  });

  it('renders a delete target read-only with its full details', () => {
    renderDeleteCard(deleteBatch());
    expect(screen.getByText('删除任务：团队会议')).toBeTruthy();
    expect(screen.getByText('工作')).toBeTruthy();
    expect(screen.getByText('高')).toBeTruthy();
    expect(screen.getByText('2026-07-22 15:00')).toBeTruthy();
    expect(screen.getByText('2026-07-22 16:00')).toBeTruthy();
    expect(screen.getByText('准备议程')).toBeTruthy();
    expect(screen.getByText('未完成')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('disables confirmation for superseded batches', () => {
    renderCard(supersededBatch());
    expect(screen.queryByRole('button', { name: /确认/ })).toBeNull();
    expect(screen.getByText('已被新提议取代')).toBeTruthy();
  });

  it('renders a legacy delete without a snapshot as read-only history', () => {
    renderDeleteCard(legacyDeleteBatch({ beforeSnapshot: null, payload: null }));
    expect(screen.getByText('任务详情不可用')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /确认删除/ })).toBeNull();
  });

  it('does not offer retry when a terminal partial batch has no pending items', () => {
    renderCard(acceptedAndRejectedBatch());
    expect(screen.queryByRole('button', { name: /剩余 0/ })).toBeNull();
  });

  it('disables confirmation when a pending title is blank', () => {
    renderCard(batch([proposal({ payload: {
      text: '  ', priority: 'medium', category: 'other',
      time_start: null, time_end: null, notes: null,
    } })]));

    expect(screen.getByText('任务标题不能为空')).toBeTruthy();
    expect(screen.getByRole('button', { name: '确认全部 1 项' })).toBeDisabled();
  });

  it('shows a local error for an invalid time range', () => {
    renderCard(editableBatchWithTwoItems());

    fireEvent.change(screen.getAllByLabelText('开始时间')[0], {
      target: { value: '2026-07-22T18:00' },
    });
    fireEvent.change(screen.getAllByLabelText('结束时间')[0], {
      target: { value: '2026-07-22T17:00' },
    });

    expect(screen.getByText('结束时间必须晚于开始时间')).toBeTruthy();
    expect(screen.getByRole('button', { name: '确认全部 2 项' })).toBeDisabled();
  });

  it('disables fields and actions while submitting', () => {
    renderCard(editableBatchWithTwoItems(), { submitting: true });

    expect(screen.getAllByLabelText('任务标题')[0]).toBeDisabled();
    expect(screen.getByRole('button', { name: '确认全部 2 项' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '拒绝' })).toBeDisabled();
  });

  it('keeps notes editable and includes them in confirmation', () => {
    const onConfirm = vi.fn();
    renderCard(editableBatchWithTwoItems(), { onConfirm });

    fireEvent.change(screen.getAllByLabelText('备注')[0], {
      target: { value: '带上资料' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认全部 2 项' }));

    const items = onConfirm.mock.calls[0][1] as ConfirmProposalItemInput[];
    expect(items[0].payload?.notes).toBe('带上资料');
  });

  it('uses independent confirm and reject actions for delete', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();
    renderDeleteCard(deleteBatch(), { onConfirm, onReject });

    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));

    expect(onConfirm).toHaveBeenCalledWith('b1', [{ proposalId: 'p1', payload: null }]);
    expect(onReject).toHaveBeenCalledWith('b1');
  });

  it('disables delete actions while submitting', () => {
    renderDeleteCard(deleteBatch(), { submitting: true });

    expect(screen.getByRole('button', { name: '确认删除' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '拒绝' })).toBeDisabled();
  });

  it('keeps reject available for a pending legacy row but cannot confirm it', () => {
    const onReject = vi.fn();
    renderCard(batch([proposal({ payload: null })]), { onReject });

    expect(screen.getByText('任务详情不可用')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /确认/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }));
    expect(onReject).toHaveBeenCalledWith('b1');
  });

  it('does not invoke a chat send callback when confirming', () => {
    const send = vi.fn();
    const onConfirm = vi.fn();
    renderCard(editableBatchWithTwoItems(), { onConfirm });

    fireEvent.click(screen.getByRole('button', { name: '确认全部 2 项' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(send).not.toHaveBeenCalled();
  });
});
