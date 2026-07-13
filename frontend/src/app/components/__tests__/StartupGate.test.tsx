import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BootstrapSnapshot, TodoApi } from '@/shared/api/contracts';
import StartupGate from '../StartupGate';

const READY_STATE = {
  status: 'ready' as const,
  api: {} as TodoApi,
  snapshot: {
    tasks: [],
    settings: {
      theme: 'workspace-light' as const,
      muted: false,
      shortcut: 'Cmd+Alt+KeyT',
    },
    achievementState: {
      unlocked: [],
      streakDays: 0,
      lastActiveDate: '',
      todayCompleted: 0,
      todayDate: '',
    },
  } satisfies BootstrapSnapshot,
};

describe('StartupGate', () => {
  it('renders loading and unsupported states without the application', () => {
    const { rerender } = render(
      <StartupGate state={{ status: 'loading' }} onRetry={vi.fn()}>
        <div>application</div>
      </StartupGate>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('正在启动本地服务');
    expect(screen.queryByText('application')).not.toBeInTheDocument();

    rerender(
      <StartupGate state={{ status: 'unsupported' }} onRetry={vi.fn()}>
        <div>application</div>
      </StartupGate>,
    );
    expect(screen.getByRole('heading')).toHaveTextContent('请通过桌面应用运行');
  });

  it('renders a blocking error whose only action retries startup', () => {
    const retry = vi.fn();
    render(
      <StartupGate
        state={{ status: 'blocked', message: '本地后端不可用，请重试。' }}
        onRetry={retry}
      >
        <div>application</div>
      </StartupGate>,
    );

    expect(screen.queryByText('application')).not.toBeInTheDocument();
    expect(screen.getByText('本地后端不可用，请重试。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('renders the application only after bootstrap is ready', () => {
    render(
      <StartupGate state={READY_STATE} onRetry={vi.fn()}>
        <div>application</div>
      </StartupGate>,
    );

    expect(screen.getByText('application')).toBeInTheDocument();
  });
});
