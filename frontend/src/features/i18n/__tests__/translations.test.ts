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
      'assistant.taskTitle', 'assistant.target', 'assistant.before',
      'assistant.after', 'assistant.confirmBatch', 'assistant.retryRemaining',
      'assistant.partiallyApplied', 'assistant.superseded',
      'assistant.deleteTarget', 'assistant.confirmDelete',
      'assistant.targetUnavailable', 'assistant.validationTitle',
      'assistant.validationTime', 'assistant.proposalError',
      'assistant.setupRequired', 'assistant.setupHint', 'assistant.apiKey',
      'assistant.apiKeySaved', 'assistant.chatModel', 'assistant.audioModel',
      'assistant.save', 'assistant.saved', 'assistant.openAssistant',
      'assistant.deleteConversation', 'assistant.emptyConversation',
      'errors.assistantNotConfigured', 'errors.assistantUnavailable',
      'errors.uploadTooLarge', 'errors.unsupportedFileType',
      'errors.documentNotReadable', 'errors.conversationNotFound',
      'errors.proposalNotFound', 'errors.proposalAlreadyResolved',
      'errors.taskChangedSinceProposal', 'errors.invalidConfirmation',
      'errors.resultVerification', 'errors.proposalBatchState',
      'errors.assistantTurnActive',
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
    expect(translationForError('zh-CN', 'TASK_CHANGED_SINCE_PROPOSAL'))
      .toBe(translate('zh-CN', 'errors.taskChangedSinceProposal'));
    expect(translationForError('en', 'INVALID_CONFIRMATION_PAYLOAD'))
      .toBe(translate('en', 'errors.invalidConfirmation'));
    expect(translationForError('en', 'RESULT_VERIFICATION_FAILED'))
      .toBe(translate('en', 'errors.resultVerification'));
    expect(translationForError('en', 'PROPOSAL_BATCH_NOT_CONFIRMABLE'))
      .toBe(translate('en', 'errors.proposalBatchState'));
    expect(translationForError('en', 'ASSISTANT_TURN_ACTIVE'))
      .toBe(translate('en', 'errors.assistantTurnActive'));
  });
});
