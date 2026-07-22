# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from todo_backend.agent.ark_client import ArkChatResult, ArkUnavailableError
from todo_backend.agent.turn_graph import AssistantTurnWorkflow
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantAttachment,
    AssistantProposalBatch,
    AssistantSettingsPatchCommand,
    ConfirmProposalBatchCommand,
    ConfirmProposalItem,
    ProposalCardFields,
    SendAssistantMessageCommand,
    TranscribeCommand,
)
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchesRepository,
    ProposalDraft,
)
from todo_backend.services.assistant import (
    AssistantNotConfiguredError,
    AssistantService,
    AssistantTurnActiveError,
    AssistantTurnPayloadMismatchError,
    UnsupportedFileTypeError,
    UploadNotFoundError,
    UploadTooLargeError,
)


def create_plan_payload(text: str) -> dict[str, Any]:
    return {
        "kind": "mutations",
        "evidence": "用户明确要求新建",
        "items": [{"action": "create", "fields": {"text": text}}],
    }


def query_plan_payload() -> dict[str, Any]:
    return {
        "kind": "query",
        "evidence": "用户在询问",
        "query": "回应用户",
        "items": [],
    }


class FakeArk:
    def __init__(
        self,
        *,
        plan_results: list[dict[str, Any] | BaseException] | None = None,
        chat_results: list[ArkChatResult | BaseException] | None = None,
        transcription: str | BaseException = "转写结果",
    ) -> None:
        self.plan_results = list(plan_results or [])
        self.chat_results = list(chat_results or [])
        self.transcription = transcription
        self.mock_calls: list[tuple[str, object]] = []

    def plan(
        self, messages: list[dict[str, Any]], submit_plan_tool: dict[str, Any]
    ) -> dict[str, Any]:
        self.mock_calls.append(("plan", messages))
        del submit_plan_tool
        result = self.plan_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: str = "disabled",
    ) -> ArkChatResult:
        self.mock_calls.append(
            (
                "chat",
                {
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "thinking": thinking,
                },
            )
        )
        result = self.chat_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        self.mock_calls.append(
            ("transcribe", {"audio": audio_base64, "format": audio_format})
        )
        if isinstance(self.transcription, BaseException):
            raise self.transcription
        return self.transcription

    def reset_mock(self) -> None:
        self.mock_calls.clear()


class BlockingArk(FakeArk):
    def __init__(self) -> None:
        super().__init__(plan_results=[create_plan_payload("A")])
        self.started = threading.Event()
        self.release = threading.Event()

    def plan(
        self, messages: list[dict[str, Any]], submit_plan_tool: dict[str, Any]
    ) -> dict[str, Any]:
        self.started.set()
        assert self.release.wait(timeout=5)
        return super().plan(messages, submit_plan_tool)


class CapabilityCachingArk(FakeArk):
    def __init__(self) -> None:
        super().__init__(
            plan_results=[create_plan_payload("A"), create_plan_payload("B")]
        )
        self.planning_thinking_supported: bool | None = None
        self.thinking_attempts: list[str] = []

    def plan(
        self, messages: list[dict[str, Any]], submit_plan_tool: dict[str, Any]
    ) -> dict[str, Any]:
        if self.planning_thinking_supported is None:
            self.thinking_attempts.extend(["enabled", "disabled"])
            self.planning_thinking_supported = False
        else:
            self.thinking_attempts.append("disabled")
        return super().plan(messages, submit_plan_tool)


@dataclass(frozen=True, slots=True)
class AssistantFixture:
    service: AssistantService
    fake_ark: FakeArk


@dataclass(frozen=True, slots=True)
class PersistentServiceFactory:
    database_path: Path
    settings: Settings

    def open(self, fake_ark: FakeArk) -> AssistantService:
        database = Database(
            self.database_path, Path(__file__).parents[1] / "migrations"
        )
        database.initialize()
        return AssistantService(
            database,
            self.settings,
            ark_factory=lambda _settings: fake_ark,
        )


@pytest.fixture
def assistant(tmp_path: Path) -> Iterator[AssistantFixture]:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    fake_ark = FakeArk()
    service = AssistantService(
        database, settings, ark_factory=lambda _settings: fake_ark
    )
    _initialize_app_settings(database)
    try:
        yield AssistantFixture(service, fake_ark)
    finally:
        service.close()


@pytest.fixture
def persistent_service_factory(tmp_path: Path) -> PersistentServiceFactory:
    database_path = tmp_path / "todo.sqlite3"
    database = Database(database_path, Path(__file__).parents[1] / "migrations")
    database.initialize()
    _initialize_app_settings(database)
    return PersistentServiceFactory(
        database_path=database_path,
        settings=Settings(database_path, "127.0.0.1", 8000, "test-token"),
    )


def _initialize_app_settings(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_settings (id, theme, muted, shortcut, language)"
            " VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT', 'zh-CN')"
        )


def _configure(service: AssistantService) -> None:
    service.patch_settings(AssistantSettingsPatchCommand(apiKey="sk-test"))


def _card(text: str) -> ProposalCardFields:
    return ProposalCardFields(
        text=text,
        priority="medium",
        category="other",
        time_start=None,
        time_end=None,
        notes=None,
    )


def seed_create_batch(
    database: Database,
    *,
    text: str,
    item_count: int = 1,
    batch_id: str | None = None,
) -> AssistantProposalBatch:
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    resolved_batch_id = batch_id or f"batch-{uuid.uuid4().hex}"
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "待确认", []
        )
        return batches.insert_batches(
            connection,
            conversation_id=conversation.id,
            message_id=message.id,
            drafts=[
                BatchDraft(
                    id=resolved_batch_id,
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id=f"{resolved_batch_id}-p{index}",
                            action="create",
                            target_task_id=None,
                            before_snapshot=None,
                            payload=_card(f"{text}{index}" if item_count > 1 else text),
                        )
                        for index in range(item_count)
                    ],
                )
            ],
        )[0]


def seed_partially_applicable_batch(database: Database) -> AssistantProposalBatch:
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    batch_id = f"mixed-{uuid.uuid4().hex}"
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "待确认", []
        )
        return batches.insert_batches(
            connection,
            conversation_id=conversation.id,
            message_id=message.id,
            drafts=[
                BatchDraft(
                    id=batch_id,
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id=f"{batch_id}-create",
                            action="create",
                            target_task_id=None,
                            before_snapshot=None,
                            payload=_card("可创建"),
                        ),
                        ProposalDraft(
                            id=f"{batch_id}-missing",
                            action="delete",
                            target_task_id="missing-task",
                            before_snapshot=None,
                            payload=_card("已不存在"),
                        ),
                    ],
                )
            ],
        )[0]


def _confirm_stored_batch(batch: AssistantProposalBatch) -> ConfirmProposalBatchCommand:
    return ConfirmProposalBatchCommand(
        items=[
            ConfirmProposalItem(
                proposalId=proposal.id,
                payload=proposal.payload,
            )
            for proposal in batch.proposals
        ]
    )


def test_send_message_requires_api_key(assistant: AssistantFixture) -> None:
    service = assistant.service
    conversation = service.create_conversation()
    with pytest.raises(AssistantNotConfiguredError):
        service.send_message(
            conversation.id,
            SendAssistantMessageCommand(
                turnId="turn-no-key", content="你好", attachments=[]
            ),
        )


def test_send_message_persists_structured_turn(assistant: AssistantFixture) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [query_plan_payload()]
    fake_ark.chat_results = [ArkChatResult(content="你好！我可以帮你规划。")]
    conversation = service.create_conversation()

    turn = service.send_message(
        conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-query-1", content="你好", attachments=[]
        ),
    )

    detail = service.get_conversation_detail(conversation.id)
    assert turn.message.content == "你好！我可以帮你规划。"
    assert turn.message.status == "done"
    assert turn.message.turn_id == "turn-query-1"
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.proposal_batches == []
    assert detail.conversation.title == "你好"


def test_retry_same_turn_does_not_duplicate_messages_or_batches(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [
        ArkUnavailableError("down"),
        create_plan_payload("买菜"),
    ]
    conversation = service.create_conversation()
    command = SendAssistantMessageCommand(
        turnId="turn-retry-1", content="新建买菜任务", attachments=[]
    )

    first = service.send_message(conversation.id, command)
    second = service.send_message(conversation.id, command)
    detail = service.get_conversation_detail(conversation.id)

    assert first.message.status == "failed"
    assert second.message.status == "done"
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1
    assert len(detail.proposal_batches[0].proposals) == 1


def test_same_turn_id_with_changed_payload_is_rejected(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [create_plan_payload("A")]
    conversation = service.create_conversation()
    service.send_message(
        conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-fixed", content="新建 A", attachments=[]
        ),
    )

    with pytest.raises(AssistantTurnPayloadMismatchError):
        service.send_message(
            conversation.id,
            SendAssistantMessageCommand(
                turnId="turn-fixed", content="新建 B", attachments=[]
            ),
        )


def test_retry_fingerprint_ignores_backend_attachment_enrichment(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [
        ArkUnavailableError("temporary"),
        create_plan_payload("文档任务"),
    ]
    conversation = service.create_conversation()
    attachment = service.save_upload("计划.txt", "任务内容".encode())
    command = SendAssistantMessageCommand(
        turnId="turn-document-retry",
        content="新建文档里的任务",
        attachments=[attachment],
    )

    assert service.send_message(conversation.id, command).message.status == "failed"
    enriched = service.get_conversation_detail(conversation.id).messages[0]
    assert enriched.attachments[0].extracted_text == "任务内容"

    retried = service.send_message(conversation.id, command)
    detail = service.get_conversation_detail(conversation.id)
    assert retried.message.status == "done"
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1


@pytest.mark.parametrize(
    ("second_turn_id", "second_content"),
    [
        ("turn-active-a", "新建 A"),
        ("turn-active-b", "新建 B"),
    ],
)
def test_concurrent_turn_requests_receive_active_error(
    tmp_path: Path, second_turn_id: str, second_content: str
) -> None:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    _initialize_app_settings(database)
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    ark = BlockingArk()
    service = AssistantService(database, settings, ark_factory=lambda _settings: ark)
    _configure(service)
    conversation = service.create_conversation()
    failures: list[BaseException] = []

    def run_first() -> None:
        try:
            service.send_message(
                conversation.id,
                SendAssistantMessageCommand(
                    turnId="turn-active-a", content="新建 A", attachments=[]
                ),
            )
        except BaseException as error:
            failures.append(error)

    thread = threading.Thread(target=run_first)
    thread.start()
    assert ark.started.wait(timeout=5)
    try:
        with pytest.raises(AssistantTurnActiveError):
            service.send_message(
                conversation.id,
                SendAssistantMessageCommand(
                    turnId=second_turn_id,
                    content=second_content,
                    attachments=[],
                ),
            )
    finally:
        ark.release.set()
        thread.join(timeout=5)
        service.close()
    assert not thread.is_alive()
    assert failures == []


def test_accepted_turn_replay_returns_stored_response(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [create_plan_payload("买菜")]
    conversation = service.create_conversation()
    command = SendAssistantMessageCommand(
        turnId="turn-replay", content="新建买菜任务", attachments=[]
    )

    first = service.send_message(conversation.id, command)
    call_count = len(fake_ark.mock_calls)
    replay = service.send_message(conversation.id, command)

    assert replay == first
    assert len(fake_ark.mock_calls) == call_count
    detail = service.get_conversation_detail(conversation.id)
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1


def test_turn_graph_resumes_from_sqlite_after_service_reopen(
    persistent_service_factory: PersistentServiceFactory,
) -> None:
    first_ark = FakeArk(plan_results=[ArkUnavailableError("temporary")])
    first = persistent_service_factory.open(first_ark)
    _configure(first)
    conversation = first.create_conversation()
    command = SendAssistantMessageCommand(
        turnId="turn-restart-1", content="新建买菜任务", attachments=[]
    )
    assert first.send_message(conversation.id, command).message.status == "failed"
    assert first._checkpoint_store.has_thread("turn:turn-restart-1") is True
    first.close()

    second_ark = FakeArk(plan_results=[create_plan_payload("买菜")])
    second = persistent_service_factory.open(second_ark)
    result = second.send_message(conversation.id, command)
    detail = second.get_conversation_detail(conversation.id)
    second.close()

    assert result.message.status == "done"
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1
    assert len(detail.proposal_batches[0].proposals) == 1


def test_confirm_edited_batch_never_calls_ark(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    batch = seed_create_batch(service.database, text="原标题")
    fake_ark.reset_mock()

    result = service.confirm_proposal_batch(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[
                ConfirmProposalItem(
                    proposalId=batch.proposals[0].id,
                    payload=ProposalCardFields(
                        text="卡片编辑后",
                        priority="high",
                        category="work",
                        time_start=None,
                        time_end=None,
                        notes="直接写入",
                    ),
                )
            ]
        ),
    )

    assert result.items[0].task is not None
    assert result.items[0].task.text == "卡片编辑后"
    assert fake_ark.mock_calls == []


def test_legacy_pending_batch_gets_checkpoint_on_first_confirmation(
    assistant: AssistantFixture,
) -> None:
    service = assistant.service
    batch = seed_create_batch(service.database, text="迁移前卡片")
    thread_id = f"proposal:{batch.id}"
    assert service._checkpoint_store.has_thread(thread_id) is False

    result = service.confirm_proposal_batch(batch.id, _confirm_stored_batch(batch))

    assert result.batch.status == "accepted"
    assert service._checkpoint_store.has_thread(thread_id) is True


def test_partial_application_returns_item_errors(
    assistant: AssistantFixture,
) -> None:
    service = assistant.service
    batch = seed_partially_applicable_batch(service.database)

    result = service.confirm_proposal_batch(batch.id, _confirm_stored_batch(batch))

    assert result.batch.status == "partially_applied"
    assert [item.proposal.status for item in result.items] == ["accepted", "pending"]
    assert [item.error for item in result.items] == [None, "TASK_TARGET_NOT_FOUND"]


def test_delete_conversation_removes_only_owned_checkpoint_threads(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [create_plan_payload("A"), create_plan_payload("B")]
    first_conversation = service.create_conversation()
    second_conversation = service.create_conversation()
    first = service.send_message(
        first_conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-delete-owned", content="新建 A", attachments=[]
        ),
    )
    second = service.send_message(
        second_conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-keep-other", content="新建 B", attachments=[]
        ),
    )
    first_batch_id = first.proposal_batches[0].id
    second_batch_id = second.proposal_batches[0].id
    owned_threads = ["turn:turn-delete-owned", f"proposal:{first_batch_id}"]
    other_threads = ["turn:turn-keep-other", f"proposal:{second_batch_id}"]
    assert all(service._checkpoint_store.has_thread(item) for item in owned_threads)
    assert all(service._checkpoint_store.has_thread(item) for item in other_threads)

    service.delete_conversation(first_conversation.id)

    assert not any(service._checkpoint_store.has_thread(item) for item in owned_threads)
    assert all(service._checkpoint_store.has_thread(item) for item in other_threads)


def test_unexpected_turn_failure_never_leaves_active_row(
    assistant: AssistantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = assistant.service
    _configure(service)
    conversation = service.create_conversation()

    def fail_run(_workflow: AssistantTurnWorkflow, _turn_id: str) -> object:
        raise RuntimeError("unexpected graph failure")

    monkeypatch.setattr(AssistantTurnWorkflow, "run", fail_run)

    with pytest.raises(RuntimeError, match="unexpected graph failure"):
        service.send_message(
            conversation.id,
            SendAssistantMessageCommand(
                turnId="turn-unexpected", content="新建 A", attachments=[]
            ),
        )

    with service.database.transaction() as connection:
        stored = ConversationsRepository().get_turn(connection, "turn-unexpected")
        message = ConversationsRepository().get_message(
            connection, stored.assistant_message_id
        )
    assert stored.status == "failed"
    assert message.status == "failed"


def test_ark_client_capability_state_is_cached_across_turns(tmp_path: Path) -> None:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    _initialize_app_settings(database)
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    clients: list[CapabilityCachingArk] = []

    def factory(_settings: object) -> CapabilityCachingArk:
        client = CapabilityCachingArk()
        clients.append(client)
        return client

    service = AssistantService(database, settings, ark_factory=factory)
    _configure(service)
    conversation = service.create_conversation()
    service.send_message(
        conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-capability-a", content="新建 A", attachments=[]
        ),
    )
    service.send_message(
        conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-capability-b", content="新建 B", attachments=[]
        ),
    )
    service.close()

    assert len(clients) == 1
    assert clients[0].thinking_attempts == ["enabled", "disabled", "disabled"]


def test_audio_message_is_transcribed_into_attachment(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [query_plan_payload()]
    fake_ark.chat_results = [ArkChatResult(content="已记录")]
    fake_ark.transcription = "明天买菜"
    conversation = service.create_conversation()
    attachment = service.save_upload("voice.wav", b"RIFF....")

    turn = service.send_message(
        conversation.id,
        SendAssistantMessageCommand(
            turnId="turn-audio-1", content="", attachments=[attachment]
        ),
    )

    detail = service.get_conversation_detail(conversation.id)
    user_message = detail.messages[0]
    assert turn.message.status == "done"
    assert user_message.attachments[0].extracted_text == "明天买菜"


def test_upload_validation(assistant: AssistantFixture) -> None:
    service = assistant.service
    saved = service.save_upload("截图.png", b"\x89PNG")
    assert saved.kind == "image"
    assert saved.file_id.endswith(".png")

    with pytest.raises(UnsupportedFileTypeError):
        service.save_upload("evil.exe", b"MZ")
    with pytest.raises(UploadTooLargeError):
        service.save_upload("big.png", b"x" * (10 * 1024 * 1024 + 1))


def test_transcribe_endpoint_flow(assistant: AssistantFixture) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.transcription = "识别文字"
    attachment = service.save_upload("voice.mp3", b"ID3....")

    assert service.transcribe(TranscribeCommand(fileId=attachment.file_id)) == "识别文字"


def test_settings_view_masks_api_key(assistant: AssistantFixture) -> None:
    service = assistant.service
    empty = service.get_settings_view()
    assert empty.has_api_key is False

    _configure(service)
    view = service.get_settings_view()

    assert view.has_api_key is True
    assert not hasattr(view, "api_key")


def test_settings_change_invalidates_cached_ark_client(tmp_path: Path) -> None:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    _initialize_app_settings(database)
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    created: list[FakeArk] = []

    def factory(_settings: object) -> FakeArk:
        client = FakeArk(transcription="缓存测试")
        created.append(client)
        return client

    service = AssistantService(database, settings, ark_factory=factory)
    _configure(service)
    attachment = service.save_upload("voice.mp3", b"ID3....")
    service.transcribe(TranscribeCommand(fileId=attachment.file_id))
    service.patch_settings(AssistantSettingsPatchCommand(chatModel="new-model"))
    service.transcribe(TranscribeCommand(fileId=attachment.file_id))
    service.close()

    assert len(created) == 2


def test_path_traversal_file_id_rejected(assistant: AssistantFixture) -> None:
    service = assistant.service
    _configure(service)
    conversation = service.create_conversation()

    evil_attachment = AssistantAttachment(
        fileId="../evil.txt",
        kind="document",
        name="evil.txt",
        mime="text/plain",
    )
    with pytest.raises(UploadNotFoundError):
        service.send_message(
            conversation.id,
            SendAssistantMessageCommand(
                turnId="turn-evil-1", content="", attachments=[evil_attachment]
            ),
        )

    with pytest.raises(UploadNotFoundError):
        service.transcribe(TranscribeCommand(fileId="../evil.mp3"))
