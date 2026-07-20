# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportConstantRedefinition=false, reportUnknownLambdaType=false

from pathlib import Path

import pytest

from todo_backend.agent.ark_client import ArkChatResult, ArkToolCall, ArkUnavailableError
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantSettingsPatchCommand,
    SendAssistantMessageCommand,
    TranscribeCommand,
)
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.assistant import (
    AssistantNotConfiguredError,
    AssistantService,
    ProposalAlreadyResolvedError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
)


class _FakeArk:
    def __init__(self, results=None, transcription="转写结果") -> None:
        self._results = list(results or [])
        self.transcription = transcription

    def chat(self, messages, tools=None):
        return self._results.pop(0)

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        return self.transcription


@pytest.fixture
def service(tmp_path: Path) -> AssistantService:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    database.initialize()
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    svc = AssistantService(database, settings, ark_factory=lambda _s: _FAKE_ARK)
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_settings (id, theme, muted, shortcut)"
            " VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT')"
        )
    return svc


_FAKE_ARK = _FakeArk()


def _configure(service: AssistantService) -> None:
    service.patch_settings(AssistantSettingsPatchCommand(apiKey="sk-test"))


def test_send_message_requires_api_key(service: AssistantService) -> None:
    conversation = service.create_conversation()
    with pytest.raises(AssistantNotConfiguredError):
        service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))


def test_send_message_persists_turn(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk([ArkChatResult(content="你好！我可以帮你规划。", tool_calls=[])])
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))

    detail = service.get_conversation_detail(conversation.id)
    assert turn.message.content == "你好！我可以帮你规划。"
    assert turn.message.status == "done"
    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert detail.conversation.title == "你好"


def test_proposal_accept_creates_real_task(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk([
        ArkChatResult(
            content="",
            tool_calls=[ArkToolCall(id="c1", name="propose_create_tasks", arguments={
                "items": [{"text": "明天下午三点开会", "priority": "high",
                           "time_start": "2026-07-21T15:00"}],
            })],
            raw_message={"role": "assistant", "tool_calls": []},
        ),
        ArkChatResult(content="已整理好提议", tool_calls=[]),
    ])
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="安排会议"))
    assert len(turn.proposals) == 1

    proposal, task = service.accept_proposal(turn.proposals[0].id)

    assert proposal.status == "accepted"
    assert task is not None and task.text == "明天下午三点开会"
    with service.database.transaction() as connection:
        assert len(TaskRepository().list_all(connection)) == 1

    with pytest.raises(ProposalAlreadyResolvedError):
        service.accept_proposal(turn.proposals[0].id)


def test_failed_ark_marks_message_failed(service: AssistantService) -> None:
    _configure(service)

    class _BrokenArk:
        def chat(self, messages, tools=None):
            raise ArkUnavailableError("down")

        def transcribe(self, a, b):
            raise ArkUnavailableError("down")

    global _FAKE_ARK
    _FAKE_ARK = _BrokenArk()
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))

    assert turn.message.status == "failed"
    assert turn.message.content == ""


def test_audio_message_is_transcribed_into_attachment(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk(
        [ArkChatResult(content="已记录", tool_calls=[])], transcription="明天买菜"
    )
    conversation = service.create_conversation()
    attachment = service.save_upload("voice.wav", b"RIFF....")

    turn = service.send_message(
        conversation.id,
        SendAssistantMessageCommand(content="", attachments=[attachment]),
    )

    detail = service.get_conversation_detail(conversation.id)
    user_message = detail.messages[0]
    assert turn.message.status == "done"
    assert user_message.attachments[0].extracted_text == "明天买菜"


def test_upload_validation(service: AssistantService) -> None:
    saved = service.save_upload("截图.png", b"\x89PNG")
    assert saved.kind == "image"
    assert saved.file_id.endswith(".png")

    with pytest.raises(UnsupportedFileTypeError):
        service.save_upload("evil.exe", b"MZ")
    with pytest.raises(UploadTooLargeError):
        service.save_upload("big.png", b"x" * (10 * 1024 * 1024 + 1))


def test_transcribe_endpoint_flow(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk(transcription="识别文字")
    attachment = service.save_upload("voice.mp3", b"ID3....")

    assert service.transcribe(TranscribeCommand(fileId=attachment.file_id)) == "识别文字"


def test_settings_view_masks_api_key(service: AssistantService) -> None:
    empty = service.get_settings_view()
    assert empty.has_api_key is False

    _configure(service)
    view = service.get_settings_view()

    assert view.has_api_key is True
    assert not hasattr(view, "api_key")
