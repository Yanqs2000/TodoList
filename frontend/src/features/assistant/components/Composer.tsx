import { useRef, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import { ApiError, type AssistantAttachment, type VoiceMode } from '@/shared/api/contracts';
import { WavRecorder } from '../recorder/wav';

const ACCEPT = '.jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.md,.mp3,.wav,.m4a';

type InputMode = 'text' | 'voice';

interface ComposerProps {
  sending: boolean;
  voiceMode: VoiceMode;
  onSend: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  onError: (error: unknown) => void;
  uploadFile: (file: File) => Promise<AssistantAttachment>;
  transcribe: (fileId: string) => Promise<string>;
}

interface PendingAudio {
  attachment: AssistantAttachment;
}

function Composer({ sending, voiceMode, onSend, onError, uploadFile, transcribe }: ComposerProps) {
  const { t } = useI18n();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [inputMode, setInputMode] = useState<InputMode>('text');
  const [recording, setRecording] = useState(false);
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const recorderRef = useRef<WavRecorder | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const voiceButtonRef = useRef<HTMLButtonElement | null>(null);

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

  const stopRecording = async (): Promise<AssistantAttachment | null> => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    setRecording(false);
    if (!recorder) return null;
    const blob = await recorder.stop();
    const file = new File([blob], `voice-${Date.now()}.wav`, { type: 'audio/wav' });
    return upload(file);
  };

  const cancelRecording = () => {
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setRecording(false);
  };

  // ---- Voice mode press-and-hold handlers ----

  const handleVoiceDown = () => {
    if (sending || voiceProcessing) return;
    void startRecording();
  };

  const handleVoiceUp = () => {
    if (!recorderRef.current) return;
    setVoiceProcessing(true);
    void (async () => {
      const attachment = await stopRecording();
      if (!attachment) {
        setVoiceProcessing(false);
        return;
      }
      if (voiceMode === 'transcribe') {
        try {
          const transcribed = await transcribe(attachment.fileId);
          await onSend(transcribed, [attachment]);
        } catch (error) {
          onError(error);
        }
      } else {
        await onSend('', [attachment]);
      }
      setVoiceProcessing(false);
    })();
  };

  // Cancel if pointer leaves the button while recording
  const handleVoiceLeave = () => {
    if (recording) cancelRecording();
  };

  // ---- Text mode handlers ----

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const attachment = await upload(file);
    if (attachment) {
      if (attachment.kind === 'audio') setPendingAudio({ attachment });
      else setAttachments(prev => [...prev, attachment]);
    }
  };

  const handleTextSend = async () => {
    const content = text.trim();
    if (!content && attachments.length === 0 && !pendingAudio) return;
    const outgoing = pendingAudio ? [...attachments, pendingAudio.attachment] : attachments;
    await onSend(content, outgoing);
    setText('');
    setAttachments([]);
    setPendingAudio(null);
  };

  // ---- Render: voice mode ----

  if (inputMode === 'voice') {
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
        <div className="assistant-composer__row">
          <button
            ref={voiceButtonRef}
            className={`assistant-composer__voice-btn${recording ? ' assistant-composer__voice-btn--recording' : ''}${voiceProcessing ? ' assistant-composer__voice-btn--processing' : ''}`}
            disabled={sending || voiceProcessing}
            onMouseDown={handleVoiceDown}
            onMouseUp={handleVoiceUp}
            onMouseLeave={handleVoiceLeave}
            onTouchStart={e => { e.preventDefault(); handleVoiceDown(); }}
            onTouchEnd={e => { e.preventDefault(); handleVoiceUp(); }}
            aria-label={recording ? t('assistant.releaseToSend') : t('assistant.holdToRecord')}
          >
            {voiceProcessing
              ? '…'
              : recording
                ? t('assistant.releaseToSend')
                : t('assistant.holdToRecord')
            }
          </button>
          <div className="assistant-composer__buttons assistant-composer__buttons--voice">
            <button
              className="assistant-composer__tool"
              onClick={() => setInputMode('text')}
              disabled={sending || voiceProcessing}
              title={t('assistant.textInput')}
              aria-label={t('assistant.textInput')}
            >⌨</button>
          </div>
        </div>
      </div>
    );
  }

  // ---- Render: text mode ----

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
          <button onClick={() => void handleTextSend()}>{t('assistant.sendDirectly')}</button>
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
              void handleTextSend();
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
            onClick={() => void (recording ? cancelRecording() : startRecording())}
            disabled={sending}
            title={recording ? t('assistant.stopRecording') : t('assistant.record')}
            aria-label={recording ? t('assistant.stopRecording') : t('assistant.record')}
          >{recording ? '⏹' : '🎙'}</button>
          <button
            className="assistant-composer__tool"
            onClick={() => setInputMode('voice')}
            disabled={sending}
            title={t('assistant.voiceInput')}
            aria-label={t('assistant.voiceInput')}
          >🎤</button>
          <button
            className="assistant-composer__send"
            onClick={() => void handleTextSend()}
            disabled={sending || (!text.trim() && attachments.length === 0 && !pendingAudio)}
          >{t('assistant.send')}</button>
        </div>
      </div>
    </div>
  );
}

export default Composer;
