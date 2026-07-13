import {
  ApiError,
  InfrastructureError,
  type AppSettings,
  type BackendConnection,
  type BootstrapSnapshot,
  type CompletionResult,
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
  if (response.status >= 500 || INFRASTRUCTURE_CODES.has(code)) {
    return new InfrastructureError('infrastructure', code, message, response.status);
  }
  return new ApiError('business', code, message, response.status);
}

function encodedTaskPath(taskId: string): string {
  return `/api/v1/tasks/${encodeURIComponent(taskId)}`;
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
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetcher(`${baseUrl}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${connection.token}`,
          'Content-Type': 'application/json',
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) throw await responseError(response);
      if (response.status === 204) return undefined as T;
      return await response.json() as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted) {
        throw new InfrastructureError(
          'timeout',
          'REQUEST_TIMEOUT',
          'Request timed out',
        );
      }
      throw new InfrastructureError(
        'network',
        'NETWORK_ERROR',
        'Network request failed',
      );
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
  };
}
