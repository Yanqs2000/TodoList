import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTodoApi, REQUEST_TIMEOUT_MS } from '../client';
import {
  InfrastructureError,
  type ProposalBatchResolveResult,
} from '../contracts';

const connection = { baseUrl: 'http://localhost:8000', token: 'test-token' };

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function batchResolveResult(
  status: 'accepted' | 'rejected',
): ProposalBatchResolveResult {
  const proposal = {
    id: 'p1',
    messageId: 'm2',
    batchId: 'b1',
    action: 'create' as const,
    targetTaskId: null,
    beforeSnapshot: null,
    payload: {
      text: '买菜',
      priority: 'medium' as const,
      category: 'life' as const,
      time_start: null,
      time_end: null,
      notes: null,
    },
    resultTaskId: status === 'accepted' ? 't1' : null,
    status,
    lastError: null,
    createdAt: 3,
  };
  return {
    batch: {
      id: 'b1',
      messageId: 'm2',
      status,
      supersedesBatchId: null,
      proposals: [proposal],
      createdAt: 3,
      resolvedAt: 4,
    },
    items: [{ proposal, task: null, error: null }],
  };
}

describe('assistant api client', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends the stable turn id with the message', async () => {
    const turn = {
      message: {
        id: 'm2', turnId: 'turn-1', role: 'assistant', content: '好',
        attachments: [], status: 'done', createdAt: 2,
      },
      proposalBatches: [],
    };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(turn));
    const api = createTodoApi(connection, fetcher);

    const result = await api.sendAssistantMessage('c1', {
      turnId: 'turn-1', content: '你好', attachments: [],
    });

    expect(result.message.content).toBe('好');
    const [, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      turnId: 'turn-1', content: '你好', attachments: [],
    });
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

  it('confirms an edited proposal batch in one request', async () => {
    const result = batchResolveResult('accepted');
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(result));
    const api = createTodoApi(connection, fetcher);
    const input = { items: [{
      proposalId: 'p1',
      payload: {
        text: '卡片编辑后', priority: 'high' as const, category: 'work' as const,
        time_start: null, time_end: null, notes: null,
      },
    }] };

    await expect(api.confirmAssistantProposalBatch('b1', input)).resolves.toEqual(result);
    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/assistant/proposal-batches/b1/confirm',
      expect.objectContaining({ method: 'POST', body: JSON.stringify(input) }),
    );
  });

  it('rejects a whole batch through the batch route', async () => {
    const result = batchResolveResult('rejected');
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(result));
    const api = createTodoApi(connection, fetcher);

    await api.rejectAssistantProposalBatch('b1');
    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/assistant/proposal-batches/b1/reject',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('reads assistant settings', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      hasApiKey: true, chatModel: 'chat', audioModel: 'audio',
    }));
    const api = createTodoApi(connection, fetcher);

    const settings = await api.getAssistantSettings();

    expect(settings.hasApiKey).toBe(true);
  });

  it('returns transcribed text', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ text: '识别结果' }));
    const api = createTodoApi(connection, fetcher);

    await expect(api.transcribeAssistantAudio('f1.wav')).resolves.toBe('识别结果');
  });

  it('uses an extended timeout for sendAssistantMessage', async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | null | undefined;
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) => {
      signal = init?.signal;
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      });
    });
    const api = createTodoApi(connection, fetcher);

    const request = api.sendAssistantMessage('c1', {
      turnId: 'turn-timeout', content: '你好', attachments: [],
    });
    const assertion = expect(request).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'timeout',
      code: 'REQUEST_TIMEOUT',
    });

    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 1);
    expect(signal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(120_000);
    await assertion;
  });

  it('classifies fetch rejection as a network failure for uploads', async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(
      new TypeError('private network adapter detail'),
    );
    const api = createTodoApi(connection, fetcher);
    const file = new File([new Uint8Array([1, 2])], 'a.png', { type: 'image/png' });

    await expect(api.uploadAssistantFile(file)).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'network',
      code: 'NETWORK_ERROR',
      message: 'Network request failed',
    });
    await expect(api.uploadAssistantFile(file)).rejects.toBeInstanceOf(InfrastructureError);
  });
});
