# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


@pytest.fixture
def database(tmp_path: Path) -> Database:
    migrations_dir = Path(__file__).parents[1] / "migrations"
    database = Database(tmp_path / "todo.sqlite3", migrations_dir)
    database.initialize()
    return database


@pytest.fixture
def client(database: Database) -> Iterator[TestClient]:
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    with TestClient(create_app(settings=settings, database=database)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def create_task(
    client: TestClient,
    auth_headers: dict[str, str],
    text: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"text": text, "priority": "medium"},
    )
    assert response.status_code == 201
    result: dict[str, object] = response.json()["task"]
    return result


def test_task_routes_require_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"text": "Task", "priority": "medium"},
    )

    assert response.status_code == 401


def test_create_task_returns_server_fields_and_lists_newest_first(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = create_task(client, auth_headers, "First")
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "text": "Second",
            "priority": "high",
            "category": "work",
            "time": {"start": "2026-07-12T09:00", "end": "2026-07-12T10:00"},
            "notes": "Details",
        },
    )

    assert response.status_code == 201
    second = response.json()["task"]
    assert second == {
        "id": second["id"],
        "text": "Second",
        "completed": False,
        "priority": "high",
        "createdAt": second["createdAt"],
        "time": {"start": "2026-07-12T09:00", "end": "2026-07-12T10:00"},
        "category": "work",
        "notes": "Details",
    }
    assert len(second["id"]) == 32
    assert isinstance(second["createdAt"], int)

    listed = client.post("/api/v1/bootstrap", headers=auth_headers, json={})
    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()["tasks"]] == [second["id"], first["id"]]


def test_patch_task_edits_only_supplied_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    task = create_task(client, auth_headers, "Before")

    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers,
        json={
            "text": "After",
            "priority": "low",
            "category": "study",
            "time": {"start": "2026-07-13T11:00"},
            "notes": "Changed",
        },
    )

    assert response.status_code == 200
    assert response.json()["task"] == {
        **task,
        "text": "After",
        "priority": "low",
        "category": "study",
        "time": {"start": "2026-07-13T11:00"},
        "notes": "Changed",
    }


def test_patch_can_clear_optional_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "text": "Task",
            "priority": "medium",
            "time": {"start": "2026-07-12T09:00"},
            "notes": "Details",
        },
    )
    task = response.json()["task"]

    patched = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers,
        json={"time": None, "notes": None},
    )

    assert patched.status_code == 200
    assert "time" not in patched.json()["task"]
    assert "notes" not in patched.json()["task"]


def test_delete_task_removes_it(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    task = create_task(client, auth_headers, "Delete me")

    response = client.delete(f"/api/v1/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 204
    listed = client.post("/api/v1/bootstrap", headers=auth_headers, json={})
    assert listed.json()["tasks"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "", "priority": "medium"},
        {"text": "x" * 10_001, "priority": "medium"},
        {"text": "Task", "priority": "urgent"},
        {"text": "Task", "priority": "medium", "category": "unknown"},
        {"text": "Task", "priority": "medium", "notes": "x" * 10_001},
        {"text": "Task", "priority": "medium", "unknown": True},
    ],
)
def test_create_rejects_invalid_text_enums_notes_and_extra_fields(
    client: TestClient,
    auth_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    response = client.post("/api/v1/tasks", headers=auth_headers, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_mutating_missing_task_returns_stable_error(
    client: TestClient,
    auth_headers: dict[str, str],
    method: str,
) -> None:
    if method == "patch":
        response = client.patch(
            "/api/v1/tasks/missing",
            headers=auth_headers,
            json={"text": "Updated"},
        )
    else:
        response = client.delete("/api/v1/tasks/missing", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "TASK_NOT_FOUND", "message": "Task not found"}
    }


def test_replace_order_returns_and_persists_exact_order(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = create_task(client, auth_headers, "First")
    second = create_task(client, auth_headers, "Second")

    response = client.put(
        "/api/v1/tasks/order",
        headers=auth_headers,
        json={"taskIds": [first["id"], second["id"]]},
    )

    assert response.status_code == 200
    assert [task["id"] for task in response.json()["tasks"]] == [first["id"], second["id"]]
    listed = client.post("/api/v1/bootstrap", headers=auth_headers, json={})
    assert [task["id"] for task in listed.json()["tasks"]] == [first["id"], second["id"]]


@pytest.mark.parametrize("kind", ["duplicate", "missing", "unknown"])
def test_invalid_order_is_atomic(
    client: TestClient,
    auth_headers: dict[str, str],
    kind: str,
) -> None:
    first = create_task(client, auth_headers, "First")
    second = create_task(client, auth_headers, "Second")
    original_order = [second["id"], first["id"]]
    invalid_ids = {
        "duplicate": [second["id"], second["id"]],
        "missing": [second["id"]],
        "unknown": [second["id"], "unknown"],
    }[kind]

    response = client.put(
        "/api/v1/tasks/order",
        headers=auth_headers,
        json={"taskIds": invalid_ids},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "INVALID_TASK_ORDER", "message": "Invalid task order"}
    }
    listed = client.post("/api/v1/bootstrap", headers=auth_headers, json={})
    assert [task["id"] for task in listed.json()["tasks"]] == original_order
