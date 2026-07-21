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

  it('provides assistant copy in both languages', () => {
    const keys = [
      'assistant.title', 'assistant.newConversation', 'assistant.untitled',
      'assistant.inputPlaceholder', 'assistant.send', 'assistant.attach',
      'assistant.record', 'assistant.stopRecording', 'assistant.transcribe',
      'assistant.sendDirectly', 'assistant.thinking', 'assistant.retry',
      'assistant.failed', 'assistant.accept', 'assistant.reject',
      'assistant.accepted', 'assistant.rejected', 'assistant.proposalCreate',
      'assistant.proposalUpdate', 'assistant.proposalDelete',
      'assistant.setupRequired', 'assistant.setupHint', 'assistant.apiKey',
      'assistant.apiKeySaved', 'assistant.chatModel', 'assistant.audioModel',
      'assistant.save', 'assistant.saved', 'assistant.openAssistant',
      'assistant.deleteConversation', 'assistant.emptyConversation',
      'errors.assistantNotConfigured', 'errors.assistantUnavailable',
      'errors.uploadTooLarge', 'errors.unsupportedFileType',
      'errors.documentNotReadable', 'errors.conversationNotFound',
      'errors.proposalNotFound', 'errors.proposalAlreadyResolved',
    ] as const;
    for (const key of keys) {
      expect(translate('zh-CN', key)).not.toBe(key);
      expect(translate('en', key)).not.toBe(key);
    }
    expect(translationForError('zh-CN', 'ASSISTANT_NOT_CONFIGURED'))
      .toBe(translate('zh-CN', 'errors.assistantNotConfigured'));
    expect(translationForError('en', 'ASSISTANT_UNAVAILABLE'))
      .toBe(translate('en', 'errors.assistantUnavailable'));
    expect(translationForError('en', 'UPLOAD_TOO_LARGE'))
      .toBe(translate('en', 'errors.uploadTooLarge'));
  });
});
