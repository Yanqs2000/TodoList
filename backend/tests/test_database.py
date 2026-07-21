import sqlite3
from pathlib import Path

import pytest

from todo_backend.database import Database
from todo_backend.errors import DatabaseVersionError


@pytest.fixture
def migrations_dir() -> Path:
    return Path(__file__).parents[1] / "migrations"


@pytest.fixture
def database(tmp_path: Path, migrations_dir: Path) -> Database:
    return Database(tmp_path / "todo.sqlite3", migrations_dir)


def test_connect_configures_sqlite(database: Database) -> None:
    with database.connect() as connection:
        row = connection.execute("SELECT 1 AS value").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert isinstance(row, sqlite3.Row)
    assert row["value"] == 1
    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert busy_timeout == 5000


def test_initialize_creates_schema(database: Database) -> None:
    database.initialize()
    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.execute(
            """
            INSERT INTO app_settings (id, theme, muted, shortcut)
            VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT')
            """
        )
        language = connection.execute(
            "SELECT language FROM app_settings WHERE id = 1"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert version == 4
    assert language == "zh-CN"
    assert {
        "tasks",
        "achievement_state",
        "achievement_unlocks",
        "task_reminders",
        "app_settings",
    } <= tables


def test_initialize_is_idempotent(database: Database) -> None:
    database.initialize()
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4


def test_initial_schema_enforces_checks_index_and_cascade(database: Database) -> None:
    database.initialize()

    with database.connect() as connection:
        for column, invalid_value in (
            ("completed", 2),
            ("priority", "urgent"),
            ("category", "unknown"),
        ):
            values: dict[str, object] = {
                "id": column,
                "text": "Task",
                "completed": 0,
                "priority": "medium",
                "created_at": 1,
                "category": "other",
                "position": 0,
            }
            values[column] = invalid_value
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO tasks
                        (id, text, completed, priority, created_at, category, position)
                    VALUES
                        (:id, :text, :completed, :priority, :created_at, :category, :position)
                    """,
                    values,
                )

        connection.execute(
            """
            INSERT INTO tasks
                (id, text, completed, priority, created_at, category, position)
            VALUES ('task-1', 'Task', 0, 'medium', 1, 'other', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO task_reminders (task_id, scheduled_start, claimed_at)
            VALUES ('task-1', '2026-07-12T10:00', 1)
            """
        )
        connection.execute("DELETE FROM tasks WHERE id = 'task-1'")
        reminders = connection.execute("SELECT COUNT(*) FROM task_reminders").fetchone()[0]
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list('tasks')")
        }

    assert reminders == 0
    assert "idx_tasks_position" in indexes


def test_transaction_commits_and_rolls_back(database: Database) -> None:
    database.initialize()

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO tasks
                (id, text, completed, priority, created_at, category, position)
            VALUES ('kept', 'Task', 0, 'medium', 1, 'other', 0)
            """
        )

    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                    (id, text, completed, priority, created_at, category, position)
                VALUES ('rolled-back', 'Task', 0, 'medium', 1, 'other', 1)
                """
            )
            raise RuntimeError("abort")

    with database.connect() as connection:
        task_ids = {row[0] for row in connection.execute("SELECT id FROM tasks")}

    assert task_ids == {"kept"}


def test_initialize_rejects_database_version_above_latest(
    database: Database,
) -> None:
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 5")

    with pytest.raises(DatabaseVersionError, match="newer"):
        database.initialize()


def test_failed_migration_rolls_back_schema_and_version(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_broken.sql").write_text(
        "CREATE TABLE partial (id INTEGER PRIMARY KEY);\nINVALID SQL;\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "todo.sqlite3", migrations_dir)

    with pytest.raises(sqlite3.OperationalError):
        database.initialize()

    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        partial_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'partial'"
        ).fetchone()

    assert version == 0
    assert partial_exists is None
