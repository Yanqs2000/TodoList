import {
  ApiError,
  InfrastructureError,
  type AppSettings,
  type AssistantAttachment,
  type AssistantConversationDetail,
  type AssistantConversationSummary,
  type AssistantSettingsView,
  type AssistantTurn,
  type BackendConnection,
  type BootstrapSnapshot,
  type CompletionResult,
  type ProposalBatchResolveResult,
  type TodoApi,
} from './contracts';
import type { Todo } from '@/shared/types';

export const REQUEST_TIMEOUT_MS = 10_000;

interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
  };
}

interface TaskEnvelope {
  task: Todo;
}

interface TasksEnvelope {
  tasks: Todo[];
}

interface ClaimedEnvelope {
  claimed: boolean;
}

interface SettingsEnvelope {
  settings: AppSettings;
}

const INFRASTRUCTURE_CODES = new Set([
  'DATABASE_UNAVAILABLE',
  'INTERNAL_ERROR',
  'UNAUTHORIZED',
]);

const FEATURE_SERVICE_CODES = new Set([
  'ASSISTANT_UNAVAILABLE',
]);

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const error = value.error;
  return typeof error === 'object'
    && error !== null
    && 'code' in error
    && typeof error.code === 'string'
    && 'message' in error
    && typeof error.message === 'string';
}

async function responseError(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const code = isErrorEnvelope(payload) ? payload.error.code : 'REQUEST_FAILED';
  const message = isErrorEnvelope(payload) ? payload.error.message : 'Request failed';
  if (
    !FEATURE_SERVICE_CODES.has(code)
    && (response.status >= 500 || INFRASTRUCTURE_CODES.has(code))
  ) {
    return new InfrastructureError('infrastructure', code, message, response.status);
  }
  return new ApiError('business', code, message, response.status);
}

function encodedTaskPath(taskId: string): string {
  return `/api/v1/tasks/${encodeURIComponent(taskId)}`;
}

function timeoutError(): InfrastructureError {
  return new InfrastructureError(
    'timeout',
    'REQUEST_TIMEOUT',
    'Request timed out',
  );
}

export function createTodoApi(
  connection: BackendConnection,
  fetcher: typeof fetch = fetch,
): TodoApi {
  const baseUrl = connection.baseUrl.replace(/\/$/, '');

  async function request<T>(
    path: string,
    method: string,
    body?: unknown,
    timeoutMs: number = REQUEST_TIMEOUT_MS,
    rawBody?: BodyInit,
    headers?: Record<string, string>,
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const requestHeaders: Record<string, string> = {
        Authorization: `Bearer ${connection.token}`,
        ...(headers ?? {}),
      };
      if (rawBody === undefined) {
        requestHeaders['Content-Type'] = 'application/json';
      }
      let response: Response;
      try {
        response = await fetcher(`${baseUrl}${path}`, {
          method,
          headers: requestHeaders,
          body: rawBody !== undefined
            ? rawBody
            : body === undefined
              ? undefined
              : JSON.stringify(body),
          signal: controller.signal,
        });
      } catch {
        if (controller.signal.aborted) throw timeoutError();
        throw new InfrastructureError(
          'network',
          'NETWORK_ERROR',
          'Network request failed',
        );
      }
      if (!response.ok) {
        const error = await responseError(response);
        if (controller.signal.aborted) throw timeoutError();
        throw error;
      }
      if (controller.signal.aborted) throw timeoutError();
      if (response.status === 204) return undefined as T;
      let payload: T;
      try {
        payload = await response.json() as T;
      } catch {
        if (controller.signal.aborted) throw timeoutError();
        throw new InfrastructureError(
          'infrastructure',
          'INVALID_RESPONSE',
          'Invalid backend response',
          response.status,
        );
      }
      if (controller.signal.aborted) throw timeoutError();
      return payload;
    } finally {
      clearTimeout(timeout);
    }
  }

  return {
    bootstrap: preferredTheme => request<BootstrapSnapshot>(
      '/api/v1/bootstrap',
      'POST',
      { preferredTheme },
    ),
    createTask: async input => (
      await request<TaskEnvelope>('/api/v1/tasks', 'POST', input)
    ).task,
    updateTask: async (taskId, input) => (
      await request<TaskEnvelope>(encodedTaskPath(taskId), 'PATCH', input)
    ).task,
    deleteTask: taskId => request<void>(encodedTaskPath(taskId), 'DELETE'),
    replaceTaskOrder: async taskIds => (
      await request<TasksEnvelope>('/api/v1/tasks/order', 'PUT', { taskIds })
    ).tasks,
    setTaskCompletion: (taskId, input) => request<CompletionResult>(
      `${encodedTaskPath(taskId)}/completion`,
      'PUT',
      input,
    ),
    claimReminder: async input => (
      await request<ClaimedEnvelope>('/api/v1/reminders/claim', 'POST', input)
    ).claimed,
    updateSettings: async input => (
      await request<SettingsEnvelope>('/api/v1/settings', 'PATCH', input)
    ).settings,
    listAssistantConversations: async () => (
      await request<{ conversations: AssistantConversationSummary[] }>(
        '/api/v1/assistant/conversations', 'GET',
      )
    ).conversations,
    createAssistantConversation: () => request<AssistantConversationSummary>(
      '/api/v1/assistant/conversations', 'POST', {},
    ),
    getAssistantConversation: id => request<AssistantConversationDetail>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}`, 'GET',
    ),
    deleteAssistantConversation: id => request<void>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}`, 'DELETE',
    ),
    sendAssistantMessage: (id, input) => request<AssistantTurn>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}/messages`, 'POST', input, 120_000,
    ),
    sendAssistantMessageStream: async (id, input, onEvent, onError, onDone, signal) => {
      const controller = new AbortController();
      if (signal) signal.addEventListener('abort', () => controller.abort());
      try {
        const response = await fetcher(
          `${baseUrl}/api/v1/assistant/conversations/${encodeURIComponent(id)}/messages/stream`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${connection.token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(input),
            signal: controller.signal,
          },
        );
        if (!response.ok) {
          throw await responseError(response);
        }
        const reader = response.body?.getReader();
        if (!reader) { onDone(); return; }
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';
          for (const part of parts) {
            const lines = part.split('\n');
            let eventType = '';
            let eventData = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) eventType = line.slice(7);
              else if (line.startsWith('data: ')) eventData = line.slice(6);
            }
            if (eventType && eventData) {
              try {
                onEvent(eventType, JSON.parse(eventData));
              } catch { /* skip malformed */ }
              if (eventType === 'done' || eventType === 'error') {
                onDone();
                return;
              }
            }
          }
        }
        onDone();
      } catch (e: unknown) {
        if (!controller.signal.aborted) onError(e);
        onDone();
      }
    },
    uploadAssistantFile: async file => {
      const form = new FormData();
      form.append('file', file, file.name);
      return request<AssistantAttachment>(
        '/api/v1/assistant/uploads', 'POST', undefined, 60_000, form,
      );
    },
    transcribeAssistantAudio: async fileId => (
      await request<{ text: string }>('/api/v1/assistant/transcribe', 'POST', { fileId })
    ).text,
    confirmAssistantProposalBatch: (id, input) => request<ProposalBatchResolveResult>(
      `/api/v1/assistant/proposal-batches/${encodeURIComponent(id)}/confirm`,
      'POST',
      input,
    ),
    rejectAssistantProposalBatch: id => request<ProposalBatchResolveResult>(
      `/api/v1/assistant/proposal-batches/${encodeURIComponent(id)}/reject`,
      'POST',
      {},
    ),
    getAssistantSettings: () => request<AssistantSettingsView>(
      '/api/v1/assistant/settings', 'GET',
    ),
    updateAssistantSettings: input => request<AssistantSettingsView>(
      '/api/v1/assistant/settings', 'PUT', input,
    ),
  };
}
