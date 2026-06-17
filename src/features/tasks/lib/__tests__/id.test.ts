import { describe, it, expect } from 'vitest';
import { generateId } from '../id';

describe('generateId', () => {
  it('returns a string', () => {
    expect(typeof generateId()).toBe('string');
  });

  it('produces unique ids across 5000 calls', () => {
    const ids = new Set<string>();
    for (let i = 0; i < 5000; i++) {
      ids.add(generateId());
    }
    expect(ids.size).toBe(5000);
  });

  it('produces ids longer than 16 chars', () => {
    expect(generateId().length).toBeGreaterThan(16);
  });
});
