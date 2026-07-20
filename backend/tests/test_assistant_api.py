# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.services.assistant import AssistantService

_HEADERS = {"Authorization": "Bearer test-token"}


class _FakeArk:
    def chat(self, messages, tools=None):
        return ArkChatResult(content="你好！", tool_calls=[])

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        return "转写文本"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    service = AssistantService(database, settings, ark_factory=lambda _s: _FakeArk())
    with TestClient(
        create_app(settings=settings, database=database, assistant_service=service)
    ) as test_client:
        test_client.post(
            "/api/v1/bootstrap", headers=_HEADERS, json={"preferredTheme": "workspace-light"}
        )
        yield test_client


def _configure_key(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/settings", headers=_HEADERS, json={"apiKey": "sk-test"}
    )
    assert response.status_code == 200


def test_settings_roundtrip_masks_key(client: TestClient) -> None:
    empty = client.get("/api/v1/assistant/settings", headers=_HEADERS)
    assert empty.status_code == 200
    assert empty.json()["hasApiKey"] is False

    _configure_key(client)
    view = client.get("/api/v1/assistant/settings", headers=_HEADERS)

    assert view.json()["hasApiKey"] is True
    assert "apiKey" not in view.json()
    assert view.json()["chatModel"] == "doubao-seed-2-1-pro-260628"


def test_send_message_without_key_returns_409(client: TestClient) -> None:
    created = client.post("/api/v1/assistant/conversations", headers=_HEADERS)
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"content": "你好", "attachments": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSISTANT_NOT_CONFIGURED"


def test_full_text_turn_over_http(client: TestClient) -> None:
    _configure_key(client)
    created = client.post("/api/v1/assistant/conversations", headers=_HEADERS)
    conversation_id = created.json()["id"]

    turn = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"content": "你好", "attachments": []},
    )
    assert turn.status_code == 200
    assert turn.json()["message"]["content"] == "你好！"

    detail = client.get(
        f"/api/v1/assistant/conversations/{conversation_id}", headers=_HEADERS
    )
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]

    listed = client.get("/api/v1/assistant/conversations", headers=_HEADERS)
    assert listed.json()["conversations"][0]["title"] == "你好"


def test_upload_and_transcribe_over_http(client: TestClient) -> None:
    _configure_key(client)
    upload = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("voice.wav", b"RIFF fake", "audio/wav")},
    )
    assert upload.status_code == 201
    assert upload.json()["kind"] == "audio"

    transcribed = client.post(
        "/api/v1/assistant/transcribe",
        headers=_HEADERS,
        json={"fileId": upload.json()["fileId"]},
    )
    assert transcribed.status_code == 200
    assert transcribed.json()["text"] == "转写文本"


def test_upload_rejects_bad_type_and_oversize(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 415

    big = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("big.wav", b"x" * (25 * 1024 * 1024 + 1), "audio/wav")},
    )
    assert big.status_code == 413


def test_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations/nope", headers=_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_assistant_routes_require_token(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations")
    assert response.status_code == 401
