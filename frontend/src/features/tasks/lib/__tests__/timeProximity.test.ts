import { describe, it, expect } from 'vitest';
import { proximityOf, isToday, toTimelineX, parseTimeStart } from '../timeProximity';

// Fixed "now": 2026-06-23T13:00 local.
const NOW = new Date('2026-06-23T13:00').getTime();

describe('parseTimeStart', () => {
  it('parses local ISO datetime', () => {
    expect(parseTimeStart('2026-06-23T14:30')).toBe(new Date('2026-06-23T14:30').getTime());
  });

  it('returns null for garbage', () => {
    expect(parseTimeStart('not-a-date')).toBeNull();
  });
});

describe('isToday', () => {
  it('true for same calendar day', () => {
    expect(isToday('2026-06-23T08:00', NOW)).toBe(true);
  });

  it('false for a different day', () => {
    expect(isToday('2026-06-24T08:00', NOW)).toBe(false);
    expect(isToday('2026-06-22T23:59', NOW)).toBe(false);
  });

  it('false for unparseable', () => {
    expect(isToday('oops', NOW)).toBe(false);
  });
});

describe('proximityOf', () => {
  it('none when no time', () => {
    expect(proximityOf(undefined, NOW)).toBe('none');
    expect(proximityOf({ start: '' }, NOW)).toBe('none');
  });

  it('overdue when start is in the past', () => {
    expect(proximityOf({ start: '2026-06-23T12:59' }, NOW)).toBe('overdue');
  });

  it('soon when within the next hour (inclusive upper bound)', () => {
    // 13:00 now → up to 14:00 is "soon"
    expect(proximityOf({ start: '2026-06-23T13:30' }, NOW)).toBe('soon');
    expect(proximityOf({ start: '2026-06-23T14:00' }, NOW)).toBe('soon');
  });

  it('today when later today beyond 1h', () => {
    expect(proximityOf({ start: '2026-06-23T15:00' }, NOW)).toBe('today');
    expect(proximityOf({ start: '2026-06-23T23:30' }, NOW)).toBe('today');
  });

  it('future when on a later calendar day', () => {
    expect(proximityOf({ start: '2026-06-24T08:00' }, NOW)).toBe('future');
  });
});

describe('toTimelineX', () => {
  it('06:00 maps to 0 (left edge of the 06–24 window)', () => {
    expect(toTimelineX('2026-06-23T06:00')).toBe(0);
  });

  it('maps mid-day proportionally (12:00 → ~33%)', () => {
    expect(toTimelineX('2026-06-23T12:00')).toBeCloseTo((6 / 18) * 100, 5);
  });

  it('maps late evening (23:00 → ~94%)', () => {
    expect(toTimelineX('2026-06-23T23:00')).toBeCloseTo((17 / 18) * 100, 5);
  });

  it('before 06:00 clamps to 0 (00:00, 04:00, 05:59)', () => {
    expect(toTimelineX('2026-06-23T00:00')).toBe(0);
    expect(toTimelineX('2026-06-23T04:00')).toBe(0);
    expect(toTimelineX('2026-06-23T05:59')).toBe(0);
  });

  it('null for unparseable', () => {
    expect(toTimelineX('oops')).toBeNull();
  });
});
