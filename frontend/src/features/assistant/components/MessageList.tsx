import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantMessage, AssistantProposal } from '@/shared/api/contracts';
import ProposalCard from './ProposalCard';

interface MessageListProps {
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
  sending: boolean;
  onRetry: () => void;
  onResolve: (id: string, action: 'accept' | 'reject') => Promise<void>;
}

function MessageList({ messages, proposals, sending, onRetry, onResolve }: MessageListProps) {
  const { t } = useI18n();
  if (messages.length === 0 && !sending) {
    return <div className="assistant-messages assistant-messages--empty">
      {t('assistant.emptyConversation')}
    </div>;
  }
  return (
    <div className="assistant-messages">
      {messages.map(message => (
        <div key={message.id}>
          <div className={`assistant-bubble assistant-bubble--${message.role}`}>
            {message.content && <p>{message.content}</p>}
            {message.attachments.map(attachment => (
              <span key={attachment.fileId} className="assistant-attachment">
                📎 {attachment.name}
              </span>
            ))}
            {message.status === 'failed' && (
              <p className="assistant-bubble__failed">
                {t('assistant.failed')}
                <button onClick={onRetry}>{t('assistant.retry')}</button>
              </p>
            )}
          </div>
          {proposals
            .filter(proposal => proposal.messageId === message.id)
            .map(proposal => (
              <ProposalCard key={proposal.id} proposal={proposal} onResolve={onResolve} />
            ))}
        </div>
      ))}
      {sending && <div className="assistant-bubble assistant-bubble--assistant">
        {t('assistant.thinking')}
      </div>}
    </div>
  );
}

export default MessageList;
