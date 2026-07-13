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
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    database.initialize()
    return database


@pytest.fixture
def client(database: Database) -> Iterator[TestClient]:
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    with TestClient(create_app(settings=settings, database=database)) as test_client:
        yield test_client


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def create_scheduled_task(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "text": "Reminder",
            "priority": "medium",
            "time": {"start": "2026-07-13T09:00"},
        },
    )
    assert response.status_code == 201
    result: dict[str, object] = response.json()["task"]
    return result


def claim(
    client: TestClient,
    headers: dict[str, str],
    task_id: object,
    scheduled_start: str,
) -> object:
    response = client.post(
        "/api/v1/reminders/claim",
        headers=headers,
        json={"taskId": task_id, "scheduledStart": scheduled_start},
    )
    assert response.status_code == 200
    return response.json()["claimed"]


def test_reminder_claim_returns_true_then_false_atomically(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    task = create_scheduled_task(client, headers)

    assert claim(client, headers, task["id"], "2026-07-13T09:00") is True
    assert claim(client, headers, task["id"], "2026-07-13T09:00") is False


def test_rescheduling_prunes_old_claim_and_allows_new_claim(
    client: TestClient,
    headers: dict[str, str],
    database: Database,
) -> None:
    task = create_scheduled_task(client, headers)
    assert claim(client, headers, task["id"], "2026-07-13T09:00") is True

    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=headers,
        json={"time": {"start": "2026-07-13T10:00"}},
    )

    assert response.status_code == 200
    assert claim(client, headers, task["id"], "2026-07-13T10:00") is True
    with database.connect() as connection:
        starts = [
            row["scheduled_start"]
            for row in connection.execute(
                "SELECT scheduled_start FROM task_reminders WHERE task_id = ?",
                (task["id"],),
            )
        ]
    assert starts == ["2026-07-13T10:00"]


def test_deleting_task_cascades_reminder_claim(
    client: TestClient,
    headers: dict[str, str],
    database: Database,
) -> None:
    task = create_scheduled_task(client, headers)
    assert claim(client, headers, task["id"], "2026-07-13T09:00") is True

    response = client.delete(f"/api/v1/tasks/{task['id']}", headers=headers)

    assert response.status_code == 204
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM task_reminders").fetchone()[0]
    assert count == 0
