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


def test_first_bootstrap_initializes_singletons_and_returns_full_snapshot(
    client: TestClient,
    database: Database,
) -> None:
    response = client.post(
        "/api/v1/bootstrap",
        headers={"Authorization": "Bearer test-token"},
        json={"preferredTheme": "workspace-dark"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "tasks": [],
        "settings": {
            "theme": "workspace-dark",
            "muted": False,
            "shortcut": "Cmd+Alt+KeyT",
            "language": "zh-CN",
        },
        "achievementState": {
            "unlocked": [],
            "streakDays": 0,
            "lastActiveDate": "",
            "todayCompleted": 0,
            "todayDate": "",
        },
    }
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM achievement_state").fetchone()[0] == 1


def test_later_bootstrap_ignores_a_different_preferred_theme(client: TestClient) -> None:
    headers = {"Authorization": "Bearer test-token"}
    first = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-dark"},
    )
    second = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-light"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["settings"]["theme"] == "workspace-dark"
