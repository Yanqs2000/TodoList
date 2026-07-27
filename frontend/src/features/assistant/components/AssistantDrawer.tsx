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

  const handleDeleteOrClose = () => {
    if (assistant.activeId) {
      void assistant.deleteConversation(assistant.activeId);
    } else {
      onClose();
    }
  };

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
          title={t('assistant.newConversation')} aria-label={t('assistant.newConversation')}>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" width="18" height="18">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
        <button className="icon-btn" onClick={() => setSettingsOpen(prev => !prev)}
          title={t('header.settings')} aria-label={t('header.settings')}>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" width="18" height="18">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
          </svg>
        </button>
        <button className="icon-btn" onClick={handleDeleteOrClose}
          title={assistant.activeId ? t('common.delete') : t('common.close')}
          aria-label={assistant.activeId ? t('common.delete') : t('common.close')}>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" width="18" height="18">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
          </svg>
        </button>
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
            streamingStep={assistant.streamingStep}
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
            voiceMode={assistant.settingsView?.voiceMode ?? 'transcribe'}
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
