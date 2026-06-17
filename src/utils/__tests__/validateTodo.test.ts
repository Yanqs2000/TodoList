import { describe, it, expect } from 'vitest';
import { validateTodo, validateTodoArray } from '../validateTodo';

describe('validateTodo', () => {
  it('accepts a well-formed task', () => {
    const raw = {
      id: 'abc',
      text: 'hi',
      completed: false,
      priority: 'low',
      createdAt: 1,
    };
    expect(validateTodo(raw)).toEqual(raw);
  });

  it('rejects missing id', () => {
    expect(validateTodo({ text: 'x', completed: false, priority: 'low', createdAt: 1 })).toBeNull();
  });

  it('rejects invalid priority', () => {
    expect(validateTodo({ id: 'a', text: 'x', completed: false, priority: 'evil', createdAt: 1 })).toBeNull();
  });

  it('rejects non-boolean completed', () => {
    expect(validateTodo({ id: 'a', text: 'x', completed: 'sure', priority: 'low', createdAt: 1 })).toBeNull();
  });

  it('rejects non-number createdAt', () => {
    expect(validateTodo({ id: 'a', text: 'x', completed: false, priority: 'low', createdAt: 'oops' })).toBeNull();
  });

  it('rejects invalid time format', () => {
    expect(validateTodo({ id: 'a', text: 'x', completed: false, priority: 'low', createdAt: 1, time: { start: 'yesterday' } })).toBeNull();
  });

  it('truncates over-long text/notes', () => {
    const longText = 'a'.repeat(2000);
    const result = validateTodo({ id: 'a', text: longText, notes: longText, completed: false, priority: 'low', createdAt: 1 });
    expect(result?.text.length).toBe(500);
    expect(result?.notes?.length).toBe(2000);
  });

  it('rejects invalid category', () => {
    expect(validateTodo({ id: 'a', text: 'x', completed: false, priority: 'low', createdAt: 1, category: 'foo' })).toBeNull();
  });
});

describe('validateTodoArray', () => {
  it('drops invalid items, keeps valid ones', () => {
    const raw = [
      { id: '1', text: 'ok', completed: false, priority: 'low', createdAt: 1 },
      { id: '2', text: 'bad', completed: 'yes', priority: 'low', createdAt: 1 },
      null,
      'string',
    ];
    const result = validateTodoArray(raw);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('1');
  });

  it('returns empty array for non-array input', () => {
    expect(validateTodoArray(null)).toEqual([]);
    expect(validateTodoArray('foo')).toEqual([]);
    expect(validateTodoArray({})).toEqual([]);
  });
});
