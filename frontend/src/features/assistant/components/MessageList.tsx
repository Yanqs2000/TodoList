import { useI18n } from '@/features/i18n/I18nProvider';
import type {
  AssistantMessage,
  AssistantProposalBatch,
  ConfirmProposalItemInput,
} from '@/shared/api/contracts';
import DeleteProposalCard from './DeleteProposalCard';
import ProposalBatchCard from './ProposalBatchCard';

interface MessageListProps {
  messages: AssistantMessage[];
  proposalBatches: AssistantProposalBatch[];
  submittingBatchIds: ReadonlySet<string>;
  sending: boolean;
  onRetry: (turnId: string) => void | Promise<void>;
  onConfirmBatch: (
    id: string,
    items: ConfirmProposalItemInput[],
  ) => void | Promise<unknown>;
  onRejectBatch: (id: string) => void | Promise<unknown>;
}

function MessageList({
  messages,
  proposalBatches,
  submittingBatchIds,
  sending,
  onRetry,
  onConfirmBatch,
  onRejectBatch,
}: MessageListProps) {
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
                {message.turnId !== null && (
                  <button onClick={() => void onRetry(message.turnId!)}>
                    {t('assistant.retry')}
                  </button>
                )}
              </p>
            )}
          </div>
          {proposalBatches
            .filter(batch => batch.messageId === message.id)
            .map(batch => {
              const props = {
                batch,
                submitting: submittingBatchIds.has(batch.id),
                onConfirm: onConfirmBatch,
                onReject: onRejectBatch,
              };
              return batch.proposals.length === 1 && batch.proposals[0]?.action === 'delete'
                ? <DeleteProposalCard key={batch.id} {...props} />
                : <ProposalBatchCard key={batch.id} {...props} />;
            })}
        </div>
      ))}
      {sending && <div className="assistant-bubble assistant-bubble--assistant">
        {t('assistant.thinking')}
      </div>}
    </div>
  );
}

export default MessageList;
