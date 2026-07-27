import { useI18n } from '@/features/i18n/I18nProvider';
import type {
  AssistantProposalBatch,
  ConfirmProposalItemInput,
} from '@/shared/api/contracts';

interface DeleteProposalCardProps {
  batch: AssistantProposalBatch;
  submitting: boolean;
  onConfirm: (id: string, items: ConfirmProposalItemInput[]) => void | Promise<unknown>;
  onReject: (id: string) => void | Promise<unknown>;
}

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

function formatTime(value: string | undefined): string | null {
  return value ? value.replace('T', ' ') : null;
}

function DeleteProposalCard({
  batch,
  submitting,
  onConfirm,
  onReject,
}: DeleteProposalCardProps) {
  const { t, errorText } = useI18n();
  const proposal = batch.proposals[0];
  const snapshot = proposal?.beforeSnapshot ?? null;
  const currentBatch = batch.status === 'pending' || batch.status === 'partially_applied';
  const pending = currentBatch && proposal?.status === 'pending';
  const statusText = proposal?.status === 'accepted'
    ? t('assistant.accepted')
    : proposal?.status === 'rejected'
      ? t('assistant.rejected')
      : null;

  const content = <>
    <section className={[
      'assistant-proposal-item',
      `assistant-proposal-item--${proposal?.status ?? 'rejected'}`,
      proposal?.lastError ? 'assistant-proposal-item--error' : '',
    ].filter(Boolean).join(' ')}>
      <div className="assistant-proposal-item__header">
        <strong>
          {snapshot
            ? t('assistant.deleteTarget', { task: snapshot.text })
            : t('assistant.proposalDelete')}
        </strong>
        {statusText && <span>{statusText}</span>}
      </div>
      {snapshot ? (
        <dl className="assistant-delete-target">
          <div><dt>{t('create.priority')}</dt><dd>{t(PRIORITY_KEYS[snapshot.priority])}</dd></div>
          <div><dt>{t('create.category')}</dt><dd>{t(CATEGORY_KEYS[snapshot.category ?? 'other'])}</dd></div>
          <div>
            <dt>{t('time.start')}</dt>
            <dd>{formatTime(snapshot.time?.start) ?? t('detail.noTime')}</dd>
          </div>
          <div>
            <dt>{t('time.end')}</dt>
            <dd>{formatTime(snapshot.time?.end) ?? t('detail.noTime')}</dd>
          </div>
          <div><dt>{t('detail.notes')}</dt><dd>{snapshot.notes ?? '—'}</dd></div>
          <div>
            <dt>{t('detail.completed')}</dt>
            <dd>{snapshot.completed ? t('detail.completed') : t('detail.notCompleted')}</dd>
          </div>
        </dl>
      ) : (
        <p className="assistant-proposal-item__unavailable">
          {t('assistant.targetUnavailable')}
        </p>
      )}
      {proposal?.lastError && (
        <p className="assistant-proposal-item__error">
          {t('assistant.proposalError', { error: errorText(proposal.lastError) })}
        </p>
      )}
    </section>
    {proposal && pending && (
      <div className="assistant-proposal__actions">
        {snapshot && (
          <button
            className="assistant-proposal__accept"
            disabled={submitting}
            onClick={() => void onConfirm(batch.id, [{
              proposalId: proposal.id,
              payload: null,
            }])}
          >
            {t('assistant.confirmDelete')}
          </button>
        )}
        <button disabled={submitting} onClick={() => void onReject(batch.id)}>
          {t('assistant.reject')}
        </button>
      </div>
    )}
  </>;

  if (batch.status === 'superseded') {
    return (
      <details className="assistant-proposal-batch assistant-proposal-batch--superseded">
        <summary>{t('assistant.superseded')}</summary>
        {content}
      </details>
    );
  }

  return (
    <div className={`assistant-proposal-batch assistant-proposal-batch--${batch.status}`}>
      {content}
    </div>
  );
}

export default DeleteProposalCard;
