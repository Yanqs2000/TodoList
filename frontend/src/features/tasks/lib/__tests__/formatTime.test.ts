import { describe, expect, it } from 'vitest';
import { formatTimeField } from '../formatTime';

const NOW = new Date('2026-07-26T12:00:00').getTime();

describe('formatTimeField', () => {
  it('shows the year when a task belongs to another year', () => {
    expect(formatTimeField({ start: '2025-07-26T23:06' }, 'zh-CN', NOW))
      .toBe('2025/07/26 23:06');
  });

  it('keeps the compact date for the current year', () => {
    expect(formatTimeField({ start: '2026-07-26T23:06' }, 'zh-CN', NOW))
      .toBe('07/26 23:06');
  });
});
