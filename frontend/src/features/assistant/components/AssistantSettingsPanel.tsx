import { useEffect, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantSettingsPatch, AssistantSettingsView, VoiceMode } from '@/shared/api/contracts';

interface AssistantSettingsPanelProps {
  view: AssistantSettingsView | null;
  onSave: (patch: AssistantSettingsPatch) => Promise<void>;
}

function AssistantSettingsPanel({ view, onSave }: AssistantSettingsPanelProps) {
  const { t } = useI18n();
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(view?.baseUrl ?? '');
  const [chatModel, setChatModel] = useState(view?.chatModel ?? '');
  const [audioModel, setAudioModel] = useState(view?.audioModel ?? '');
  const [voiceMode, setVoiceMode] = useState<VoiceMode>(view?.voiceMode ?? 'transcribe');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setBaseUrl(view?.baseUrl ?? '');
    setChatModel(view?.chatModel ?? '');
    setAudioModel(view?.audioModel ?? '');
    setVoiceMode(view?.voiceMode ?? 'transcribe');
  }, [view]);

  return (
    <div className="assistant-settings">
      <h3>{t('assistant.setupRequired')}</h3>
      <p>{t('assistant.setupHint')}</p>
      <label>
        {t('assistant.apiKey')}
        <input
          type="password"
          value={apiKey}
          onChange={event => setApiKey(event.target.value)}
          placeholder={view?.hasApiKey ? t('assistant.apiKeySaved') : ''}
        />
      </label>
      <label>
        {t('assistant.baseUrl')}
        <input value={baseUrl} onChange={event => setBaseUrl(event.target.value)} />
      </label>
      <label>
        {t('assistant.chatModel')}
        <input value={chatModel} onChange={event => setChatModel(event.target.value)} />
      </label>
      <label>
        {t('assistant.audioModel')}
        <input value={audioModel} onChange={event => setAudioModel(event.target.value)} />
      </label>
      <fieldset className="assistant-settings__voice-mode">
        <legend>{t('assistant.voiceModeLabel')}</legend>
        <label className="assistant-settings__radio">
          <input
            type="radio"
            name="voiceMode"
            value="transcribe"
            checked={voiceMode === 'transcribe'}
            onChange={() => setVoiceMode('transcribe')}
          />
          <span>{t('assistant.voiceModeTranscribe')}</span>
        </label>
        <label className="assistant-settings__radio">
          <input
            type="radio"
            name="voiceMode"
            value="direct"
            checked={voiceMode === 'direct'}
            onChange={() => setVoiceMode('direct')}
          />
          <span>{t('assistant.voiceModeDirect')}</span>
        </label>
      </fieldset>
      <button
        onClick={() => {
          const patch: AssistantSettingsPatch = { baseUrl, chatModel, audioModel, voiceMode };
          if (apiKey) patch.apiKey = apiKey;
          void onSave(patch).then(() => {
            setSaved(true);
            setApiKey('');
          });
        }}
      >{t('assistant.save')}</button>
      {saved && <span>{t('assistant.saved')}</span>}
    </div>
  );
}

export default AssistantSettingsPanel;
