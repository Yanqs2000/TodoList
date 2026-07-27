import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProposalApplyItemResult } from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import App, { applyProposalItemToTaskList } from '../App';

describe('App startup gate', () => {
  beforeEach(() => {
    Reflect.deleteProperty(window, '__TAURI_INTERNALS__');
  });

  it('does not mount the todo application in an ordinary browser', () => {
    render(<App />);

    expect(screen.getByRole('heading')).toHaveTextContent('请通过桌面应用运行');
    expect(document.querySelector('.app-shell')).not.toBeInTheDocument();
  });

  it('applies every accepted proposal result to the task list by action', () => {
    const task: Todo = {
      id: 't1', text: '助手任务', completed: false, priority: 'medium', createdAt: 1,
    };
    const upsertExternalTask = vi.fn();
    const removeExternalTask = vi.fn();
    const createResult = {
      proposal: { action: 'create' }, task,
    } as ProposalApplyItemResult;
    const deleteResult = {
      proposal: { action: 'delete', targetTaskId: 't1' }, task: null,
    } as ProposalApplyItemResult;

    applyProposalItemToTaskList(createResult, { upsertExternalTask, removeExternalTask });
    applyProposalItemToTaskList(deleteResult, { upsertExternalTask, removeExternalTask });

    expect(upsertExternalTask).toHaveBeenCalledWith(task);
    expect(removeExternalTask).toHaveBeenCalledWith('t1');
  });
});
