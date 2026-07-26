import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


StrictText = Annotated[str, Field(strict=True, min_length=1, max_length=10_000)]
StrictNotes = Annotated[str, Field(strict=True, max_length=10_000)]
Priority = Literal["low", "medium", "high"]
Category = Literal["work", "study", "life", "other"]
ThemeId = Literal[
    "workspace-light",
    "mint-light",
    "paper-light",
    "workspace-dark",
    "mint-dark",
    "paper-dark",
]
Language = Literal["zh-CN", "en"]
LocalDate = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]


def validate_local_datetime(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("time must be a valid local ISO minute datetime") from None
    return value


LocalDateTime = Annotated[
    str,
    Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"),
    AfterValidator(validate_local_datetime),
]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class TimeField(WireModel):
    start: LocalDateTime
    end: LocalDateTime | None = None


class Task(WireModel):
    id: str
    text: StrictText
    completed: bool
    priority: Priority
    created_at: int = Field(alias="createdAt")
    time: TimeField | None = None
    category: Category
    notes: StrictNotes | None = None


class CreateTaskCommand(WireModel):
    text: StrictText
    priority: Priority
    time: TimeField | None = None
    category: Category = "other"
    notes: StrictNotes | None = None


class UpdateTaskCommand(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    time: TimeField | None = None
    category: Category | None = None
    notes: StrictNotes | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "UpdateTaskCommand":
        for field_name in ("text", "priority", "category"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ReplaceTaskOrderCommand(WireModel):
    task_ids: list[str] = Field(alias="taskIds")


class CompletionCommand(WireModel):
    completed: bool
    local_date: LocalDate = Field(alias="localDate")

    @field_validator("local_date")
    @classmethod
    def validate_local_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("localDate must be a valid ISO date") from None
        return value


class BootstrapCommand(WireModel):
    preferred_theme: ThemeId = Field(default="workspace-light", alias="preferredTheme")


class AppSettings(WireModel):
    theme: ThemeId
    muted: bool
    shortcut: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    language: Language


class SettingsPatchCommand(WireModel):
    theme: ThemeId | None = None
    muted: bool | None = None
    shortcut: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None
    language: Language | None = None

    @field_validator("shortcut")
    @classmethod
    def validate_shortcut(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = value.split("+")
        modifiers = {"Cmd", "CmdOrCtrl", "Ctrl", "Alt", "Shift", "Super", "Meta"}
        if (
            len(parts) < 2
            or any(part not in modifiers for part in parts[:-1])
            or len(set(parts[:-1])) != len(parts[:-1])
            or parts[-1] in modifiers
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", parts[-1]) is None
        ):
            raise ValueError("shortcut must contain a modifier and key")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null_patch(self) -> "SettingsPatchCommand":
        if not self.model_fields_set:
            raise ValueError("settings patch cannot be empty")
        if any(getattr(self, field_name) is None for field_name in self.model_fields_set):
            raise ValueError("settings fields cannot be null")
        return self


class ReminderClaimCommand(WireModel):
    task_id: StrictText = Field(alias="taskId")
    scheduled_start: LocalDateTime = Field(alias="scheduledStart")


class TaskResponse(WireModel):
    task: Task


class TaskListResponse(WireModel):
    tasks: list[Task]


class BootstrapResponse(WireModel):
    tasks: list[Task]
    settings: AppSettings
    achievement_state: "AchievementState" = Field(alias="achievementState")


class SettingsResponse(WireModel):
    settings: AppSettings


class ReminderClaimResponse(WireModel):
    claimed: bool


class AchievementState(WireModel):
    unlocked: list[str]
    streak_days: int = Field(alias="streakDays")
    last_active_date: str = Field(alias="lastActiveDate")
    today_completed: int = Field(alias="todayCompleted")
    today_date: str = Field(alias="todayDate")


class CompletionResponse(WireModel):
    task: Task
    achievement_state: AchievementState = Field(alias="achievementState")
    newly_unlocked: list[str] = Field(alias="newlyUnlocked")


DEFAULT_CHAT_MODEL = "doubao-seed-2-1-pro-260628"
DEFAULT_AUDIO_MODEL = "doubao-seed-2-0-lite-260428"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


VoiceMode = Literal["direct", "transcribe"]


class AssistantSettings(WireModel):
    api_key: str
    chat_model: str
    audio_model: str
    base_url: str
    voice_mode: VoiceMode


class AssistantSettingsView(WireModel):
    has_api_key: bool = Field(alias="hasApiKey")
    chat_model: str = Field(alias="chatModel")
    audio_model: str = Field(alias="audioModel")
    base_url: str = Field(alias="baseUrl")
    voice_mode: VoiceMode = Field(alias="voiceMode")


class AssistantSettingsPatchCommand(WireModel):
    api_key: Annotated[str, Field(strict=True, max_length=200)] | None = Field(
        default=None, alias="apiKey"
    )
    chat_model: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = Field(
        default=None, alias="chatModel"
    )
    audio_model: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = Field(
        default=None, alias="audioModel"
    )
    base_url: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = Field(
        default=None, alias="baseUrl"
    )
    voice_mode: VoiceMode | None = Field(default=None, alias="voiceMode")

    @model_validator(mode="after")
    def reject_empty_or_null_patch(self) -> "AssistantSettingsPatchCommand":
        if not self.model_fields_set:
            raise ValueError("settings patch cannot be empty")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("settings fields cannot be null")
        return self


AssistantRole = Literal["user", "assistant"]
AssistantMessageStatus = Literal["pending", "done", "failed"]
AttachmentKind = Literal["image", "document", "audio"]
ProposalAction = Literal["create", "update", "delete"]
ProposalStatus = Literal["pending", "accepted", "rejected", "superseded"]
ProposalBatchStatus = Literal[
    "pending", "partially_applied", "accepted", "rejected", "superseded"
]
AssistantTurnStatus = Literal["active", "done", "failed"]


class AssistantAttachment(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )
    kind: AttachmentKind
    name: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    mime: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    extracted_text: str | None = Field(default=None, alias="extractedText")


class PlannedFields(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    category: Category | None = None
    time_start: LocalDateTime | None = None
    time_end: LocalDateTime | None = None
    notes: StrictNotes | None = None

    @field_validator("notes")
    @classmethod
    def normalize_blank_notes(cls, value: str | None) -> str | None:
        # "Clear notes" arrives as an empty or whitespace-only string; the wire
        # contract represents absent notes as null.
        if value is not None and not value.strip():
            return None
        return value


class ProposalCardFields(WireModel):
    text: StrictText
    priority: Priority
    category: Category
    time_start: LocalDateTime | None
    time_end: LocalDateTime | None
    notes: StrictNotes | None


# Temporary source-compatibility alias for the old AgentTools removed in Task 11.
ProposalFields = PlannedFields


class AssistantMessage(WireModel):
    id: str
    role: AssistantRole
    content: str
    attachments: list[AssistantAttachment] = []
    status: AssistantMessageStatus = "done"
    created_at: int = Field(alias="createdAt")
    turn_id: str | None = Field(default=None, alias="turnId")


class AssistantTurnRecord(WireModel):
    id: str
    conversation_id: str = Field(alias="conversationId")
    user_message_id: str = Field(alias="userMessageId")
    assistant_message_id: str = Field(alias="assistantMessageId")
    request_fingerprint: str = Field(alias="requestFingerprint")
    status: AssistantTurnStatus
    last_error: str | None = Field(default=None, alias="lastError")


class AssistantProposal(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    batch_id: str = Field(alias="batchId")
    action: ProposalAction
    target_task_id: str | None = Field(default=None, alias="targetTaskId")
    before_snapshot: Task | None = Field(default=None, alias="beforeSnapshot")
    payload: ProposalCardFields | None
    result_task_id: str | None = Field(default=None, alias="resultTaskId")
    status: ProposalStatus
    last_error: str | None = Field(default=None, alias="lastError")
    created_at: int = Field(alias="createdAt")


class AssistantProposalBatch(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    status: ProposalBatchStatus
    supersedes_batch_id: str | None = Field(default=None, alias="supersedesBatchId")
    proposals: list[AssistantProposal]
    created_at: int = Field(alias="createdAt")
    resolved_at: int | None = Field(default=None, alias="resolvedAt")


class AssistantConversationSummary(WireModel):
    id: str
    title: str
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class SendAssistantMessageCommand(WireModel):
    turn_id: Annotated[str, Field(strict=True, min_length=8, max_length=100)] = Field(
        alias="turnId"
    )
    content: Annotated[str, Field(strict=True, max_length=10_000)] = ""
    attachments: list[AssistantAttachment] = Field(
        default_factory=list[AssistantAttachment], max_length=5
    )

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "SendAssistantMessageCommand":
        if not self.content.strip() and not self.attachments:
            raise ValueError("message requires content or attachments")
        return self


class ConfirmProposalItem(WireModel):
    proposal_id: str = Field(alias="proposalId")
    payload: ProposalCardFields | None = None


class ConfirmProposalBatchCommand(WireModel):
    items: Annotated[list[ConfirmProposalItem], Field(min_length=1)]


class ProposalReviewDecision(WireModel):
    decision: Literal["confirm", "reject"]
    items: list[ConfirmProposalItem] = Field(default_factory=list[ConfirmProposalItem])


class ProposalApplyItemResult(WireModel):
    proposal: AssistantProposal
    task: Task | None = None
    error: str | None = None


class ProposalBatchResolveResponse(WireModel):
    batch: AssistantProposalBatch
    items: list[ProposalApplyItemResult]


class TranscribeCommand(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )


class AssistantTurnResponse(WireModel):
    message: AssistantMessage
    proposal_batches: list[AssistantProposalBatch] = Field(alias="proposalBatches")


class AssistantConversationDetail(WireModel):
    conversation: AssistantConversationSummary
    messages: list[AssistantMessage]
    proposal_batches: list[AssistantProposalBatch] = Field(alias="proposalBatches")


class AssistantConversationListResponse(WireModel):
    conversations: list[AssistantConversationSummary]


class AssistantProposalResolveResponse(WireModel):
    proposal: AssistantProposal
    task: Task | None = None


class UploadResponse(WireModel):
    file_id: str = Field(alias="fileId")
    kind: AttachmentKind
    name: str
    mime: str


class TranscribeResponse(WireModel):
    text: str
