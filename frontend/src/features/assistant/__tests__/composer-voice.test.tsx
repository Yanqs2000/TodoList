import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import type { AssistantAttachment } from '@/shared/api/contracts';
import Composer from '../components/Composer';

const recorder = vi.hoisted(() => ({
  start: vi.fn<() => Promise<void>>(),
  stop: vi.fn<() => Promise<Blob>>(),
  cancel: vi.fn(),
}));

vi.mock('../recorder/wav', () => ({
  WavRecorder: vi.fn(function MockWavRecorder() {
    return recorder;
  }),
}));

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>(next => {
    resolve = next;
  });
  return { promise, resolve };
}

function renderComposer(
  overrides: Partial<React.ComponentProps<typeof Composer>> = {},
  openVoiceMode = true,
) {
  const attachment: AssistantAttachment = {
    fileId: 'voice-1',
    kind: 'audio',
    name: 'voice.wav',
    mime: 'audio/wav',
  };
  const props: React.ComponentProps<typeof Composer> = {
    sending: false,
    voiceMode: 'direct',
    onSend: vi.fn().mockResolvedValue(undefined),
    onError: vi.fn(),
    uploadFile: vi.fn().mockResolvedValue(attachment),
    transcribe: vi.fn().mockResolvedValue('转写结果'),
    ...overrides,
  };

  render(
    <I18nProvider language="zh-CN">
      <Composer {...props} />
    </I18nProvider>,
  );
  if (openVoiceMode) fireEvent.click(screen.getByRole('button', { name: '语音' }));
  return props;
}

describe('Composer voice input', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    recorder.start.mockResolvedValue(undefined);
    recorder.stop.mockResolvedValue(new Blob(['wav'], { type: 'audio/wav' }));
  });

  it('uses one voice entry and keeps attachment input in text mode only', () => {
    renderComposer({}, false);

    expect(screen.getByRole('button', { name: '添加附件' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '语音' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '开始录音' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '语音' }));

    expect(screen.queryByRole('button', { name: '添加附件' })).toBeNull();
    expect(screen.getByRole('button', { name: '文字' })).toBeTruthy();
  });

  it('finishes a press released while microphone startup is still pending', async () => {
    const startup = deferred<void>();
    recorder.start.mockReturnValueOnce(startup.promise);
    const props = renderComposer();
    const button = screen.getByRole('button', { name: '按住 录音' });

    fireEvent.pointerDown(button, { pointerId: 7, pointerType: 'mouse', button: 0 });
    fireEvent.pointerUp(button, { pointerId: 7, pointerType: 'mouse', button: 0 });

    await act(async () => {
      startup.resolve();
      await startup.promise;
    });

    await waitFor(() => expect(recorder.stop).toHaveBeenCalledTimes(1));
    expect(props.uploadFile).toHaveBeenCalledTimes(1);
    expect(props.onSend).toHaveBeenCalledWith('', [
      expect.objectContaining({ fileId: 'voice-1' }),
    ]);
  });

  it('cancels a pending recording when the pointer gesture is cancelled', async () => {
    const startup = deferred<void>();
    recorder.start.mockReturnValueOnce(startup.promise);
    const props = renderComposer();
    const button = screen.getByRole('button', { name: '按住 录音' });

    fireEvent.pointerDown(button, { pointerId: 8, pointerType: 'touch', button: 0 });
    fireEvent.pointerCancel(button, { pointerId: 8, pointerType: 'touch' });

    await act(async () => {
      startup.resolve();
      await startup.promise;
    });

    await waitFor(() => expect(recorder.cancel).toHaveBeenCalledTimes(1));
    expect(props.uploadFile).not.toHaveBeenCalled();
    expect(props.onSend).not.toHaveBeenCalled();
  });
});
