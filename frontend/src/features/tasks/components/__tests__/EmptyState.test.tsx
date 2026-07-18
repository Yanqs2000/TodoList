import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmptyState from '../EmptyState';
import { I18nProvider } from '@/features/i18n/I18nProvider';

describe('EmptyState', () => {
  it('should show "no tasks yet" when there are no tasks at all (default)', () => {
    render(<EmptyState filter="active" />);
    expect(screen.getByText('还没有任务，添加一个吧')).toBeInTheDocument();
  });

  it('should show "all done" only when there are tasks but active filter is empty', () => {
    render(<EmptyState filter="active" hasAnyTasks={true} />);
    expect(screen.getByText('所有任务都完成了！')).toBeInTheDocument();
  });

  it('should show "no completed" when filter=completed and tasks exist', () => {
    render(<EmptyState filter="completed" hasAnyTasks={true} />);
    expect(screen.getByText('还没有已完成的任务')).toBeInTheDocument();
  });

  it('should show "no matching" when filter=all but list is empty (search/category)', () => {
    render(<EmptyState filter="all" hasAnyTasks={true} />);
    expect(screen.getByText('没有匹配的任务')).toBeInTheDocument();
  });

  it('should show "no tasks yet" regardless of filter when hasAnyTasks is false', () => {
    render(<EmptyState filter="completed" hasAnyTasks={false} />);
    expect(screen.getByText('还没有任务，添加一个吧')).toBeInTheDocument();
  });

  it('renders English copy when the application language is English', () => {
    render(
      <I18nProvider language="en">
        <EmptyState filter="active" hasAnyTasks={true} />
      </I18nProvider>,
    );
    expect(screen.getByText('All tasks are complete!')).toBeInTheDocument();
  });
});
