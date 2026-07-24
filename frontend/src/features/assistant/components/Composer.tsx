import { useRef, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import { ApiError, type AssistantAttachment } from '@/shared/api/contracts';
import { WavRecorder } from '../recorder/wav';

const ACCEPT = '.jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.md,.mp3,.wav,.m4a';

interface ComposerProps {
  sending: boolean;
  onSend: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  onError: (error: unknown) => void;
  uploadFile: (file: File) => Promise<AssistantAttachment>;
  transcribe: (fileId: string) => Promise<string>;
}

interface PendingAudio {
  attachment: AssistantAttachment;
}

function Composer({ sending, onSend, onError, uploadFile, transcribe }: ComposerProps) {
  const { t } = useI18n();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [recording, setRecording] = useState(false);
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const recorderRef = useRef<WavRecorder | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const upload = async (file: File) => {
    try {
      return await uploadFile(file);
    } catch (error) {
      onError(error);
      return null;
    }
  };

  const startRecording = async () => {
    try {
      const recorder = new WavRecorder();
      await recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      onError(new ApiError('business', 'MIC_DENIED', 'Microphone denied'));
    }
  };

  const stopRecording = async () => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    setRecording(false);
    if (!recorder) return;
    const blob = await recorder.stop();
    const file = new File([blob], `voice-${Date.now()}.wav`, { type: 'audio/wav' });
    const attachment = await upload(file);
    if (attachment) setPendingAudio({ attachment });
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const attachment = await upload(file);
    if (attachment) {
      if (attachment.kind === 'audio') setPendingAudio({ attachment });
      else setAttachments(prev => [...prev, attachment]);
    }
  };

  const handleSend = async () => {
    const content = text.trim();
    if (!content && attachments.length === 0 && !pendingAudio) return;
    const outgoing = pendingAudio ? [...attachments, pendingAudio.attachment] : attachments;
    await onSend(content, outgoing);
    setText('');
    setAttachments([]);
    setPendingAudio(null);
  };

  return (
    <div className="assistant-composer">
      {attachments.map(attachment => (
        <span key={attachment.fileId} className="assistant-attachment">
          📎 {attachment.name}
          <button
            aria-label={t('common.delete')}
            onClick={() => setAttachments(prev => prev.filter(a => a.fileId !== attachment.fileId))}
          >✕</button>
        </span>
      ))}
      {pendingAudio && (
        <div className="assistant-pending-audio">
          <span>🎙 {pendingAudio.attachment.name}</span>
          <button
            onClick={() => {
              const audio = pendingAudio;
              setPendingAudio(null);
              void (async () => {
                try {
                  setText(await transcribe(audio.attachment.fileId));
                } catch (error) {
                  onError(error);
                }
              })();
            }}
          >{t('assistant.transcribe')}</button>
          <button onClick={() => void handleSend()}>{t('assistant.sendDirectly')}</button>
          <button onClick={() => setPendingAudio(null)}>{t('common.cancel')}</button>
        </div>
      )}
      <div className="assistant-composer__row">
        <textarea
          value={text}
          onChange={event => setText(event.target.value)}
          placeholder={t('assistant.inputPlaceholder')}
          disabled={sending}
          rows={2}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void handleSend();
            }
          }}
        />
        <div className="assistant-composer__buttons">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={event => {
              void handleFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <button className="assistant-composer__tool" onClick={() => fileInputRef.current?.click()} disabled={sending}
            title={t('assistant.attach')} aria-label={t('assistant.attach')}>📎</button>
          <button
            className={recording ? 'assistant-composer__tool assistant-composer__tool--recording' : 'assistant-composer__tool'}
            onClick={() => void (recording ? stopRecording() : startRecording())}
            disabled={sending}
            title={recording ? t('assistant.stopRecording') : t('assistant.record')}
            aria-label={recording ? t('assistant.stopRecording') : t('assistant.record')}
          >{recording ? '⏹' : '🎙'}</button>
          <button
            className="assistant-composer__send"
            onClick={() => void handleSend()}
            disabled={sending || (!text.trim() && attachments.length === 0 && !pendingAudio)}
          >{t('assistant.send')}</button>
        </div>
      </div>
    </div>
  );
}

export default Composer;
