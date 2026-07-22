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

export type AssistantAttachmentKind = 'image' | 'document' | 'audio';

export interface AssistantAttachment {
  fileId: string;
  kind: AssistantAttachmentKind;
  name: string;
  mime: string;
  extractedText?: string | null;
}

export interface AssistantConversationSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export interface AssistantMessage {
  id: string;
  turnId: string | null;
  role: 'user' | 'assistant';
  content: string;
  attachments: AssistantAttachment[];
  status: 'pending' | 'done' | 'failed';
  createdAt: number;
}

export interface ProposalCardFields {
  text: string;
  priority: Priority;
  category: Category;
  time_start: string | null;
  time_end: string | null;
  notes: string | null;
}

export type ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'superseded';
export type ProposalBatchStatus =
  | 'pending' | 'partially_applied' | 'accepted' | 'rejected' | 'superseded';

export interface AssistantProposal {
  id: string;
  messageId: string;
  batchId: string;
  action: 'create' | 'update' | 'delete';
  targetTaskId: string | null;
  beforeSnapshot: Todo | null;
  payload: ProposalCardFields | null;
  resultTaskId: string | null;
  status: ProposalStatus;
  lastError: string | null;
  createdAt: number;
}

export interface AssistantProposalBatch {
  id: string;
  messageId: string;
  status: ProposalBatchStatus;
  supersedesBatchId: string | null;
  proposals: AssistantProposal[];
  createdAt: number;
  resolvedAt: number | null;
}

export interface ConfirmProposalItemInput {
  proposalId: string;
  payload: ProposalCardFields | null;
}

export interface ConfirmProposalBatchInput {
  items: ConfirmProposalItemInput[];
}

export interface ProposalApplyItemResult {
  proposal: AssistantProposal;
  task: Todo | null;
  error: string | null;
}

export interface ProposalBatchResolveResult {
  batch: AssistantProposalBatch;
  items: ProposalApplyItemResult[];
}

export interface AssistantTurn {
  message: AssistantMessage;
  proposalBatches: AssistantProposalBatch[];
}

export interface AssistantConversationDetail {
  conversation: AssistantConversationSummary;
  messages: AssistantMessage[];
  proposalBatches: AssistantProposalBatch[];
}

export interface AssistantSettingsView {
  hasApiKey: boolean;
  chatModel: string;
  audioModel: string;
  baseUrl: string;
}

export interface AssistantSettingsPatch {
  apiKey?: string;
  chatModel?: string;
  audioModel?: string;
  baseUrl?: string;
}

export interface SendAssistantMessageInput {
  turnId: string;
  content: string;
  attachments: AssistantAttachment[];
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
  listAssistantConversations(): Promise<AssistantConversationSummary[]>;
  createAssistantConversation(): Promise<AssistantConversationSummary>;
  getAssistantConversation(id: string): Promise<AssistantConversationDetail>;
  deleteAssistantConversation(id: string): Promise<void>;
  sendAssistantMessage(id: string, input: SendAssistantMessageInput): Promise<AssistantTurn>;
  uploadAssistantFile(file: File): Promise<AssistantAttachment>;
  transcribeAssistantAudio(fileId: string): Promise<string>;
  confirmAssistantProposalBatch(
    id: string,
    input: ConfirmProposalBatchInput,
  ): Promise<ProposalBatchResolveResult>;
  rejectAssistantProposalBatch(id: string): Promise<ProposalBatchResolveResult>;
  getAssistantSettings(): Promise<AssistantSettingsView>;
  updateAssistantSettings(input: AssistantSettingsPatch): Promise<AssistantSettingsView>;
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
