# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportCallIssue=false

from pathlib import Path

import pytest

from todo_backend.database import Database
from todo_backend.models import AssistantSettingsPatchCommand
from todo_backend.repositories.assistant_settings import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_AUDIO_MODEL,
    DEFAULT_CHAT_MODEL,
    AssistantSettingsRepository,
)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


def test_migration_003_creates_assistant_tables(database: Database) -> None:
    connection = database.connect()
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(app_settings)").fetchall()
        }
    finally:
        connection.close()
    assert version == 4
    assert {
        "assistant_conversations",
        "assistant_messages",
        "assistant_proposals",
    } <= tables
    assert {
        "assistant_api_key",
        "assistant_chat_model",
        "assistant_audio_model",
        "assistant_base_url",
    } <= columns


def test_assistant_settings_defaults_and_patch(database: Database) -> None:
    repository = AssistantSettingsRepository()
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_settings (id, theme, muted, shortcut)"
            " VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT')"
        )
        defaults = repository.get(connection)
        assert defaults.api_key == ""
        assert defaults.chat_model == DEFAULT_CHAT_MODEL
        assert defaults.audio_model == DEFAULT_AUDIO_MODEL
        assert defaults.base_url == DEFAULT_ARK_BASE_URL

        updated = repository.patch(
            connection,
            AssistantSettingsPatchCommand(apiKey="sk-test-123", chatModel="custom-model"),
        )
        assert updated.api_key == "sk-test-123"
        assert updated.chat_model == "custom-model"
        assert updated.audio_model == DEFAULT_AUDIO_MODEL

        cleared = repository.patch(
            connection, AssistantSettingsPatchCommand(apiKey="")
        )
        assert cleared.api_key == ""
        assert cleared.chat_model == "custom-model"


def test_assistant_settings_patch_rejects_null_and_unknown() -> None:
    with pytest.raises(Exception):
        AssistantSettingsPatchCommand(apiKey=None)
    with pytest.raises(Exception):
        AssistantSettingsPatchCommand(unknown="x")
