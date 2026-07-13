import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TaskList from '../TaskList';
import type { Todo } from '@/shared/types';
import type { TaskMutationKind } from '../../hooks/useTodos';

// Fixed "now": 2026-06-23T13:00 local.
const NOW = new Date('2026-06-23T13:00').getTime();

function makeTask(partial: Partial<Todo>): Todo {
  return { id: 'x', text: 'task', completed: false, priority: 'low', createdAt: 1, ...partial };
}

const noop = () => {};

const baseProps = {
  filter: 'active' as const,
  hasAnyTasks: true,
  onToggleSortMode: noop,
  onToggle: noop,
  onDelete: noop,
  onReorder: noop,
  now: NOW,
};

describe('TaskList grouping (Today Focus)', () => {
  it('renders proximity groups in active + time-sorted mode', () => {
    const tasks = [
      makeTask({ id: '1', text: '昨天的', time: { start: '2026-06-22T10:00' } }),   // overdue
      makeTask({ id: '2', text: '今天的', time: { start: '2026-06-23T15:00' } }),     // today
      makeTask({ id: '3', text: '以后的', time: { start: '2026-06-25T10:00' } }),     // future
      makeTask({ id: '4', text: '待办的' }),                                          // unscheduled
    ];
    render(<TaskList {...baseProps} tasks={tasks} sortMode="time" />);
    expect(screen.getByText('已过期')).toBeInTheDocument();
    expect(screen.getByText('今天')).toBeInTheDocument();
    expect(screen.getByText('以后')).toBeInTheDocument();
    expect(screen.getByText('待安排')).toBeInTheDocument();
  });

  it('does NOT group in active + manual mode', () => {
    const tasks = [
      makeTask({ id: '1', text: '昨天的', time: { start: '2026-06-22T10:00' } }),
      makeTask({ id: '2', text: '今天的', time: { start: '2026-06-23T15:00' } }),
    ];
    render(<TaskList {...baseProps} tasks={tasks} sortMode="manual" />);
    expect(screen.queryByText('已过期')).not.toBeInTheDocument();
    expect(screen.queryByText('今天')).not.toBeInTheDocument();
  });

  it('renders the DayTimeline in active view', () => {
    const tasks = [makeTask({ id: '1', text: '今天的', time: { start: '2026-06-23T15:00' } })];
    const { container } = render(<TaskList {...baseProps} tasks={tasks} sortMode="manual" />);
    expect(container.querySelector('.day-timeline')).toBeInTheDocument();
  });

  it('omits empty groups (only shows groups that have items)', () => {
    const tasks = [makeTask({ id: '1', text: '以后的', time: { start: '2026-06-25T10:00' } })];
    render(<TaskList {...baseProps} tasks={tasks} sortMode="time" />);
    expect(screen.getByText('以后')).toBeInTheDocument();
    expect(screen.queryByText('已过期')).not.toBeInTheDocument();
    expect(screen.queryByText('今天')).not.toBeInTheDocument();
    expect(screen.queryByText('待安排')).not.toBeInTheDocument();
  });

  it('disables only the pending mutation control and its destructive conflicts', () => {
    const tasks = [
      makeTask({ id: '1', text: '正在完成' }),
      makeTask({ id: '2', text: '正在编辑' }),
    ];
    render(
      <TaskList
        {...baseProps}
        tasks={tasks}
        sortMode="manual"
        pendingMutations={new Map<string, Set<TaskMutationKind>>([
          ['1', new Set(['toggle'])],
          ['2', new Set(['edit'])],
        ])}
        reorderPending={false}
      />,
    );

    const pendingItem = document.querySelector('[data-task-id="1"]');
    const availableItem = document.querySelector('[data-task-id="2"]');
    expect(pendingItem?.querySelector('button[aria-label="标记为已完成"]')).toBeDisabled();
    expect(pendingItem?.querySelector('button[aria-label="编辑任务"]')).toBeEnabled();
    expect(pendingItem?.querySelector('button[aria-label="删除任务"]')).toBeDisabled();
    expect(availableItem?.querySelector('button[aria-label="标记为已完成"]')).toBeEnabled();
    expect(availableItem?.querySelector('button[aria-label="编辑任务"]')).toBeDisabled();
    expect(availableItem?.querySelector('button[aria-label="删除任务"]')).toBeDisabled();
  });

  it('keeps edit and completion available while reorder is pending', () => {
    const tasks = [makeTask({ id: '1', text: '可编辑任务' })];
    render(
      <TaskList
        {...baseProps}
        tasks={tasks}
        sortMode="manual"
        reorderPending
      />,
    );

    const item = document.querySelector('[data-task-id="1"]');
    expect(item).toHaveAttribute('draggable', 'false');
    expect(item?.querySelector('button[aria-label="标记为已完成"]')).toBeEnabled();
    expect(item?.querySelector('button[aria-label="编辑任务"]')).toBeEnabled();
    expect(item?.querySelector('button[aria-label="删除任务"]')).toBeDisabled();
  });
});
