# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import ProposalCardFields
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchesRepository,
    ProposalDraft,
)
from todo_backend.services.assistant import AssistantService

_HEADERS = {"Authorization": "Bearer test-token"}
_CLIENT_SERVICES: dict[int, AssistantService] = {}


def create_plan_payload(text: str = "原标题") -> dict[str, Any]:
    return {
        "kind": "mutations",
        "evidence": "用户明确要求新建",
        "items": [{"action": "create", "fields": {"text": text}}],
    }


class FakeArk:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def plan(
        self, messages: list[dict[str, Any]], submit_plan_tool: dict[str, Any]
    ) -> dict[str, Any]:
        del messages, submit_plan_tool
        self.calls.append("plan")
        return create_plan_payload()

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: str = "disabled",
    ) -> ArkChatResult:
        del tools, tool_choice, thinking
        system = messages[0]["content"] if messages else ""
        if "Output one AnalysisResult" in system or (
            tools and any(t.get("function", {}).get("name") == "submit_analysis" for t in tools)
        ):
            self.calls.append("analyze")
            from todo_backend.agent.ark_client import ArkToolCall
            return ArkChatResult(
                content="",
                tool_calls=[
                    ArkToolCall(
                        id="call_analyze",
                        name="submit_analysis",
                        arguments={"intent": "mutations", "reasoning": "default for backward compatibility"},
                    )
                ],
            )
        # Auto-respond to reflect calls: model approves proposals
        if tools is None and tool_choice is None and system and "review" in system.lower():
            self.calls.append("reflect")
            return ArkChatResult(content='{"ok": true}')
        self.calls.append("chat")
        return ArkChatResult(content="你好！")

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        del audio_base64, audio_format
        self.calls.append("transcribe")
        return "转写文本"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    fake_ark = FakeArk()
    service = AssistantService(
        database, settings, ark_factory=lambda _settings: fake_ark
    )
    with TestClient(
        create_app(settings=settings, database=database, assistant_service=service)
    ) as test_client:
        _CLIENT_SERVICES[id(test_client)] = service
        try:
            test_client.post(
                "/api/v1/bootstrap",
                headers=_HEADERS,
                json={"preferredTheme": "workspace-light"},
            )
            yield test_client
        finally:
            _CLIENT_SERVICES.pop(id(test_client), None)


def _service(client: TestClient) -> AssistantService:
    return _CLIENT_SERVICES[id(client)]


def _configure_key(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/settings", headers=_HEADERS, json={"apiKey": "sk-test"}
    )
    assert response.status_code == 200


def configured_conversation(client: TestClient) -> str:
    _configure_key(client)
    created = client.post("/api/v1/assistant/conversations", headers=_HEADERS)
    assert created.status_code == 201
    return created.json()["id"]


def create_batch_over_http(client: TestClient) -> dict[str, Any]:
    conversation_id = configured_conversation(client)
    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={
            "turnId": f"turn-{uuid.uuid4().hex}",
            "content": "新建一个任务",
            "attachments": [],
        },
    )
    assert response.status_code == 200
    return response.json()["proposalBatches"][0]


def _card(text: str) -> ProposalCardFields:
    return ProposalCardFields(
        text=text,
        priority="medium",
        category="other",
        time_start=None,
        time_end=None,
        notes=None,
    )


def seed_batch(
    client: TestClient,
    *,
    batch_id: str | None = None,
    item_count: int = 1,
    include_missing_delete: bool = False,
) -> dict[str, Any]:
    service = _service(client)
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    resolved_batch_id = batch_id or f"batch-{uuid.uuid4().hex}"
    proposals = [
        ProposalDraft(
            id=f"{resolved_batch_id}-a{index}",
            action="create",
            target_task_id=None,
            before_snapshot=None,
            payload=_card(f"任务 {index + 1}"),
        )
        for index in range(item_count)
    ]
    if include_missing_delete:
        proposals.append(
            ProposalDraft(
                id=f"{resolved_batch_id}-z-missing",
                action="delete",
                target_task_id="missing-task",
                before_snapshot=None,
                payload=_card("已不存在"),
            )
        )
    with service.database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "待确认", []
        )
        batch = batches.insert_batches(
            connection,
            conversation_id=conversation.id,
            message_id=message.id,
            drafts=[
                BatchDraft(
                    id=resolved_batch_id,
                    supersedes_batch_id=None,
                    proposals=proposals,
                )
            ],
        )[0]
    return batch.model_dump(mode="json", by_alias=True)


def _confirmation_payload(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": [
            {
                "proposalId": proposal["id"],
                "payload": proposal["payload"],
            }
            for proposal in batch["proposals"]
        ]
    }


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
        json={"turnId": "turn-no-key", "content": "你好", "attachments": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSISTANT_NOT_CONFIGURED"


def test_message_request_requires_stable_turn_id(client: TestClient) -> None:
    conversation_id = configured_conversation(client)

    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"content": "新建买菜任务", "attachments": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_message_request_echoes_stable_turn_id(client: TestClient) -> None:
    conversation_id = configured_conversation(client)
    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={
            "turnId": "turn-http-1",
            "content": "新建买菜任务",
            "attachments": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["message"]["turnId"] == "turn-http-1"
    assert "proposalBatches" in response.json()
    assert "proposals" not in response.json()


def test_conversation_detail_keeps_explicit_null_wire_fields(
    client: TestClient,
) -> None:
    conversation_id = configured_conversation(client)
    created = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={
            "turnId": "turn-null-wire",
            "content": "新建任务",
            "attachments": [],
        },
    )
    assert created.status_code == 200

    detail = client.get(
        f"/api/v1/assistant/conversations/{conversation_id}", headers=_HEADERS
    ).json()
    batch = detail["proposalBatches"][0]
    proposal = batch["proposals"][0]
    assert batch["supersedesBatchId"] is None
    assert batch["resolvedAt"] is None
    assert proposal["targetTaskId"] is None
    assert proposal["beforeSnapshot"] is None
    assert proposal["resultTaskId"] is None
    assert proposal["lastError"] is None


def test_turn_payload_mismatch_returns_conflict(client: TestClient) -> None:
    conversation_id = configured_conversation(client)
    endpoint = f"/api/v1/assistant/conversations/{conversation_id}/messages"
    first = client.post(
        endpoint,
        headers=_HEADERS,
        json={"turnId": "turn-http-fixed", "content": "新建 A", "attachments": []},
    )
    assert first.status_code == 200

    response = client.post(
        endpoint,
        headers=_HEADERS,
        json={"turnId": "turn-http-fixed", "content": "新建 B", "attachments": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSISTANT_TURN_PAYLOAD_MISMATCH"


def test_active_turn_conflict_returns_stable_error(client: TestClient) -> None:
    conversation_id = configured_conversation(client)
    conversations = ConversationsRepository()
    with _service(client).database.transaction() as connection:
        user = conversations.insert_message(
            connection,
            conversation_id,
            "user",
            "进行中",
            [],
            turn_id="turn-active-existing",
        )
        assistant = conversations.insert_message(
            connection,
            conversation_id,
            "assistant",
            "",
            [],
            "pending",
            turn_id="turn-active-existing",
        )
        conversations.insert_turn(
            connection,
            "turn-active-existing",
            conversation_id,
            user.id,
            assistant.id,
            "fingerprint",
        )

    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"turnId": "turn-active-new", "content": "新建 B", "attachments": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSISTANT_TURN_ACTIVE"


def test_confirm_batch_accepts_edited_fields_and_returns_item_results(
    client: TestClient,
) -> None:
    batch = create_batch_over_http(client)
    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json={
            "items": [
                {
                    "proposalId": batch["proposals"][0]["id"],
                    "payload": {
                        "text": "卡片编辑后",
                        "priority": "high",
                        "category": "work",
                        "time_start": None,
                        "time_end": None,
                        "notes": None,
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["batch"]["status"] == "accepted"
    assert response.json()["items"][0]["task"]["text"] == "卡片编辑后"
    assert response.json()["items"][0]["error"] is None


def test_repeated_batch_confirmation_is_idempotent(client: TestClient) -> None:
    batch = create_batch_over_http(client)
    payload = _confirmation_payload(batch)
    endpoint = f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm"

    first = client.post(endpoint, headers=_HEADERS, json=payload)
    second = client.post(endpoint, headers=_HEADERS, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_reject_batch_returns_explicit_null_item_result(client: TestClient) -> None:
    batch = create_batch_over_http(client)

    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/reject",
        headers=_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["batch"]["status"] == "rejected"
    assert response.json()["items"][0]["task"] is None
    assert response.json()["items"][0]["error"] is None


@pytest.mark.parametrize("operation", ["confirm", "reject"])
def test_missing_batch_returns_404(client: TestClient, operation: str) -> None:
    kwargs = (
        {"json": {"items": [{"proposalId": "missing", "payload": None}]}}
        if operation == "confirm"
        else {}
    )
    response = client.post(
        f"/api/v1/assistant/proposal-batches/missing/{operation}",
        headers=_HEADERS,
        **kwargs,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPOSAL_BATCH_NOT_FOUND"


def test_invalid_confirmation_payload_returns_stable_422(client: TestClient) -> None:
    batch = create_batch_over_http(client)
    item = {
        "proposalId": batch["proposals"][0]["id"],
        "payload": batch["proposals"][0]["payload"],
    }

    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json={"items": [item, item]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CONFIRMATION_PAYLOAD"


@pytest.mark.parametrize(
    ("location", "field_name", "value"),
    [
        ("item", "action", "delete"),
        ("item", "targetTaskId", "attacker-selected-task"),
        ("item", "beforeSnapshot", {"text": "forged snapshot"}),
        ("payload", "completed", True),
    ],
)
def test_confirmation_rejects_server_owned_and_unsupported_fields(
    client: TestClient,
    location: str,
    field_name: str,
    value: Any,
) -> None:
    batch = seed_batch(client)
    command = _confirmation_payload(batch)
    target: dict[str, Any] = (
        command["items"][0]
        if location == "item"
        else command["items"][0]["payload"]
    )
    target[field_name] = value

    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json=command,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    with _service(client).database.transaction() as connection:
        stored = ProposalBatchesRepository().get_batch(connection, batch["id"])
        task_row = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
    assert task_row is not None
    assert int(task_row[0]) == 0
    assert stored.status == "pending"
    assert stored.proposals[0].status == "pending"


def test_partial_application_is_http_success_with_item_error(
    client: TestClient,
) -> None:
    batch = seed_batch(client, include_missing_delete=True)

    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json=_confirmation_payload(batch),
    )

    assert response.status_code == 200
    assert response.json()["batch"]["status"] == "partially_applied"
    assert [item["error"] for item in response.json()["items"]] == [
        None,
        "TASK_TARGET_NOT_FOUND",
    ]


def test_superseded_batch_confirm_returns_conflict(client: TestClient) -> None:
    batch = seed_batch(client, batch_id="superseded")
    with _service(client).database.transaction() as connection:
        ProposalBatchesRepository().supersede(connection, batch["id"], 1)

    response = client.post(
        "/api/v1/assistant/proposal-batches/superseded/confirm",
        headers=_HEADERS,
        json={
            "items": [
                {"proposalId": batch["proposals"][0]["id"], "payload": None}
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_BATCH_NOT_CONFIRMABLE"


@pytest.mark.parametrize("operation", ["accept", "reject"])
def test_legacy_single_proposal_routes_require_single_item_batch(
    client: TestClient, operation: str
) -> None:
    batch = seed_batch(client, item_count=2)

    response = client.post(
        f"/api/v1/assistant/proposals/{batch['proposals'][0]['id']}/{operation}",
        headers=_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_BATCH_REQUIRED"


def test_legacy_single_proposal_accept_is_idempotent(client: TestClient) -> None:
    batch = seed_batch(client)
    endpoint = f"/api/v1/assistant/proposals/{batch['proposals'][0]['id']}/accept"

    first = client.post(endpoint, headers=_HEADERS)
    second = client.post(endpoint, headers=_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_legacy_missing_proposal_keeps_compatibility_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assistant/proposals/missing/accept", headers=_HEADERS
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


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
        files={
            "file": ("big.wav", b"x" * (25 * 1024 * 1024 + 1), "audio/wav")
        },
    )
    assert big.status_code == 413


def test_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations/nope", headers=_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_assistant_routes_require_token(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations")
    assert response.status_code == 401


def test_app_lifespan_closes_assistant_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    service = AssistantService(
        database, settings, ark_factory=lambda _settings: FakeArk()
    )
    closed: list[bool] = []

    def close() -> None:
        closed.append(True)
        service._checkpoint_store.close()

    monkeypatch.setattr(service, "close", close)
    with TestClient(
        create_app(settings=settings, database=database, assistant_service=service)
    ):
        pass

    assert closed == [True]
