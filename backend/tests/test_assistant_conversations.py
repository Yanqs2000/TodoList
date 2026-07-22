# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import sqlite3
from pathlib import Path

import pytest

from todo_backend.database import Database
from todo_backend.models import AssistantAttachment, ProposalFields
from todo_backend.repositories.conversations import (
    AssistantTurnNotFoundError,
    ConversationNotFoundError,
    ConversationsRepository,
)
from todo_backend.repositories.proposal_batches import ProposalNotFoundError


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


@pytest.fixture
def repository() -> ConversationsRepository:
    return ConversationsRepository()


@pytest.fixture
def conversation_id(database: Database) -> str:
    with database.transaction() as connection:
        return ConversationsRepository().create_conversation(connection, "测试").id


def test_conversation_lifecycle(
    database: Database, repository: ConversationsRepository
) -> None:
    with database.transaction() as connection:
        created = repository.create_conversation(connection, "明天安排")
        assert created.title == "明天安排"

        listed = repository.list_conversations(connection)
        assert [c.id for c in listed] == [created.id]

        fetched = repository.get_conversation(connection, created.id)
        assert fetched.id == created.id

        repository.delete_conversation(connection, created.id)
        with pytest.raises(ConversationNotFoundError):
            repository.get_conversation(connection, created.id)


def test_message_roundtrip_with_attachments(
    database: Database, repository: ConversationsRepository
) -> None:
    with database.transaction() as connection:
        conversation = repository.create_conversation(connection, "测试")
        attachments = [
            AssistantAttachment(
                fileId="abc.pdf", kind="document", name="计划.pdf",
                mime="application/pdf", extractedText="文档正文",
            )
        ]
        message = repository.insert_message(
            connection, conversation.id, "user", "分析这个", attachments, turn_id="turn-1",
        )
        repository.update_message(
            connection, message.id,
            content="更新后", status="done", tool_trace='[{"name": "list_tasks"}]',
        )
        messages = repository.list_messages(connection, conversation.id)

        assert len(messages) == 1
        assert messages[0].content == "更新后"
        assert messages[0].attachments[0].extracted_text == "文档正文"
        assert messages[0].turn_id == "turn-1"
        assert repository.list_conversation_file_ids(connection, conversation.id) == ["abc.pdf"]


def test_turn_lifecycle(
    database: Database, repository: ConversationsRepository
) -> None:
    with database.transaction() as connection:
        conversation = repository.create_conversation(connection, "测试")
        user = repository.insert_message(
            connection, conversation.id, "user", "安排会议", [], turn_id="turn-1"
        )
        assistant = repository.insert_message(
            connection,
            conversation.id,
            "assistant",
            "",
            [],
            "pending",
            turn_id="turn-1",
        )
        inserted = repository.insert_turn(
            connection,
            "turn-1",
            conversation.id,
            user.id,
            assistant.id,
            "fingerprint-1",
        )

        assert inserted.status == "active"
        assert inserted.request_fingerprint == "fingerprint-1"
        assert repository.get_turn(connection, "turn-1") == inserted
        assert repository.list_turn_ids(connection, conversation.id) == ["turn-1"]

        completed = repository.mark_turn(connection, "turn-1", "done", None)
        assert completed.status == "done"
        assert completed.last_error is None

        with pytest.raises(AssistantTurnNotFoundError):
            repository.get_turn(connection, "missing")


def test_only_one_active_turn_per_conversation(
    database: Database, conversation_id: str
) -> None:
    repository = ConversationsRepository()
    with database.transaction() as connection:
        user = repository.insert_message(
            connection, conversation_id, "user", "one", [], turn_id="turn-1"
        )
        assistant = repository.insert_message(
            connection, conversation_id, "assistant", "", [], "pending", turn_id="turn-1"
        )
        repository.insert_turn(
            connection, "turn-1", conversation_id, user.id, assistant.id, "fingerprint-1"
        )

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            user = repository.insert_message(
                connection, conversation_id, "user", "two", [], turn_id="turn-2"
            )
            assistant = repository.insert_message(
                connection,
                conversation_id,
                "assistant",
                "",
                [],
                "pending",
                turn_id="turn-2",
            )
            repository.insert_turn(
                connection,
                "turn-2",
                conversation_id,
                user.id,
                assistant.id,
                "fingerprint-2",
            )


def test_proposal_lifecycle(
    database: Database, repository: ConversationsRepository
) -> None:
    with database.transaction() as connection:
        conversation = repository.create_conversation(connection, "测试")
        message = repository.insert_message(
            connection, conversation.id, "assistant", "提议如下", [],
        )
        proposal = repository.insert_proposal(
            connection, conversation.id, message.id, "create", None,
            ProposalFields(text="买菜", priority="medium"),
        )
        assert proposal.status == "pending"
        assert [p.id for p in repository.list_pending_proposals(connection, conversation.id)] == [
            proposal.id
        ]

        resolved = repository.mark_proposal(connection, proposal.id, "accepted", 123)
        assert resolved.status == "accepted"
        assert repository.list_pending_proposals(connection, conversation.id) == []

        with pytest.raises(ProposalNotFoundError):
            repository.get_proposal(connection, "missing")
