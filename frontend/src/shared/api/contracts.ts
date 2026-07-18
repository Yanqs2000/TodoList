import type {
  AchievementState,
  Category,
  Priority,
  TimeField,
  Todo,
} from '@/shared/types';
import type { Language } from '@/features/i18n/translations';

export type ThemeId =
  | 'workspace-light'
  | 'mint-light'
  | 'paper-light'
  | 'workspace-dark'
  | 'mint-dark'
  | 'paper-dark';

export type SystemTheme = 'workspace-light' | 'workspace-dark';

export interface BackendConnection {
  baseUrl: string;
  token: string;
}

export interface AppSettings {
  theme: ThemeId;
  muted: boolean;
  shortcut: string;
  language: Language;
}

export interface BootstrapSnapshot {
  tasks: Todo[];
  settings: AppSettings;
  achievementState: AchievementState;
}

export interface CreateTaskInput {
  text: string;
  priority: Priority;
  time?: TimeField;
  category?: Category;
  notes?: string;
}

export interface UpdateTaskInput {
  text?: string;
  priority?: Priority;
  time?: TimeField | null;
  category?: Category;
  notes?: string | null;
}

export interface CompletionInput {
  completed: boolean;
  localDate: string;
}

export interface CompletionResult {
  task: Todo;
  achievementState: AchievementState;
  newlyUnlocked: string[];
}

export interface ReminderClaimInput {
  taskId: string;
  scheduledStart: string;
}

export interface SettingsPatch {
  theme?: ThemeId;
  muted?: boolean;
  shortcut?: string;
  language?: Language;
}

export interface TodoApi {
  bootstrap(preferredTheme: SystemTheme): Promise<BootstrapSnapshot>;
  createTask(input: CreateTaskInput): Promise<Todo>;
  updateTask(taskId: string, input: UpdateTaskInput): Promise<Todo>;
  deleteTask(taskId: string): Promise<void>;
  replaceTaskOrder(taskIds: string[]): Promise<Todo[]>;
  setTaskCompletion(taskId: string, input: CompletionInput): Promise<CompletionResult>;
  claimReminder(input: ReminderClaimInput): Promise<boolean>;
  updateSettings(input: SettingsPatch): Promise<AppSettings>;
}

export type ApiErrorKind = 'business' | 'infrastructure' | 'timeout' | 'network';

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly code: string,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class InfrastructureError extends ApiError {
  constructor(
    kind: Exclude<ApiErrorKind, 'business'>,
    code: string,
    message: string,
    status?: number,
  ) {
    super(kind, code, message, status);
    this.name = 'InfrastructureError';
  }
}
