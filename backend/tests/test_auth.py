from pathlib import Path

import pytest
from fastapi import HTTPException, status

from todo_backend.auth import require_token
from todo_backend.config import Settings


def test_settings_require_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("TODO_DATABASE_PATH", "TODO_BACKEND_PORT", "TODO_BACKEND_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="TODO_DATABASE_PATH"):
        Settings.from_env()


def test_settings_load_environment_and_force_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODO_DATABASE_PATH", "/tmp/todo.sqlite3")
    monkeypatch.setenv("TODO_BACKEND_PORT", "43123")
    monkeypatch.setenv("TODO_BACKEND_TOKEN", "secret-token")

    settings = Settings.from_env()

    assert settings.database_path == Path("/tmp/todo.sqlite3")
    assert settings.host == "127.0.0.1"
    assert settings.port == 43123
    assert settings.token == "secret-token"
    with pytest.raises((AttributeError, TypeError)):
        settings.port = 8000  # type: ignore[misc]


def test_settings_enable_parent_stdin_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODO_DATABASE_PATH", "/tmp/todo.sqlite3")
    monkeypatch.setenv("TODO_BACKEND_PORT", "43123")
    monkeypatch.setenv("TODO_BACKEND_TOKEN", "secret-token")
    monkeypatch.setenv("TODO_PARENT_STDIN_WATCH", "1")

    assert Settings.from_env().watch_parent_stdin is True


def test_settings_leave_parent_stdin_watch_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TODO_DATABASE_PATH", "/tmp/todo.sqlite3")
    monkeypatch.setenv("TODO_BACKEND_PORT", "43123")
    monkeypatch.setenv("TODO_BACKEND_TOKEN", "secret-token")
    monkeypatch.delenv("TODO_PARENT_STDIN_WATCH", raising=False)

    assert Settings.from_env().watch_parent_stdin is False


@pytest.mark.parametrize("authorization", [None, "", "Basic secret-token", "Bearer wrong-token"])
def test_require_token_rejects_missing_or_wrong_bearer_token(
    authorization: str | None,
) -> None:
    settings = Settings(Path("todo.sqlite3"), "127.0.0.1", 8000, "secret-token")

    with pytest.raises(HTTPException) as raised:
        require_token(settings, authorization)

    assert raised.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_require_token_accepts_matching_bearer_token() -> None:
    settings = Settings(Path("todo.sqlite3"), "127.0.0.1", 8000, "secret-token")

    assert require_token(settings, "Bearer secret-token") is None
