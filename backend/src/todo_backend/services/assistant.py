import asyncio
import base64
import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from todo_backend.agent.apply_graph import ProposalApplyWorkflow
from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError
from todo_backend.agent.checkpoints import CheckpointStore
from todo_backend.agent.planning import ArkPlanner
from todo_backend.agent.turn_graph import (
    AssistantTurnWorkflow,
    TurnGraphDependencies,
)
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
    AssistantTurnRecord,
    AssistantTurnResponse,
    AttachmentKind,
    ConfirmProposalBatchCommand,
    ConfirmProposalItem,
    ProposalBatchResolveResponse,
    SendAssistantMessageCommand,
    Task,
    TranscribeCommand,
)
from todo_backend.repositories.assistant_settings import AssistantSettingsRepository
from todo_backend.repositories.conversations import (
    AssistantTurnNotFoundError,
    ConversationsRepository,
)
from todo_backend.repositories.proposal_batches import ProposalBatchesRepository
from todo_backend.services.documents import extract_document_text
from todo_backend.services.proposal_batches import (
    ProposalBatchExecutor,
    ProposalBatchNotConfirmableError,
)
from todo_backend.services.tasks import TaskService

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_RULES: dict[str, tuple[set[str], int]] = {
    "image": ({".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024),
    "document": ({".pdf", ".docx", ".txt", ".md"}, 10 * 1024 * 1024),
    "audio": ({".mp3", ".wav", ".m4a"}, 25 * 1024 * 1024),
}
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/m4a",
}
_AUDIO_FORMAT_BY_EXT = {".mp3": "mp3", ".wav": "wav", ".m4a": "m4a"}
_TITLE_LENGTH = 30
_HISTORY_LIMIT = 20


class AssistantNotConfiguredError(RuntimeError):
    pass


class AssistantUnavailableError(RuntimeError):
    pass


class AssistantTurnActiveError(RuntimeError):
    pass


class AssistantTurnPayloadMismatchError(RuntimeError):
    pass


class ProposalBatchRequiredError(RuntimeError):
    pass


class UnsupportedFileTypeError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class UploadNotFoundError(LookupError):
    pass


def _default_ark_factory(config: AssistantSettings) -> ArkClient:
    return ArkClient(config.api_key, config.chat_model, config.audio_model, config.base_url)


def _request_fingerprint(command: SendAssistantMessageCommand) -> str:
    stable_request = {
        "content": command.content,
        "attachmentFileIds": [
            attachment.file_id for attachment in command.attachments
        ],
    }
    serialized = json.dumps(
        stable_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AssistantService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        ark_factory: Callable[[AssistantSettings], Any] | None = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.database = database
        self._settings = settings
        self._conversations = ConversationsRepository()
        self._assistant_settings = AssistantSettingsRepository()
        self._tasks = TaskService(database)
        self._ark_factory = ark_factory or _default_ark_factory
        self._checkpoint_store = checkpoint_store or CheckpointStore(
            settings.database_path.parent / "assistant_graph.sqlite3"
        )
        self._batch_repository = ProposalBatchesRepository()
        self._batch_executor = ProposalBatchExecutor(
            database, self._batch_repository
        )
        self._apply_workflow = ProposalApplyWorkflow(
            self._batch_executor, self._checkpoint_store.saver
        )
        self._running_turns: set[str] = set()
        self._running_turns_lock = threading.Lock()
        self._ark_cache: tuple[AssistantSettings, Any] | None = None

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

    def close(self) -> None:
        self._checkpoint_store.close()

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
        self._ark_cache = None
        return self._view(config)

    def _view(self, config: AssistantSettings) -> AssistantSettingsView:
        return AssistantSettingsView(
            hasApiKey=bool(config.api_key),
            chatModel=config.chat_model,
            audioModel=config.audio_model,
            baseUrl=config.base_url,
        )

    def _require_ark(self) -> Any:
        with self.database.transaction() as connection:
            config = self._assistant_settings.get(connection)
        if not config.api_key:
            raise AssistantNotConfiguredError
        if self._ark_cache is not None and self._ark_cache[0] == config:
            return self._ark_cache[1]
        ark = self._ark_factory(config)
        self._ark_cache = (config, ark)
        return ark

    # ---- conversations ----

    def create_conversation(self) -> AssistantConversationSummary:
        with self.database.transaction() as connection:
            return self._conversations.create_conversation(connection, "")

    def list_conversations(self) -> list[AssistantConversationSummary]:
        with self.database.transaction() as connection:
            return self._conversations.list_conversations(connection)

    def get_conversation_detail(
        self, conversation_id: str
    ) -> AssistantConversationDetail:
        with self.database.transaction() as connection:
            return AssistantConversationDetail(
                conversation=self._conversations.get_conversation(
                    connection, conversation_id
                ),
                messages=self._conversations.list_messages(
                    connection, conversation_id
                ),
                proposalBatches=self._batch_repository.list_for_conversation(
                    connection, conversation_id
                ),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self.database.transaction() as connection:
            file_ids = self._conversations.list_conversation_file_ids(
                connection, conversation_id
            )
            turn_ids = self._conversations.list_turn_ids(connection, conversation_id)
            batch_ids = self._batch_repository.list_batch_ids(
                connection, conversation_id
            )
            self._conversations.delete_conversation(connection, conversation_id)
        for turn_id in turn_ids:
            self._checkpoint_store.delete_thread(f"turn:{turn_id}")
        for batch_id in batch_ids:
            self._checkpoint_store.delete_thread(f"proposal:{batch_id}")
        for file_id in file_ids:
            (self._uploads_dir / file_id).unlink(missing_ok=True)

    # ---- uploads & transcription ----

    def save_upload(self, filename: str, data: bytes) -> AssistantAttachment:
        suffix = Path(filename).suffix.lower()
        rule = next(
            (
                (kind, limit)
                for kind, (extensions, limit) in UPLOAD_RULES.items()
                if suffix in extensions
            ),
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
            fileId=file_id,
            kind=cast(AttachmentKind, kind),
            name=filename[:255],
            mime=_MIME_BY_EXT[suffix],
        )

    def transcribe(self, command: TranscribeCommand) -> str:
        ark = self._require_ark()
        path, audio_format = self._audio_path(command.file_id)
        audio_base64 = base64.b64encode(path.read_bytes()).decode()
        try:
            return cast(str, ark.transcribe(audio_base64, audio_format))
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

    # ---- assistant turns ----

    def send_message(
        self, conversation_id: str, command: SendAssistantMessageCommand
    ) -> AssistantTurnResponse:
        fingerprint = _request_fingerprint(command)
        existing = self._existing_turn_response(
            conversation_id, command.turn_id, fingerprint
        )
        if isinstance(existing, AssistantTurnResponse):
            return existing

        turn = existing
        if turn is None:
            verified_attachments = [
                self._verified_attachment(attachment)
                for attachment in command.attachments
            ]
        else:
            verified_attachments = []
        ark = self._require_ark()

        if turn is None:
            try:
                turn = self._insert_turn(
                    conversation_id,
                    command,
                    fingerprint,
                    verified_attachments,
                )
            except sqlite3.IntegrityError as error:
                raise AssistantTurnActiveError from error
        elif turn.status == "failed":
            try:
                with self.database.transaction() as connection:
                    self._conversations.mark_turn(
                        connection, turn.id, "active", None
                    )
                    self._conversations.update_message(
                        connection,
                        turn.assistant_message_id,
                        content="",
                        status="pending",
                        tool_trace=None,
                    )
                    turn = self._conversations.get_turn(connection, turn.id)
            except sqlite3.IntegrityError as error:
                raise AssistantTurnActiveError from error

        with self._claim_running_turn(turn.id):
            try:
                self._enrich_turn_attachments(turn, ark)
                workflow = AssistantTurnWorkflow(
                    TurnGraphDependencies(
                        database=self.database,
                        conversations=self._conversations,
                        batches=self._batch_repository,
                        tasks=self._tasks,
                        planner=ArkPlanner(ark),
                        ark=ark,
                        apply_workflow=self._apply_workflow,
                        build_ark_messages=self._build_ark_messages,
                    ),
                    self._checkpoint_store.saver,
                )
                return workflow.run(turn.id)
            except ArkUnavailableError:
                return self._fail_turn(turn, "ASSISTANT_UNAVAILABLE")
            except Exception:
                self._fail_turn(turn, "TURN_GRAPH_FAILED")
                raise

    async def send_message_stream(
        self, conversation_id: str, command: SendAssistantMessageCommand
    ) -> "AsyncIterator[dict[str, Any]]":
        """Send a message and stream SSE events as the agent processes it."""
        import asyncio as _asyncio
        fingerprint = _request_fingerprint(command)
        existing = self._existing_turn_response(
            conversation_id, command.turn_id, fingerprint
        )
        if isinstance(existing, AssistantTurnResponse):
            yield {"event": "done", "data": {
                "message": existing.message.model_dump(mode="json", by_alias=True),
                "proposalBatches": [
                    b.model_dump(mode="json", by_alias=True) for b in existing.proposalBatches
                ],
            }}
            return

        turn = existing
        if turn is None:
            verified_attachments = [
                self._verified_attachment(attachment)
                for attachment in command.attachments
            ]
        else:
            verified_attachments = []
        ark = self._require_ark()

        if turn is None:
            try:
                turn = self._insert_turn(
                    conversation_id, command, fingerprint, verified_attachments,
                )
            except sqlite3.IntegrityError as error:
                raise AssistantTurnActiveError from error
        elif turn.status == "failed":
            try:
                with self.database.transaction() as connection:
                    self._conversations.mark_turn(connection, turn.id, "active", None)
                    self._conversations.update_message(
                        connection, turn.assistant_message_id,
                        content="", status="pending", tool_trace=None,
                    )
                    turn = self._conversations.get_turn(connection, turn.id)
            except sqlite3.IntegrityError as error:
                raise AssistantTurnActiveError from error

        with self._claim_running_turn(turn.id):
            stream_done = False
            try:
                self._enrich_turn_attachments(turn, ark)
                queue: _asyncio.Queue = _asyncio.Queue()

                def on_event(event_type: str, data: dict[str, Any]) -> None:
                    try:
                        queue.put_nowait({"event": event_type, "data": data})
                    except _asyncio.QueueFull:
                        pass

                workflow = AssistantTurnWorkflow(
                    TurnGraphDependencies(
                        database=self.database,
                        conversations=self._conversations,
                        batches=self._batch_repository,
                        tasks=self._tasks,
                        planner=ArkPlanner(ark),
                        ark=ark,
                        apply_workflow=self._apply_workflow,
                        build_ark_messages=self._build_ark_messages,
                        on_event=on_event,
                    ),
                    self._checkpoint_store.saver,
                )

                def _run() -> None:
                    try:
                        workflow.run(turn.id)
                    except ArkUnavailableError:
                        self._fail_turn(turn, "ASSISTANT_UNAVAILABLE")
                        try:
                            queue.put_nowait({"event": "error", "data": {"code": "ASSISTANT_UNAVAILABLE", "message": "Assistant unavailable"}})
                        except _asyncio.QueueFull:
                            pass
                    except Exception:
                        self._fail_turn(turn, "TURN_GRAPH_FAILED")
                        try:
                            queue.put_nowait({"event": "error", "data": {"code": "TURN_GRAPH_FAILED", "message": "Internal error"}})
                        except _asyncio.QueueFull:
                            pass

                loop = _asyncio.get_running_loop()
                loop.run_in_executor(None, _run)

                _STREAM_TIMEOUT = 120  # seconds max wait between events
                while True:
                    try:
                        event = await _asyncio.wait_for(queue.get(), timeout=_STREAM_TIMEOUT)
                    except TimeoutError:
                        self._fail_turn(turn, "STREAM_TIMEOUT")
                        yield {"event": "error", "data": {"code": "STREAM_TIMEOUT", "message": "Stream timed out"}}
                        stream_done = True
                        break
                    yield event
                    if event["event"] in ("done", "error"):
                        stream_done = True
                        break

            except ArkUnavailableError:
                self._fail_turn(turn, "ASSISTANT_UNAVAILABLE")
                yield {"event": "error", "data": {"code": "ASSISTANT_UNAVAILABLE", "message": "Assistant unavailable"}}
                stream_done = True
            except Exception:
                self._fail_turn(turn, "TURN_GRAPH_FAILED")
                yield {"event": "error", "data": {"code": "TURN_GRAPH_FAILED", "message": "Internal error"}}
                stream_done = True
            finally:
                if not stream_done:
                    # Client disconnected before completion — fail the turn
                    try:
                        self._fail_turn(turn, "STREAM_DISCONNECTED")
                    except Exception:
                        pass

    def _existing_turn_response(
        self,
        conversation_id: str,
        turn_id: str,
        fingerprint: str,
    ) -> AssistantTurnRecord | AssistantTurnResponse | None:
        with self.database.transaction() as connection:
            try:
                turn = self._conversations.get_turn(connection, turn_id)
            except AssistantTurnNotFoundError:
                return None
            if (
                turn.conversation_id != conversation_id
                or turn.request_fingerprint != fingerprint
            ):
                raise AssistantTurnPayloadMismatchError
            if turn.status != "done":
                return turn
            message = self._conversations.get_message(
                connection, turn.assistant_message_id
            )
            batches = self._batch_repository.list_for_message(
                connection, turn.assistant_message_id
            )
        return AssistantTurnResponse(message=message, proposalBatches=batches)

    def _insert_turn(
        self,
        conversation_id: str,
        command: SendAssistantMessageCommand,
        fingerprint: str,
        attachments: list[AssistantAttachment],
    ) -> AssistantTurnRecord:
        with self.database.transaction() as connection:
            conversation = self._conversations.get_conversation(
                connection, conversation_id
            )
            user_message = self._conversations.insert_message(
                connection,
                conversation_id,
                "user",
                command.content,
                attachments,
                turn_id=command.turn_id,
            )
            assistant_message = self._conversations.insert_message(
                connection,
                conversation_id,
                "assistant",
                "",
                [],
                status="pending",
                turn_id=command.turn_id,
            )
            turn = self._conversations.insert_turn(
                connection,
                command.turn_id,
                conversation_id,
                user_message.id,
                assistant_message.id,
                fingerprint,
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
        return turn

    @contextmanager
    def _claim_running_turn(self, turn_id: str) -> Iterator[None]:
        with self._running_turns_lock:
            if turn_id in self._running_turns:
                raise AssistantTurnActiveError
            self._running_turns.add(turn_id)
        try:
            yield
        finally:
            with self._running_turns_lock:
                self._running_turns.discard(turn_id)

    def _enrich_turn_attachments(
        self, turn: AssistantTurnRecord, ark: Any
    ) -> None:
        with self.database.transaction() as connection:
            user_message = self._conversations.get_message(
                connection, turn.user_message_id
            )
        enriched = [
            self._enrich_attachment(ark, attachment)
            if attachment.extracted_text is None
            else attachment
            for attachment in user_message.attachments
        ]
        if enriched == user_message.attachments:
            return
        with self.database.transaction() as connection:
            self._conversations.update_message_attachments(
                connection, user_message.id, enriched
            )

    def _fail_turn(
        self, turn: AssistantTurnRecord, error_code: str
    ) -> AssistantTurnResponse:
        with self.database.transaction() as connection:
            self._conversations.update_message(
                connection,
                turn.assistant_message_id,
                content="",
                status="failed",
                tool_trace=None,
            )
            self._conversations.mark_turn(
                connection, turn.id, "failed", error_code
            )
            message = self._conversations.get_message(
                connection, turn.assistant_message_id
            )
        return AssistantTurnResponse(message=message, proposalBatches=[])

    def _verified_attachment(
        self, attachment: AssistantAttachment
    ) -> AssistantAttachment:
        path = self._upload_path(attachment.file_id)
        if not path.is_file():
            raise UploadNotFoundError
        suffix = path.suffix.lower()
        kind = next(
            (
                candidate
                for candidate, (extensions, _limit) in UPLOAD_RULES.items()
                if suffix in extensions
            ),
            None,
        )
        if kind is None:
            raise UnsupportedFileTypeError
        return attachment.model_copy(
            update={
                "kind": kind,
                "mime": _MIME_BY_EXT[suffix],
                "extracted_text": None,
            }
        )

    def _enrich_attachment(
        self, ark: Any, attachment: AssistantAttachment
    ) -> AssistantAttachment:
        if attachment.kind == "document":
            text = extract_document_text(self._upload_path(attachment.file_id))
            return attachment.model_copy(update={"extracted_text": text})
        if attachment.kind == "audio":
            path, audio_format = self._audio_path(attachment.file_id)
            audio_base64 = base64.b64encode(path.read_bytes()).decode()
            text = ark.transcribe(audio_base64, audio_format)
            return attachment.model_copy(update={"extracted_text": text})
        return attachment

    def _build_ark_messages(
        self, messages: list[AssistantMessage], language: str
    ) -> list[dict[str, Any]]:
        attachment_fallback = (
            "（附件消息）" if language == "zh-CN" else "(attachment message)"
        )
        ark_messages: list[dict[str, Any]] = []
        for message in messages[-_HISTORY_LIMIT:]:
            if message.role == "assistant":
                if message.status == "done" and message.content:
                    ark_messages.append(
                        {"role": "assistant", "content": message.content}
                    )
                continue
            parts: list[dict[str, Any]] = []
            text = message.content
            for attachment in message.attachments:
                if attachment.kind == "image":
                    path = self._upload_path(attachment.file_id)
                    encoded = base64.b64encode(path.read_bytes()).decode()
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{attachment.mime};base64,{encoded}"
                            },
                        }
                    )
                elif attachment.extracted_text:
                    text += (
                        f"\n\n〈{attachment.name}〉\n"
                        f"{attachment.extracted_text}"
                    )
            parts.append(
                {"type": "text", "text": text or attachment_fallback}
            )
            ark_messages.append({"role": "user", "content": parts})
        return ark_messages

    # ---- proposal batches ----

    def confirm_proposal_batch(
        self, batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        current = self._batch_executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current
        self._apply_workflow.start(batch_id)
        return self._apply_workflow.confirm(batch_id, command)

    def reject_proposal_batch(
        self, batch_id: str
    ) -> ProposalBatchResolveResponse:
        current = self._batch_executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current
        self._apply_workflow.start(batch_id)
        return self._apply_workflow.reject(batch_id)

    def accept_proposal(
        self, proposal_id: str
    ) -> tuple[AssistantProposal, Task | None]:
        proposal, batch_size = self._legacy_proposal(proposal_id)
        if batch_size != 1:
            raise ProposalBatchRequiredError
        result = self.confirm_proposal_batch(
            proposal.batch_id,
            ConfirmProposalBatchCommand(
                items=[
                    ConfirmProposalItem(
                        proposalId=proposal.id,
                        payload=proposal.payload,
                    )
                ]
            ),
        )
        item = result.items[0]
        return item.proposal, item.task

    def reject_proposal(self, proposal_id: str) -> AssistantProposal:
        proposal, batch_size = self._legacy_proposal(proposal_id)
        if batch_size != 1:
            raise ProposalBatchRequiredError
        result = self.reject_proposal_batch(proposal.batch_id)
        return result.items[0].proposal

    def _legacy_proposal(
        self, proposal_id: str
    ) -> tuple[AssistantProposal, int]:
        with self.database.transaction() as connection:
            proposal = self._batch_repository.get_proposal(
                connection, proposal_id
            )
            batch = self._batch_repository.get_batch(
                connection, proposal.batch_id
            )
        return proposal, len(batch.proposals)
