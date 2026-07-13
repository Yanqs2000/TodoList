# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


def test_sqlite_failure_returns_sanitized_stable_error(tmp_path: Path) -> None:
    database = Database(tmp_path / "private.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "secret-token")
    app = create_app(settings=settings, database=database)
    with database.connect() as connection:
        connection.execute("DROP TABLE tasks")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/bootstrap",
            headers={"Authorization": "Bearer secret-token"},
            json={"preferredTheme": "workspace-light"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database unavailable",
        }
    }
    assert "private.sqlite3" not in response.text
    assert "secret-token" not in response.text
    assert "tasks" not in response.text


def test_authentication_error_uses_stable_envelope(tmp_path: Path) -> None:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "secret-token")

    with TestClient(create_app(settings=settings, database=database)) as client:
        response = client.post("/api/v1/bootstrap", json={})

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"}
    }


def test_newer_database_version_returns_sanitized_service_error(tmp_path: Path) -> None:
    database = Database(tmp_path / "future.sqlite3", Path(__file__).parents[1] / "migrations")
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 2")
    settings = Settings(database.path, "127.0.0.1", 8000, "secret-token")

    app = create_app(settings=settings, database=database)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/bootstrap",
            headers={"Authorization": "Bearer secret-token"},
            json={"preferredTheme": "workspace-light"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database unavailable",
        }
    }
    assert "future.sqlite3" not in response.text
    assert "version" not in response.text.lower()


def test_unexpected_failure_returns_sanitized_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "secret-token")
    app = create_app(settings=settings, database=database)

    def fail_with_private_text(*_args: object) -> object:
        raise RuntimeError("private task notes")

    monkeypatch.setattr(
        "todo_backend.repositories.tasks.TaskRepository.list_all",
        fail_with_private_text,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/bootstrap",
            headers={"Authorization": "Bearer secret-token"},
            json={"preferredTheme": "workspace-light"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Internal error"}
    }
    assert "private task notes" not in response.text
    assert "secret-token" not in response.text
