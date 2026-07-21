import base64
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError
from todo_backend.agent.orchestrator import HISTORY_LIMIT, AgentOrchestrator, AgentTurn
from todo_backend.agent.tools import AgentTools
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantAttachment,
    AssistantConversationDetail,
    AssistantConversationSummary,
    AssistantMessage,
    AssistantProposal,
    AssistantSettings,
    AssistantSettingsPatchCommand,
    AssistantSettingsView,
    AssistantTurnResponse,
    AttachmentKind,
    CreateTaskCommand,
    SendAssistantMessageCommand,
    Task,
    TimeField,
    TranscribeCommand,
    UpdateTaskCommand,
)
from todo_backend.repositories.assistant_settings import AssistantSettingsRepository
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.reminders import ReminderRepository
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.documents import extract_document_text

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_RULES: dict[str, tuple[set[str], int]] = {
    "image": ({".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024),
    "document": ({".pdf", ".docx", ".txt", ".md"}, 10 * 1024 * 1024),
    "audio": ({".mp3", ".wav", ".m4a"}, 25 * 1024 * 1024),
}
_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain", ".md": "text/markdown",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/m4a",
}
_AUDIO_FORMAT_BY_EXT = {".mp3": "mp3", ".wav": "wav", ".m4a": "m4a"}
_TITLE_LENGTH = 30


class AssistantNotConfiguredError(RuntimeError):
    pass


class AssistantUnavailableError(RuntimeError):
    pass


class UnsupportedFileTypeError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class UploadNotFoundError(LookupError):
    pass


class ProposalAlreadyResolvedError(RuntimeError):
    pass


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _default_ark_factory(config: AssistantSettings) -> ArkClient:
    return ArkClient(config.api_key, config.chat_model, config.audio_model)


class AssistantService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        ark_factory: Callable[[AssistantSettings], Any] | None = None,
    ) -> None:
        self.database = database
        self._settings = settings
        self._conversations = ConversationsRepository()
        self._assistant_settings = AssistantSettingsRepository()
        self._tasks = TaskRepository()
        self._reminders = ReminderRepository()
        self._ark_factory = ark_factory or _default_ark_factory

    @property
    def _uploads_dir(self) -> Path:
        return self._settings.database_path.parent / "assistant_uploads"

    def _upload_path(self, file_id: str) -> Path:
        if "/" in file_id or "\\" in file_id or ".." in file_id:
            raise UploadNotFoundError
        uploads_dir = self._uploads_dir.resolve()
        path = (uploads_dir / file_id).resolve()
        if not path.is_relative_to(uploads_dir):
            raise UploadNotFoundError
        return path

    # ---- settings ----

    def get_settings_view(self) -> AssistantSettingsView:
        with self.database.transaction() as connection:
            config = self._assistant_settings.get(connection)
        return self._view(config)

    def patch_settings(
        self, command: AssistantSettingsPatchCommand
    ) -> AssistantSettingsView:
        with self.database.transaction() as connection:
            config = self._assistant_settings.patch(connection, command)
        return self._view(config)

    def _view(self, config: AssistantSettings) -> AssistantSettingsView:
        return AssistantSettingsView(
            hasApiKey=bool(config.api_key),
            chatModel=config.chat_model,
            audioModel=config.audio_model,
        )

    def _require_ark(self) -> Any:
        with self.database.transaction() as connection:
            config = self._assistant_settings.get(connection)
        if not config.api_key:
            raise AssistantNotConfiguredError
        return self._ark_factory(config)

    # ---- conversations ----

    def create_conversation(self) -> AssistantConversationSummary:
        with self.database.transaction() as connection:
            return self._conversations.create_conversation(connection, "")

    def list_conversations(self) -> list[AssistantConversationSummary]:
        with self.database.transaction() as connection:
            return self._conversations.list_conversations(connection)

    def get_conversation_detail(self, conversation_id: str) -> AssistantConversationDetail:
        with self.database.transaction() as connection:
            return AssistantConversationDetail(
                conversation=self._conversations.get_conversation(connection, conversation_id),
                messages=self._conversations.list_messages(connection, conversation_id),
                proposals=self._conversations.list_proposals(connection, conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self.database.transaction() as connection:
            file_ids = self._conversations.list_conversation_file_ids(
                connection, conversation_id
            )
            self._conversations.delete_conversation(connection, conversation_id)
        for file_id in file_ids:
            (self._uploads_dir / file_id).unlink(missing_ok=True)

    # ---- uploads & transcription ----

    def save_upload(self, filename: str, data: bytes) -> AssistantAttachment:
        suffix = Path(filename).suffix.lower()
        rule = next(
            ((kind, limit) for kind, (exts, limit) in UPLOAD_RULES.items() if suffix in exts),
            None,
        )
        if rule is None:
            raise UnsupportedFileTypeError
        kind, limit = rule
        if len(data) > limit:
            raise UploadTooLargeError
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        file_id = f"{uuid.uuid4().hex}{suffix}"
        (self._uploads_dir / file_id).write_bytes(data)
        return AssistantAttachment(
            fileId=file_id, kind=cast(AttachmentKind, kind),
            name=filename[:255], mime=_MIME_BY_EXT[suffix],
        )

    def transcribe(self, command: TranscribeCommand) -> str:
        ark = self._require_ark()
        path, audio_format = self._audio_path(command.file_id)
        audio_base64 = base64.b64encode(path.read_bytes()).decode()
        try:
            return ark.transcribe(audio_base64, audio_format)
        except ArkUnavailableError as error:
            raise AssistantUnavailableError from error

    def _audio_path(self, file_id: str) -> tuple[Path, str]:
        path = self._upload_path(file_id)
        audio_format = _AUDIO_FORMAT_BY_EXT.get(path.suffix.lower())
        if audio_format is None:
            raise UnsupportedFileTypeError
        if not path.is_file():
            raise UploadNotFoundError
        return path, audio_format

    # ---- agent turn ----

    def send_message(
        self, conversation_id: str, command: SendAssistantMessageCommand
    ) -> AssistantTurnResponse:
        ark = self._require_ark()
        attachments = [self._verified_attachment(a) for a in command.attachments]
        attachments = [self._enrich_document(a) for a in attachments]

        with self.database.transaction() as connection:
            conversation = self._conversations.get_conversation(connection, conversation_id)
            user_message = self._conversations.insert_message(
                connection, conversation_id, "user", command.content, attachments,
            )
            assistant_message = self._conversations.insert_message(
                connection, conversation_id, "assistant", "", [], status="pending",
            )
            if not conversation.title:
                title_source = command.content.strip() or (
                    attachments[0].name if attachments else ""
                )
                connection.execute(
                    "UPDATE assistant_conversations SET title = ? WHERE id = ?",
                    (title_source[:_TITLE_LENGTH], conversation_id),
                )
            self._conversations.touch(connection, conversation_id)

        try:
            enriched = [self._enrich_audio(ark, a) for a in attachments]
            if enriched != attachments:
                with self.database.transaction() as connection:
                    self._conversations.update_message_attachments(
                        connection, user_message.id, enriched
                    )
            turn = self._run_agent(ark, conversation_id, assistant_message.id)
        except ArkUnavailableError:
            with self.database.transaction() as connection:
                self._conversations.update_message(
                    connection, assistant_message.id,
                    content="", status="failed", tool_trace=None,
                )
            failed = AssistantMessage(
                id=assistant_message.id, role="assistant", content="",
                attachments=[], status="failed", createdAt=assistant_message.created_at,
            )
            return AssistantTurnResponse(message=failed, proposals=[])

        with self.database.transaction() as connection:
            self._conversations.update_message(
                connection, assistant_message.id,
                content=turn.content, status="done",
                tool_trace=json.dumps(turn.tool_trace, ensure_ascii=False),
            )
            proposals = [
                self._conversations.get_proposal(connection, proposal_id)
                for proposal_id in turn.proposal_ids
            ]
        done = AssistantMessage(
            id=assistant_message.id, role="assistant", content=turn.content,
            attachments=[], status="done", createdAt=assistant_message.created_at,
        )
        return AssistantTurnResponse(message=done, proposals=proposals)

    def _verified_attachment(self, attachment: AssistantAttachment) -> AssistantAttachment:
        path = self._upload_path(attachment.file_id)
        if not path.is_file():
            raise UploadNotFoundError
        suffix = path.suffix.lower()
        kind = next(
            (kind for kind, (exts, _limit) in UPLOAD_RULES.items() if suffix in exts), None
        )
        if kind is None:
            raise UnsupportedFileTypeError
        return attachment.model_copy(update={"kind": kind, "extracted_text": None})

    def _enrich_document(self, attachment: AssistantAttachment) -> AssistantAttachment:
        if attachment.kind != "document":
            return attachment
        text = extract_document_text(self._upload_path(attachment.file_id))
        return attachment.model_copy(update={"extracted_text": text})

    def _enrich_audio(self, ark: Any, attachment: AssistantAttachment) -> AssistantAttachment:
        if attachment.kind != "audio":
            return attachment
        path, audio_format = self._audio_path(attachment.file_id)
        audio_base64 = base64.b64encode(path.read_bytes()).decode()
        text = ark.transcribe(audio_base64, audio_format)
        return attachment.model_copy(update={"extracted_text": text})

    def _run_agent(
        self,
        ark: Any,
        conversation_id: str,
        assistant_message_id: str,
    ) -> AgentTurn:
        with self.database.transaction() as connection:
            messages = self._conversations.list_messages(connection, conversation_id)
            pending = self._conversations.list_pending_proposals(connection, conversation_id)
            row = connection.execute(
                "SELECT language FROM app_settings WHERE id = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Application settings are not initialized")
            language = row["language"]
        tools = AgentTools(
            self.database,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
        )
        orchestrator = AgentOrchestrator(
            ark,
            tools,
            language=language,
            now_local=time.strftime("%Y-%m-%dT%H:%M"),
            pending_summary=self._pending_summary(pending),
        )
        history = [{"role": "system", "content": orchestrator.system_prompt()}]
        history.extend(self._build_ark_messages(messages, language))
        return orchestrator.run(history)

    def _build_ark_messages(
        self, messages: list[AssistantMessage], language: str
    ) -> list[dict[str, Any]]:
        attachment_fallback = "（附件消息）" if language == "zh-CN" else "(attachment message)"
        ark_messages: list[dict[str, Any]] = []
        for message in messages[-HISTORY_LIMIT:]:
            if message.role == "assistant":
                if message.status == "done" and message.content:
                    ark_messages.append({"role": "assistant", "content": message.content})
                continue
            parts: list[dict[str, Any]] = []
            text = message.content
            for attachment in message.attachments:
                if attachment.kind == "image":
                    path = self._upload_path(attachment.file_id)
                    encoded = base64.b64encode(path.read_bytes()).decode()
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{attachment.mime};base64,{encoded}"},
                    })
                elif attachment.extracted_text:
                    text += f"\n\n〈{attachment.name}〉\n{attachment.extracted_text}"
            parts.append({"type": "text", "text": text or attachment_fallback})
            ark_messages.append({"role": "user", "content": parts})
        return ark_messages

    def _pending_summary(self, pending: list[AssistantProposal]) -> str:
        lines: list[str] = []
        for proposal in pending:
            label = proposal.payload.text or proposal.task_id or ""
            lines.append(f"- [{proposal.id}] {proposal.action}: {label}")
        return "\n".join(lines)

    # ---- proposals ----

    def accept_proposal(
        self, proposal_id: str
    ) -> tuple[AssistantProposal, Task | None]:
        with self.database.transaction() as connection:
            proposal = self._conversations.get_proposal(connection, proposal_id)
            if proposal.status != "pending":
                raise ProposalAlreadyResolvedError
            task: Task | None = None
            if proposal.action == "create":
                task = self._tasks.create(
                    connection,
                    CreateTaskCommand(
                        text=proposal.payload.text or "",
                        priority=proposal.payload.priority or "medium",
                        category=proposal.payload.category or "other",
                        time=self._time_field(proposal.payload),
                        notes=proposal.payload.notes,
                    ),
                )
            elif proposal.action == "update":
                task = self._tasks.update(
                    connection,
                    proposal.task_id or "",
                    UpdateTaskCommand(**self._update_kwargs(proposal.payload)),
                )
                if {"time_start", "time_end"} & proposal.payload.model_fields_set:
                    self._reminders.prune_stale(
                        connection,
                        task.id,
                        task.time.start if task.time else None,
                    )
            else:
                self._tasks.delete(connection, proposal.task_id or "")
            resolved = self._conversations.mark_proposal(
                connection, proposal_id, "accepted", _now_ms()
            )
        return resolved, task

    def reject_proposal(self, proposal_id: str) -> AssistantProposal:
        with self.database.transaction() as connection:
            proposal = self._conversations.get_proposal(connection, proposal_id)
            if proposal.status != "pending":
                raise ProposalAlreadyResolvedError
            return self._conversations.mark_proposal(
                connection, proposal_id, "rejected", _now_ms()
            )

    def _time_field(self, payload: Any) -> TimeField | None:
        if not payload.time_start:
            return None
        return TimeField(start=payload.time_start, end=payload.time_end)

    def _update_kwargs(self, payload: Any) -> dict[str, Any]:
        fields_set = payload.model_fields_set
        kwargs: dict[str, Any] = {}
        for name in ("text", "priority", "category"):
            value = getattr(payload, name)
            if name in fields_set and value is not None:
                kwargs[name] = value
        if "notes" in fields_set:
            kwargs["notes"] = payload.notes
        if {"time_start", "time_end"} & fields_set:
            kwargs["time"] = (
                TimeField(start=payload.time_start, end=payload.time_end)
                if payload.time_start
                else None
            )
        return kwargs
