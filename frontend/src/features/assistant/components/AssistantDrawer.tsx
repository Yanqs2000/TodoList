import { useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { ProposalApplyItemResult, TodoApi } from '@/shared/api/contracts';
import type { AssistantState } from '../hooks/useAssistant';
import AssistantSettingsPanel from './AssistantSettingsPanel';
import Composer from './Composer';
import MessageList from './MessageList';
import '../styles/assistant.css';

interface AssistantDrawerProps {
  open: boolean;
  onClose: () => void;
  assistant: AssistantState;
  api: TodoApi;
  onApplyProposal: (result: ProposalApplyItemResult) => void;
  onError: (error: unknown) => void;
}

function AssistantDrawer({ open, onClose, assistant, api, onApplyProposal, onError }: AssistantDrawerProps) {
  const { t } = useI18n();
  const [settingsOpen, setSettingsOpen] = useState(false);
  if (!open) return null;

  const needsSetup = assistant.settingsView !== null && !assistant.settingsView.hasApiKey;
  const showSettings = needsSetup || settingsOpen;

  return (
    <aside className="assistant-drawer" aria-label={t('assistant.title')}>
      <div className="assistant-drawer__header">
        <span className="assistant-drawer__title">{t('assistant.title')}</span>
        <select
          className="assistant-drawer__conversations"
          value={assistant.activeId ?? ''}
          onChange={event => {
            if (event.target.value) void assistant.selectConversation(event.target.value);
          }}
          aria-label={t('assistant.title')}
        >
          {assistant.activeId === null && (
            <option value="">{t('assistant.newConversation')}</option>
          )}
          {assistant.conversations.map(conversation => (
            <option key={conversation.id} value={conversation.id}>
              {conversation.title || t('assistant.untitled')}
            </option>
          ))}
        </select>
        <button className="icon-btn" onClick={assistant.startNewConversation}
          title={t('assistant.newConversation')} aria-label={t('assistant.newConversation')}>＋</button>
        <button className="icon-btn" onClick={() => setSettingsOpen(prev => !prev)}
          title={t('header.settings')} aria-label={t('header.settings')}>⚙</button>
        <button className="icon-btn" onClick={onClose}
          title={t('common.close')} aria-label={t('common.close')}>✕</button>
      </div>
      {showSettings ? (
        <AssistantSettingsPanel
          view={assistant.settingsView}
          onSave={async patch => {
            const saved = await assistant.saveSettings(patch);
            if (saved) setSettingsOpen(false);
          }}
        />
      ) : (
        <>
          <MessageList
            messages={assistant.messages}
            proposalBatches={assistant.proposalBatches}
            submittingBatchIds={assistant.submittingBatchIds}
            sending={assistant.sending}
            onRetry={assistant.retry}
            onConfirmBatch={async (id, items) => {
              const result = await assistant.confirmBatch(id, items);
              for (const item of result?.items ?? []) {
                if (item.proposal.status === 'accepted') {
                  onApplyProposal(item);
                }
              }
            }}
            onRejectBatch={assistant.rejectBatch}
          />
          <Composer
            sending={assistant.sending}
            onSend={assistant.send}
            onError={onError}
            uploadFile={file => api.uploadAssistantFile(file)}
            transcribe={fileId => api.transcribeAssistantAudio(fileId)}
          />
        </>
      )}
    </aside>
  );
}

export default AssistantDrawer;
