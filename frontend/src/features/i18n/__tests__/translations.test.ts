import { describe, expect, it } from 'vitest';
import { localeFor, translate, translationForError, translationKeys } from '../translations';

describe('translations', () => {
  it('provides every key in both languages', () => {
    expect(translationKeys('zh-CN')).toEqual(translationKeys('en'));
  });

  it('interpolates values without changing user text', () => {
    expect(translate('en', 'feedback.reminder', { task: '写周报' }))
      .toBe('⏰ Time for: 写周报');
  });

  it('maps locales and stable error codes', () => {
    expect(localeFor('zh-CN')).toBe('zh-CN');
    expect(localeFor('en')).toBe('en-US');
    expect(translationForError('en', 'INVALID_REQUEST')).toBe('Invalid request.');
    expect(translationForError('en', 'UNKNOWN')).toBe('Something went wrong. Please try again.');
  });
});
