import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DayTimeline from '../DayTimeline';
import type { Todo } from '@/shared/types';

// Fixed "now": 2026-06-23T13:00 local.
const NOW = new Date('2026-06-23T13:00').getTime();

function makeTask(partial: Partial<Todo>): Todo {
  return {
    id: 'x',
    text: 'task',
    completed: false,
    priority: 'low',
    createdAt: 1,
    ...partial,
  };
}

describe('DayTimeline', () => {
  it('renders a block for a task timed today', () => {
    const task = makeTask({ id: '1', text: '写周报', time: { start: '2026-06-23T09:30' } });
    render(<DayTimeline tasks={[task]} now={NOW} />);
    expect(screen.getByRole('button', { name: /写周报/ })).toBeInTheDocument();
  });

  it('shows the empty hint when no tasks are timed today', () => {
    render(<DayTimeline tasks={[]} now={NOW} />);
    expect(screen.getByText('今天还没有计划任务')).toBeInTheDocument();
  });

  it('calls onSelectTask with the id when a block is clicked', () => {
    const task = makeTask({ id: '1', text: '写周报', time: { start: '2026-06-23T09:30' } });
    const onSelectTask = vi.fn();
    render(<DayTimeline tasks={[task]} now={NOW} onSelectTask={onSelectTask} />);
    fireEvent.click(screen.getByRole('button', { name: /写周报/ }));
    expect(onSelectTask).toHaveBeenCalledWith('1');
  });

  it('shows a 待安排 cluster count for unscheduled tasks', () => {
    const unscheduled = makeTask({ id: '2', text: '读文档' });
    render(<DayTimeline tasks={[unscheduled]} now={NOW} />);
    expect(screen.getByText(/待安排 \(1\)/)).toBeInTheDocument();
  });

  it('does not render a block for a future-dated task (not today)', () => {
    const future = makeTask({ id: '3', text: '下周开会', time: { start: '2026-06-25T10:00' } });
    render(<DayTimeline tasks={[future]} now={NOW} />);
    expect(screen.queryByRole('button', { name: /下周开会/ })).not.toBeInTheDocument();
    // future is scheduled (has time) so it is not counted as 待安排
    expect(screen.queryByText(/待安排/)).not.toBeInTheDocument();
    // and no today task → empty hint
    expect(screen.getByText('今天还没有计划任务')).toBeInTheDocument();
  });

  it('renders the now indicator line during the 06–24 window', () => {
    const { container } = render(<DayTimeline tasks={[]} now={NOW} />);
    expect(container.querySelector('.day-timeline__now')).toBeInTheDocument();
  });

  it('hides the now indicator line before 06:00 (outside the window)', () => {
    const early = new Date('2026-06-23T03:00').getTime();
    const { container } = render(<DayTimeline tasks={[]} now={early} />);
    expect(container.querySelector('.day-timeline__now')).not.toBeInTheDocument();
  });
});
