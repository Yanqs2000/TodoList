import { useEffect, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import type {
  AssistantProposal,
  AssistantProposalBatch,
  ConfirmProposalItemInput,
  ProposalCardFields,
} from '@/shared/api/contracts';
import type { Todo } from '@/shared/types';
import ProposalFieldsEditor from './ProposalFieldsEditor';

interface ProposalBatchCardProps {
  batch: AssistantProposalBatch;
  submitting: boolean;
  onConfirm: (id: string, items: ConfirmProposalItemInput[]) => void | Promise<unknown>;
  onReject: (id: string) => void | Promise<unknown>;
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

function draftsFromBatch(batch: AssistantProposalBatch): Record<string, ProposalCardFields> {
  const drafts: Record<string, ProposalCardFields> = {};
  for (const proposal of batch.proposals) {
    if (proposal.payload !== null) drafts[proposal.id] = proposal.payload;
  }
  return drafts;
}

function formatTime(value: string | null | undefined): string | null {
  return value ? value.replace('T', ' ') : null;
}

function fieldsFromTask(task: Todo): ProposalCardFields {
  return {
    text: task.text,
    priority: task.priority,
    category: task.category ?? 'other',
    time_start: task.time?.start ?? null,
    time_end: task.time?.end ?? null,
    notes: task.notes ?? null,
  };
}

function DiffValues({
  value,
  t,
}: {
  value: ProposalCardFields;
  t: ReturnType<typeof useI18n>['t'];
}) {
  const values = [
    value.text,
    t(PRIORITY_KEYS[value.priority]),
    t(CATEGORY_KEYS[value.category]),
    formatTime(value.time_start),
    formatTime(value.time_end),
    value.notes,
  ].filter((item): item is string => Boolean(item));
  return <div className="assistant-proposal-diff__values">
    {values.map((item, index) => <span key={`${index}-${item}`}>{item}</span>)}
  </div>;
}

function itemStatusText(
  proposal: AssistantProposal,
  t: ReturnType<typeof useI18n>['t'],
): string | null {
  if (proposal.status === 'accepted') return t('assistant.accepted');
  if (proposal.status === 'rejected') return t('assistant.rejected');
  return null;
}

function ProposalBatchCard({
  batch,
  submitting,
  onConfirm,
  onReject,
}: ProposalBatchCardProps) {
  const { t, errorText } = useI18n();
  const [drafts, setDrafts] = useState<Record<string, ProposalCardFields>>(
    () => draftsFromBatch(batch),
  );
  const syncKey = JSON.stringify([
    batch.id,
    batch.status,
    batch.proposals.map(proposal => [
      proposal.id, proposal.status, proposal.payload, proposal.lastError,
    ]),
  ]);

  useEffect(() => {
    setDrafts(draftsFromBatch(batch));
  }, [batch, syncKey]);

  const currentBatch = batch.status === 'pending' || batch.status === 'partially_applied';
  const pending = currentBatch ? batch.proposals.filter(proposal => (
    proposal.status === 'pending' && proposal.payload !== null
  )) : [];
  const hasPendingRows = currentBatch && batch.proposals.some(proposal => (
    proposal.status === 'pending'
  ));
  const invalid = pending.some(proposal => {
    const fields = drafts[proposal.id];
    return !fields?.text?.trim()
      || Boolean(fields.time_end && !fields.time_start)
      || Boolean(fields.time_start && fields.time_end && fields.time_end < fields.time_start);
  });

  const confirm = () => onConfirm(batch.id, pending.map(proposal => ({
    proposalId: proposal.id,
    payload: drafts[proposal.id] ?? proposal.payload,
  })));

  const content = <>
    {batch.status === 'partially_applied' && (
      <p className="assistant-proposal-batch__status">{t('assistant.partiallyApplied')}</p>
    )}
    {batch.proposals.map(proposal => {
      const fields = drafts[proposal.id];
      const titleInvalid = proposal.status === 'pending' && fields !== undefined
        && !fields.text.trim();
      const timeInvalid = proposal.status === 'pending' && fields !== undefined
        && (Boolean(fields.time_end && !fields.time_start)
          || Boolean(fields.time_start && fields.time_end && fields.time_end < fields.time_start));
      const statusText = itemStatusText(proposal, t);
      return (
        <section
          key={proposal.id}
          className={[
            'assistant-proposal-item',
            `assistant-proposal-item--${proposal.status}`,
            proposal.lastError ? 'assistant-proposal-item--error' : '',
          ].filter(Boolean).join(' ')}
        >
          <div className="assistant-proposal-item__header">
            <strong>{t(ACTION_KEYS[proposal.action])}</strong>
            {statusText && <span>{statusText}</span>}
          </div>
          {proposal.action === 'update' && proposal.beforeSnapshot && fields && (
            <>
              <p className="assistant-proposal-item__target">
                {t('assistant.target', { task: proposal.beforeSnapshot.text })}
              </p>
              <div className="assistant-proposal-diff">
                <div>
                  <strong>{t('assistant.before')}</strong>
                  <DiffValues value={fieldsFromTask(proposal.beforeSnapshot)} t={t} />
                </div>
                <div>
                  <strong>{t('assistant.after')}</strong>
                  <DiffValues value={fields} t={t} />
                </div>
              </div>
            </>
          )}
          {fields ? (
            <ProposalFieldsEditor
              value={fields}
              disabled={submitting || proposal.status !== 'pending' || !currentBatch}
              onChange={value => setDrafts(current => ({
                ...current,
                [proposal.id]: value,
              }))}
            />
          ) : (
            <p className="assistant-proposal-item__unavailable">
              {t('assistant.targetUnavailable')}
            </p>
          )}
          {titleInvalid && (
            <p className="assistant-proposal-item__validation">{t('assistant.validationTitle')}</p>
          )}
          {timeInvalid && (
            <p className="assistant-proposal-item__validation">{t('assistant.validationTime')}</p>
          )}
          {proposal.lastError && (
            <p className="assistant-proposal-item__error">
              {t('assistant.proposalError', { error: errorText(proposal.lastError) })}
            </p>
          )}
        </section>
      );
    })}
    {hasPendingRows && (
      <div className="assistant-proposal__actions">
        {pending.length > 0 && (
          <button
            className="assistant-proposal__accept"
            disabled={submitting || invalid}
            onClick={() => void confirm()}
          >
            {batch.status === 'partially_applied'
              ? t('assistant.retryRemaining', { count: pending.length })
              : t('assistant.confirmBatch', { count: pending.length })}
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

export default ProposalBatchCard;
