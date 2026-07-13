# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import Iterator
from pathlib import Path
import sqlite3

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


def set_completion(
    client: TestClient,
    auth_headers: dict[str, str],
    task_id: object,
    completed: bool,
    local_date: str,
) -> dict[str, object]:
    response = client.put(
        f"/api/v1/tasks/{task_id}/completion",
        headers=auth_headers,
        json={"completed": completed, "localDate": local_date},
    )
    assert response.status_code == 200
    result: dict[str, object] = response.json()
    return result


def test_first_completion_persists_state_and_unlocks_first_task(
    client: TestClient,
    auth_headers: dict[str, str],
    database: Database,
) -> None:
    task = create_task(client, auth_headers, "First")

    payload = set_completion(client, auth_headers, task["id"], True, "2026-07-13")

    assert payload == {
        "task": {**task, "completed": True},
        "achievementState": {
            "unlocked": ["first-task"],
            "streakDays": 1,
            "lastActiveDate": "2026-07-13",
            "todayCompleted": 1,
            "todayDate": "2026-07-13",
        },
        "newlyUnlocked": ["first-task"],
    }
    with database.connect() as connection:
        state = connection.execute("SELECT * FROM achievement_state WHERE id = 1").fetchone()
        unlocks = connection.execute(
            "SELECT achievement_id FROM achievement_unlocks"
        ).fetchall()

    assert state is not None
    assert dict(state) == {
        "id": 1,
        "streak_days": 1,
        "last_active_date": "2026-07-13",
        "today_completed": 1,
        "today_date": "2026-07-13",
    }
    assert [row["achievement_id"] for row in unlocks] == ["first-task"]


def test_tenth_same_day_completion_unlocks_speed_demon(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    payload: dict[str, object] = {}
    for index in range(10):
        task = create_task(client, auth_headers, f"Task {index}")
        payload = set_completion(client, auth_headers, task["id"], True, "2026-07-13")

    assert payload["achievementState"] == {
        "unlocked": ["first-task", "speed-demon"],
        "streakDays": 1,
        "lastActiveDate": "2026-07-13",
        "todayCompleted": 10,
        "todayDate": "2026-07-13",
    }
    assert payload["newlyUnlocked"] == ["speed-demon"]


def test_completion_on_seven_consecutive_days_unlocks_streak(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    payload: dict[str, object] = {}
    for day in range(1, 8):
        task = create_task(client, auth_headers, f"Day {day}")
        payload = set_completion(
            client,
            auth_headers,
            task["id"],
            True,
            f"2026-07-{day:02d}",
        )

    assert payload["achievementState"] == {
        "unlocked": ["first-task", "streak-7"],
        "streakDays": 7,
        "lastActiveDate": "2026-07-07",
        "todayCompleted": 1,
        "todayDate": "2026-07-07",
    }
    assert payload["newlyUnlocked"] == ["streak-7"]


def test_uncomplete_does_not_decrement_achievement_progress(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    task = create_task(client, auth_headers, "Task")
    completed = set_completion(client, auth_headers, task["id"], True, "2026-07-13")

    uncompleted = set_completion(client, auth_headers, task["id"], False, "2026-07-13")

    assert uncompleted["task"] == {**task, "completed": False}
    assert uncompleted["achievementState"] == completed["achievementState"]
    assert uncompleted["newlyUnlocked"] == []


def test_repeated_completed_true_is_idempotent(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    task = create_task(client, auth_headers, "Task")
    first = set_completion(client, auth_headers, task["id"], True, "2026-07-13")

    repeated = set_completion(client, auth_headers, task["id"], True, "2026-07-14")

    assert repeated["task"] == first["task"]
    assert repeated["achievementState"] == first["achievementState"]
    assert repeated["newlyUnlocked"] == []


def test_missing_achievement_singleton_is_persisted_as_default_on_uncomplete(
    client: TestClient,
    auth_headers: dict[str, str],
    database: Database,
) -> None:
    task = create_task(client, auth_headers, "Already incomplete")

    payload = set_completion(client, auth_headers, task["id"], False, "2026-07-13")

    assert payload["achievementState"] == {
        "unlocked": [],
        "streakDays": 0,
        "lastActiveDate": "",
        "todayCompleted": 0,
        "todayDate": "",
    }
    assert payload["newlyUnlocked"] == []
    with database.connect() as connection:
        state_count = connection.execute(
            "SELECT COUNT(*) FROM achievement_state WHERE id = 1"
        ).fetchone()[0]
    assert state_count == 1


def test_achievement_write_failure_rolls_back_task_and_achievement_state(
    client: TestClient,
    auth_headers: dict[str, str],
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = create_task(client, auth_headers, "Atomic")

    def fail_achievement_write(
        _repository: object,
        _connection: sqlite3.Connection,
        _achievement_ids: object,
    ) -> None:
        raise RuntimeError("injected achievement write failure")

    monkeypatch.setattr(
        "todo_backend.repositories.achievements.AchievementRepository.add_unlocks",
        fail_achievement_write,
    )

    with pytest.raises(RuntimeError, match="injected achievement write failure"):
        client.put(
            f"/api/v1/tasks/{task['id']}/completion",
            headers=auth_headers,
            json={"completed": True, "localDate": "2026-07-13"},
        )

    with database.connect() as connection:
        completed = connection.execute(
            "SELECT completed FROM tasks WHERE id = ?", (task["id"],)
        ).fetchone()["completed"]
        state_count = connection.execute(
            "SELECT COUNT(*) FROM achievement_state"
        ).fetchone()[0]
        unlock_count = connection.execute(
            "SELECT COUNT(*) FROM achievement_unlocks"
        ).fetchone()[0]

    assert completed == 0
    assert state_count == 0
    assert unlock_count == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"completed": True},
        {"completed": True, "localDate": "2026-02-30"},
        {"completed": True, "localDate": "2026-7-13"},
        {"completed": True, "localDate": 20260713},
        {"completed": "true", "localDate": "2026-07-13"},
        {"completed": True, "localDate": "2026-07-13", "unknown": True},
    ],
)
def test_completion_rejects_invalid_payloads(
    client: TestClient,
    auth_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    task = create_task(client, auth_headers, "Task")

    response = client.put(
        f"/api/v1/tasks/{task['id']}/completion",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
