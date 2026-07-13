# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    return TestClient(create_app(settings, database))


def test_health_reports_ready_for_matching_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token"])
def test_health_rejects_missing_or_wrong_token(
    client: TestClient,
    authorization: str | None,
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}

    response = client.get("/api/v1/health", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"}
    }
