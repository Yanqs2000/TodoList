import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('should show message for all filter', () => {
    render(<EmptyState filter="all" />);
    expect(screen.getByText('还没有任务，添加一个吧')).toBeInTheDocument();
  });

  it('should show message for active filter', () => {
    render(<EmptyState filter="active" />);
    expect(screen.getByText('所有任务都完成了！')).toBeInTheDocument();
  });

  it('should show message for completed filter', () => {
    render(<EmptyState filter="completed" />);
    expect(screen.getByText('还没有已完成的任务')).toBeInTheDocument();
  });
});
