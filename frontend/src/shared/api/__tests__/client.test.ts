import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  InfrastructureError,
  type BootstrapSnapshot,
} from '../contracts';
import { createTodoApi, REQUEST_TIMEOUT_MS } from '../client';

const EMPTY_SNAPSHOT: BootstrapSnapshot = {
  tasks: [],
  settings: {
    theme: 'workspace-dark',
    muted: false,
    shortcut: 'Cmd+Alt+KeyT',
  },
  achievementState: {
    unlocked: [],
    streakDays: 0,
    lastActiveDate: '',
    todayCompleted: 0,
    todayDate: '',
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('createTodoApi', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('injects Bearer and JSON headers and sends the preferred system theme', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(EMPTY_SNAPSHOT));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    await expect(api.bootstrap('workspace-dark')).resolves.toEqual(EMPTY_SNAPSHOT);

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(
      'http://127.0.0.1:43123/api/v1/bootstrap',
      expect.objectContaining({
        method: 'POST',
        headers: {
          Authorization: 'Bearer run-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ preferredTheme: 'workspace-dark' }),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it('parses stable business errors without exposing response internals', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      error: { code: 'TASK_NOT_FOUND', message: 'Task not found' },
    }, 404));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    const request = api.updateTask('missing', { text: 'new text' });

    await expect(request).rejects.toMatchObject({
      name: 'ApiError',
      kind: 'business',
      code: 'TASK_NOT_FOUND',
      message: 'Task not found',
      status: 404,
    });
    await expect(request).rejects.toBeInstanceOf(ApiError);
  });

  it('classifies stable backend service errors as infrastructure failures', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      error: { code: 'DATABASE_UNAVAILABLE', message: 'Database unavailable' },
    }, 503));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    const request = api.bootstrap('workspace-light');

    await expect(request).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'infrastructure',
      code: 'DATABASE_UNAVAILABLE',
      status: 503,
    });
    await expect(request).rejects.toBeInstanceOf(InfrastructureError);
  });

  it('classifies a request aborted at ten seconds as a timeout', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation((_input, init) => (
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      })
    ));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    const request = api.bootstrap('workspace-light');
    const assertion = expect(request).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'timeout',
      code: 'REQUEST_TIMEOUT',
    });
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);

    await assertion;
  });

  it('classifies fetch rejection as a sanitized network failure', async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(
      new TypeError('private network adapter detail'),
    );
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    await expect(api.bootstrap('workspace-light')).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'network',
      code: 'NETWORK_ERROR',
      message: 'Network request failed',
    });
  });

  it('classifies malformed successful JSON as a sanitized protocol failure', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      'private malformed response body',
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    await expect(api.bootstrap('workspace-light')).rejects.toMatchObject({
      name: 'InfrastructureError',
      kind: 'infrastructure',
      code: 'INVALID_RESPONSE',
      message: 'Invalid backend response',
      status: 200,
    });
  });

  it('clears the ten-second timeout after a completed request', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(EMPTY_SNAPSHOT));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    await api.bootstrap('workspace-light');

    expect(vi.getTimerCount()).toBe(0);
  });

  it('still times out when a successful response body resolves after the deadline', async () => {
    vi.useFakeTimers();
    const response = jsonResponse(EMPTY_SNAPSHOT);
    vi.spyOn(response, 'json').mockImplementation(() => new Promise(resolve => {
      setTimeout(() => resolve(EMPTY_SNAPSHOT), REQUEST_TIMEOUT_MS + 1);
    }));
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response);
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    const request = api.bootstrap('workspace-light');
    const assertion = expect(request).rejects.toMatchObject({
      kind: 'timeout',
      code: 'REQUEST_TIMEOUT',
    });
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 1);

    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  });

  it('maps the remaining typed operations to their backend routes', async () => {
    const task = {
      id: 'task/1',
      text: 'task',
      completed: false,
      priority: 'medium' as const,
      createdAt: 1,
      category: 'other' as const,
    };
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ task }))
      .mockResolvedValueOnce(jsonResponse({ task: { ...task, text: 'edited' } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ tasks: [task] }))
      .mockResolvedValueOnce(jsonResponse({
        task: { ...task, completed: true },
        achievementState: EMPTY_SNAPSHOT.achievementState,
        newlyUnlocked: [],
      }))
      .mockResolvedValueOnce(jsonResponse({ claimed: true }))
      .mockResolvedValueOnce(jsonResponse({ settings: EMPTY_SNAPSHOT.settings }));
    const api = createTodoApi({ baseUrl: 'http://127.0.0.1:43123', token: 'run-token' }, fetcher);

    await expect(api.createTask({ text: 'task', priority: 'medium' })).resolves.toEqual(task);
    await expect(api.updateTask('task/1', { text: 'edited' })).resolves.toMatchObject({ text: 'edited' });
    await expect(api.deleteTask('task/1')).resolves.toBeUndefined();
    await expect(api.replaceTaskOrder(['task/1'])).resolves.toEqual([task]);
    await expect(api.setTaskCompletion('task/1', {
      completed: true,
      localDate: '2026-07-13',
    })).resolves.toMatchObject({ task: { completed: true } });
    await expect(api.claimReminder({
      taskId: 'task/1',
      scheduledStart: '2026-07-13T09:00',
    })).resolves.toBe(true);
    await expect(api.updateSettings({ muted: true })).resolves.toEqual(EMPTY_SNAPSHOT.settings);

    expect(fetcher.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['http://127.0.0.1:43123/api/v1/tasks', 'POST'],
      ['http://127.0.0.1:43123/api/v1/tasks/task%2F1', 'PATCH'],
      ['http://127.0.0.1:43123/api/v1/tasks/task%2F1', 'DELETE'],
      ['http://127.0.0.1:43123/api/v1/tasks/order', 'PUT'],
      ['http://127.0.0.1:43123/api/v1/tasks/task%2F1/completion', 'PUT'],
      ['http://127.0.0.1:43123/api/v1/reminders/claim', 'POST'],
      ['http://127.0.0.1:43123/api/v1/settings', 'PATCH'],
    ]);
  });
});
