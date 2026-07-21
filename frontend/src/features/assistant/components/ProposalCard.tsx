import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantProposal } from '@/shared/api/contracts';

interface ProposalCardProps {
  proposal: AssistantProposal;
  onResolve: (id: string, action: 'accept' | 'reject') => Promise<void>;
}

const ACTION_KEYS = {
  create: 'assistant.proposalCreate',
  update: 'assistant.proposalUpdate',
  delete: 'assistant.proposalDelete',
} as const;

const PRIORITY_KEYS = {
  low: 'priority.low',
  medium: 'priority.medium',
  high: 'priority.high',
} as const;

const CATEGORY_KEYS = {
  work: 'category.work',
  study: 'category.study',
  life: 'category.life',
  other: 'category.other',
} as const;

function ProposalCard({ proposal, onResolve }: ProposalCardProps) {
  const { t } = useI18n();
  const { payload } = proposal;
  return (
    <div className={`assistant-proposal assistant-proposal--${proposal.status}`}>
      <div className="assistant-proposal__header">
        <span>{t(ACTION_KEYS[proposal.action])}</span>
        {proposal.status !== 'pending' && (
          <span className="assistant-proposal__status">
            {proposal.status === 'accepted' ? t('assistant.accepted') : t('assistant.rejected')}
          </span>
        )}
      </div>
      {payload.text && <p className="assistant-proposal__text">{payload.text}</p>}
      <div className="assistant-proposal__fields">
        {payload.time_start && <span>{payload.time_start.replace('T', ' ')}</span>}
        {payload.priority && <span>{t(PRIORITY_KEYS[payload.priority])}</span>}
        {payload.category && <span>{t(CATEGORY_KEYS[payload.category])}</span>}
      </div>
      {proposal.status === 'pending' && (
        <div className="assistant-proposal__actions">
          <button className="assistant-proposal__accept"
            onClick={() => void onResolve(proposal.id, 'accept')}>
            {t('assistant.accept')}
          </button>
          <button onClick={() => void onResolve(proposal.id, 'reject')}>
            {t('assistant.reject')}
          </button>
        </div>
      )}
    </div>
  );
}

export default ProposalCard;
