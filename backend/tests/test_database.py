import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from todo_backend import models
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

    assert version == 5
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_migration_005_adds_turns_batches_and_extended_proposals(
    database: Database,
) -> None:
    database.initialize()
    connection = database.connect()
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        proposal_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(assistant_proposals)")
        }
        message_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(assistant_messages)")
        }
        batch_indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(assistant_proposal_batches)")
        }
        message_index_columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA index_info(idx_assistant_batches_message)"
            )
        ]
    finally:
        connection.close()

    assert {"assistant_turns", "assistant_proposal_batches"} <= tables
    assert {
        "batch_id",
        "target_task_id",
        "before_snapshot",
        "result_task_id",
        "last_error",
    } <= proposal_columns
    assert "turn_id" in message_columns
    assert "idx_assistant_batches_message" in batch_indexes
    assert message_index_columns == ["message_id"]


def test_migration_005_wraps_legacy_proposals_without_changing_status(
    tmp_path: Path, migrations_dir: Path
) -> None:
    staged_migrations = tmp_path / "migrations"
    staged_migrations.mkdir()
    for version in range(1, 5):
        source = next(migrations_dir.glob(f"{version:03d}_*.sql"))
        shutil.copy2(source, staged_migrations / source.name)
    database_path = tmp_path / "legacy.sqlite3"
    legacy = Database(database_path, staged_migrations)
    legacy.initialize()
    with legacy.transaction() as connection:
        connection.execute(
            "INSERT INTO assistant_conversations VALUES ('c1', 'chat', 1, 1)"
        )
        connection.execute(
            "INSERT INTO assistant_messages"
            " (id, conversation_id, role, content, status, created_at)"
            " VALUES ('m1', 'c1', 'assistant', 'draft', 'done', 1)"
        )
        connection.execute(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, action, task_id, payload, status, created_at)"
            " VALUES ('p1', 'c1', 'm1', 'create', NULL, '{\"text\":\"买菜\"}',"
            " 'pending', 1)"
        )
        connection.execute(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, action, task_id, payload, status, created_at)"
            " VALUES ('p2', 'c1', 'm1', 'delete', 'missing-accepted',"
            " '{\"text\":\"已删除\"}', 'accepted', 2)"
        )
        connection.execute(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, action, task_id, payload, status, created_at)"
            " VALUES ('p3', 'c1', 'm1', 'delete', 'missing-pending',"
            " '{\"text\":\"待删除\"}', 'pending', 3)"
        )

    migration_005 = migrations_dir / "005_redesign_assistant_agent.sql"
    shutil.copy2(migration_005, staged_migrations / migration_005.name)
    legacy.initialize()

    with legacy.transaction() as connection:
        batch = connection.execute(
            "SELECT id, status FROM assistant_proposal_batches WHERE id = 'p1'"
        ).fetchone()
        proposal = connection.execute(
            "SELECT batch_id, status, payload FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone()
        missing_deletes = {
            row["id"]: dict(row)
            for row in connection.execute(
                "SELECT proposals.id, proposals.message_id, proposals.batch_id,"
                " proposals.action, proposals.target_task_id, proposals.before_snapshot,"
                " proposals.payload, proposals.result_task_id, proposals.status,"
                " proposals.last_error, proposals.created_at,"
                " batches.status AS batch_status"
                " FROM assistant_proposals AS proposals"
                " JOIN assistant_proposal_batches AS batches"
                " ON batches.id = proposals.batch_id"
                " WHERE proposals.id IN ('p2', 'p3')"
                " ORDER BY proposals.id"
            ).fetchall()
        }

    assert dict(batch) == {"id": "p1", "status": "pending"}
    assert proposal["batch_id"] == "p1"
    assert proposal["status"] == "pending"
    assert json.loads(proposal["payload"])["text"] == "买菜"
    assert missing_deletes["p2"] == {
        "id": "p2",
        "status": "accepted",
        "before_snapshot": None,
        "payload": None,
        "last_error": None,
        "message_id": "m1",
        "batch_id": "p2",
        "action": "delete",
        "target_task_id": "missing-accepted",
        "result_task_id": "missing-accepted",
        "created_at": 2,
        "batch_status": "accepted",
    }
    assert missing_deletes["p3"] == {
        "id": "p3",
        "status": "pending",
        "before_snapshot": None,
        "payload": None,
        "last_error": "TASK_TARGET_NOT_FOUND",
        "message_id": "m1",
        "batch_id": "p3",
        "action": "delete",
        "target_task_id": "missing-pending",
        "result_task_id": None,
        "created_at": 3,
        "batch_status": "pending",
    }

    detail = models.AssistantConversationDetail(
        conversation=models.AssistantConversationSummary(
            id="c1", title="chat", createdAt=1, updatedAt=1
        ),
        messages=[
            models.AssistantMessage(
                id="m1", role="assistant", content="draft", status="done", createdAt=1
            )
        ],
        proposalBatches=[
            models.AssistantProposalBatch(
                id=row["batch_id"],
                messageId=row["message_id"],
                status=row["batch_status"],
                proposals=[
                    models.AssistantProposal(
                        id=row["id"],
                        messageId=row["message_id"],
                        batchId=row["batch_id"],
                        action=row["action"],
                        targetTaskId=row["target_task_id"],
                        beforeSnapshot=row["before_snapshot"],
                        payload=row["payload"],
                        resultTaskId=row["result_task_id"],
                        status=row["status"],
                        lastError=row["last_error"],
                        createdAt=row["created_at"],
                    )
                ],
                createdAt=row["created_at"],
            )
            for row in missing_deletes.values()
        ],
    )
    assert [batch.status for batch in detail.proposal_batches] == ["accepted", "pending"]


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
        connection.execute("PRAGMA user_version = 6")

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
