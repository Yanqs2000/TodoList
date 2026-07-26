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

interface VoicePress {
  pointerId: number;
  released: boolean;
  cancelled: boolean;
  finishing: boolean;
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
  const voicePressRef = useRef<VoicePress | null>(null);
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
      return recorder;
    } catch {
      onError(new ApiError('business', 'MIC_DENIED', 'Microphone denied'));
      return null;
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

  const finishVoicePress = (press: VoicePress) => {
    if (press.finishing || press.cancelled || !recorderRef.current) return;
    press.finishing = true;
    voicePressRef.current = null;
    setVoiceProcessing(true);
    void (async () => {
      try {
        const attachment = await stopRecording();
        if (!attachment) return;
        if (voiceMode === 'transcribe') {
          const transcribed = await transcribe(attachment.fileId);
          await onSend(transcribed, [attachment]);
        } else {
          await onSend('', [attachment]);
        }
      } catch (error) {
        onError(error);
      } finally {
        setVoiceProcessing(false);
      }
    })();
  };

  const handleVoicePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || sending || voiceProcessing || voicePressRef.current) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const press: VoicePress = {
      pointerId: event.pointerId,
      released: false,
      cancelled: false,
      finishing: false,
    };
    voicePressRef.current = press;

    void (async () => {
      const recorder = await startRecording();
      if (!recorder) {
        if (voicePressRef.current === press) voicePressRef.current = null;
        return;
      }
      if (voicePressRef.current !== press || press.cancelled) {
        if (recorderRef.current === recorder) cancelRecording();
        else recorder.cancel();
        return;
      }
      if (press.released) finishVoicePress(press);
    })();
  };

  const handleVoicePointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const press = voicePressRef.current;
    if (!press || press.pointerId !== event.pointerId) return;
    event.preventDefault();
    press.released = true;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (recorderRef.current) finishVoicePress(press);
  };

  const handleVoicePointerCancel = (event: React.PointerEvent<HTMLButtonElement>) => {
    const press = voicePressRef.current;
    if (!press || press.pointerId !== event.pointerId) return;
    press.cancelled = true;
    voicePressRef.current = null;
    cancelRecording();
  };

  const switchToTextInput = () => {
    const press = voicePressRef.current;
    if (press) {
      press.cancelled = true;
      voicePressRef.current = null;
      cancelRecording();
    }
    setInputMode('text');
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
        <div className="assistant-composer__row assistant-composer__row--voice">
          <button
            className={`assistant-composer__voice-btn${recording ? ' assistant-composer__voice-btn--recording' : ''}${voiceProcessing ? ' assistant-composer__voice-btn--processing' : ''}`}
            disabled={sending || voiceProcessing}
            onPointerDown={handleVoicePointerDown}
            onPointerUp={handleVoicePointerUp}
            onPointerCancel={handleVoicePointerCancel}
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
              onClick={switchToTextInput}
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
