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


class AssistantSettings(WireModel):
    api_key: str
    chat_model: str
    audio_model: str


class AssistantSettingsView(WireModel):
    has_api_key: bool = Field(alias="hasApiKey")
    chat_model: str = Field(alias="chatModel")
    audio_model: str = Field(alias="audioModel")


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
ProposalStatus = Literal["pending", "accepted", "rejected"]


class AssistantAttachment(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )
    kind: AttachmentKind
    name: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    mime: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    extracted_text: str | None = Field(default=None, alias="extractedText")


class ProposalFields(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    category: Category | None = None
    time_start: LocalDateTime | None = None
    time_end: LocalDateTime | None = None
    notes: StrictNotes | None = None


class AssistantMessage(WireModel):
    id: str
    role: AssistantRole
    content: str
    attachments: list[AssistantAttachment] = []
    status: AssistantMessageStatus = "done"
    created_at: int = Field(alias="createdAt")


class AssistantProposal(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    action: ProposalAction
    task_id: str | None = Field(default=None, alias="taskId")
    payload: ProposalFields
    status: ProposalStatus
    created_at: int = Field(alias="createdAt")


class AssistantConversationSummary(WireModel):
    id: str
    title: str
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class SendAssistantMessageCommand(WireModel):
    content: Annotated[str, Field(strict=True, max_length=10_000)] = ""
    attachments: list[AssistantAttachment] = Field(
        default_factory=list[AssistantAttachment], max_length=5
    )

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "SendAssistantMessageCommand":
        if not self.content.strip() and not self.attachments:
            raise ValueError("message requires content or attachments")
        return self


class TranscribeCommand(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )


class AssistantTurnResponse(WireModel):
    message: AssistantMessage
    proposals: list[AssistantProposal]


class AssistantConversationDetail(WireModel):
    conversation: AssistantConversationSummary
    messages: list[AssistantMessage]
    proposals: list[AssistantProposal]


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
