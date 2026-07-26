# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportCallIssue=false

from pathlib import Path

import pytest
from pydantic import ValidationError

from todo_backend.agent.planning import IntentPlan, PlannedMutation
from todo_backend.agent.proposals import ResolvedMutation, build_batch_drafts
from todo_backend.database import Database
from todo_backend import models
from todo_backend.models import AssistantSettingsPatchCommand
from todo_backend.repositories.assistant_settings import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_AUDIO_MODEL,
    DEFAULT_CHAT_MODEL,
    AssistantSettingsRepository,
)
from todo_backend.repositories.settings import SettingsRepository


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
    assert version == 6
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


def test_proposal_card_fields_require_all_six_wire_keys() -> None:
    assert set(models.ProposalCardFields.model_json_schema()["required"]) == {
        "text",
        "priority",
        "category",
        "time_start",
        "time_end",
        "notes",
    }

    card = models.ProposalCardFields(
        text="买菜",
        priority="medium",
        category="life",
        time_start=None,
        time_end=None,
        notes=None,
    )
    assert card.text == "买菜"

    with pytest.raises(ValidationError):
        models.ProposalCardFields(
            text="买菜",
            priority="medium",
            category="life",
            time_start=None,
            time_end=None,
        )


def test_planned_fields_remain_partial() -> None:
    planned = models.PlannedFields(time_end="2026-07-22T17:00")

    assert planned.time_end == "2026-07-22T17:00"


def test_planned_fields_blank_notes_normalized_to_none() -> None:
    assert models.PlannedFields.model_validate({"notes": ""}).notes is None
    assert models.PlannedFields.model_validate({"notes": "   "}).notes is None
    assert models.PlannedFields.model_validate({"notes": "abc"}).notes == "abc"


def test_create_draft_payload_uses_null_notes_for_blank_input() -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence="清空备注",
        items=[PlannedMutation(action="create", fields=models.PlannedFields(text="x", notes=""))],
    )

    drafts = build_batch_drafts("turn-1", plan, [ResolvedMutation()], superseded_batch=None)

    assert drafts[0].proposals[0].payload.notes is None


def test_patch_on_uninitialized_settings_inserts_bootstrap_defaults(
    database: Database,
) -> None:
    repository = AssistantSettingsRepository()
    with database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0

        patched = repository.patch(connection, AssistantSettingsPatchCommand(apiKey="k"))

        assert patched.api_key == "k"
        assert patched.chat_model == DEFAULT_CHAT_MODEL
        assert patched.audio_model == DEFAULT_AUDIO_MODEL
        assert patched.base_url == DEFAULT_ARK_BASE_URL

        settings = SettingsRepository().get(connection)
        assert settings.theme == "workspace-light"
        assert settings.muted is False
        assert settings.shortcut == "Cmd+Alt+KeyT"
        assert settings.language == "zh-CN"

        assert repository.get(connection).api_key == "k"
