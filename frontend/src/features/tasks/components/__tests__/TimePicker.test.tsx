import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import TimePicker from '../TimePicker';

afterEach(() => {
  vi.useRealTimers();
});

describe('TimePicker', () => {
  it('moves an old event to the actual current date', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-26T12:00:00'));
    const onTimeChange = vi.fn();

    render(
      <I18nProvider language="zh-CN">
        <TimePicker
          time={{ start: '2025-07-26T23:06' }}
          onTimeChange={onTimeChange}
          onClose={vi.fn()}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '今天' }));
    fireEvent.click(screen.getByRole('button', { name: '确定' }));

    expect(onTimeChange).toHaveBeenCalledWith({
      start: '2026-07-26T23:06',
      end: undefined,
    });
  });
});
