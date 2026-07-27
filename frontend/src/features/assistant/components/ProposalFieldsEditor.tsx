import { useI18n } from '@/features/i18n/I18nProvider';
import type { ProposalCardFields } from '@/shared/api/contracts';
import type { Category, Priority } from '@/shared/types';

interface ProposalFieldsEditorProps {
  value: ProposalCardFields;
  disabled: boolean;
  onChange: (value: ProposalCardFields) => void;
}

function valueOrNull(value: string): string | null {
  return value === '' ? null : value;
}

function ProposalFieldsEditor({ value, disabled, onChange }: ProposalFieldsEditorProps) {
  const { t } = useI18n();
  return (
    <fieldset className="assistant-proposal-fields" disabled={disabled}>
      <label>
        {t('assistant.taskTitle')}
        <input
          aria-label={t('assistant.taskTitle')}
          value={value.text ?? ''}
          onChange={event => onChange({ ...value, text: event.target.value })}
        />
      </label>
      <label>
        {t('create.priority')}
        <select
          aria-label={t('create.priority')}
          value={value.priority ?? 'medium'}
          onChange={event => onChange({
            ...value,
            priority: event.target.value as Priority,
          })}
        >
          <option value="low">{t('priority.low')}</option>
          <option value="medium">{t('priority.medium')}</option>
          <option value="high">{t('priority.high')}</option>
        </select>
      </label>
      <label>
        {t('create.category')}
        <select
          aria-label={t('create.category')}
          value={value.category ?? 'other'}
          onChange={event => onChange({
            ...value,
            category: event.target.value as Category,
          })}
        >
          <option value="work">{t('category.work')}</option>
          <option value="study">{t('category.study')}</option>
          <option value="life">{t('category.life')}</option>
          <option value="other">{t('category.other')}</option>
        </select>
      </label>
      <label>
        {t('time.start')}
        <input
          aria-label={t('time.start')}
          type="datetime-local"
          value={value.time_start ?? ''}
          onChange={event => onChange({
            ...value,
            time_start: valueOrNull(event.target.value),
          })}
        />
      </label>
      <label>
        {t('time.end')}
        <input
          aria-label={t('time.end')}
          type="datetime-local"
          value={value.time_end ?? ''}
          onChange={event => onChange({
            ...value,
            time_end: valueOrNull(event.target.value),
          })}
        />
      </label>
      <label>
        {t('detail.notes')}
        <textarea
          aria-label={t('detail.notes')}
          value={value.notes ?? ''}
          onChange={event => onChange({
            ...value,
            notes: valueOrNull(event.target.value),
          })}
        />
      </label>
    </fieldset>
  );
}

export default ProposalFieldsEditor;
