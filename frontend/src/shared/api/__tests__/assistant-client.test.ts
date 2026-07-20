import { describe, expect, it, vi } from 'vitest';
import { createTodoApi } from '../client';

const connection = { baseUrl: 'http://localhost:8000', token: 'test-token' };

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('assistant api client', () => {
  it('sends a message and unwraps the turn', async () => {
    const turn = {
      message: { id: 'm2', role: 'assistant', content: '好', attachments: [], status: 'done', createdAt: 2 },
      proposals: [],
    };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(turn));
    const api = createTodoApi(connection, fetcher);

    const result = await api.sendAssistantMessage('c1', { content: '你好', attachments: [] });

    expect(result.message.content).toBe('好');
    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/assistant/conversations/c1/messages',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('uploads a file as multipart without a JSON content type', async () => {
    const attachment = { fileId: 'f1.png', kind: 'image', name: 'a.png', mime: 'image/png' };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(attachment, 201));
    const api = createTodoApi(connection, fetcher);
    const file = new File([new Uint8Array([1, 2])], 'a.png', { type: 'image/png' });

    const result = await api.uploadAssistantFile(file);

    expect(result).toEqual(attachment);
    const [, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer test-token');
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('resolves proposals and reads settings', async () => {
    const resolved = {
      proposal: { id: 'p1', messageId: 'm1', action: 'create', taskId: null,
        payload: { text: '买菜' }, status: 'accepted', createdAt: 1 },
      task: { id: 't1', text: '买菜', completed: false, priority: 'medium',
        createdAt: 1, category: 'life' },
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse(resolved))
      .mockResolvedValueOnce(jsonResponse({
        hasApiKey: true, chatModel: 'chat', audioModel: 'audio',
      }));
    const api = createTodoApi(connection, fetcher);

    const accepted = await api.acceptAssistantProposal('p1');
    const settings = await api.getAssistantSettings();

    expect(accepted.proposal.status).toBe('accepted');
    expect(accepted.task?.id).toBe('t1');
    expect(settings.hasApiKey).toBe(true);
  });

  it('returns transcribed text', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ text: '识别结果' }));
    const api = createTodoApi(connection, fetcher);

    await expect(api.transcribeAssistantAudio('f1.wav')).resolves.toBe('识别结果');
  });
});
