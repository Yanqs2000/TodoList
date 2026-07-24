# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from todo_backend.agent.planning import IntentPlan, PlannedMutation, TargetQuery
from todo_backend.agent.proposals import ResolvedMutation, build_batch_drafts
from todo_backend.database import Database
from todo_backend.models import CreateTaskCommand, ProposalCardFields, TimeField
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchNotFoundError,
    ProposalBatchesRepository,
    ProposalDraft,
    ProposalNotFoundError,
)
from todo_backend.repositories.tasks import TaskRepository


@dataclass(frozen=True, slots=True)
class Seed:
    conversation_id: str
    assistant_message_id: str


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


@pytest.fixture
def seeded_turn(database: Database) -> Seed:
    conversations = ConversationsRepository()
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        user = conversations.insert_message(connection, conversation.id, "user", "安排任务", [])
        assistant = conversations.insert_message(
            connection, conversation.id, "assistant", "", [], "pending"
        )
        connection.execute(
            "UPDATE assistant_messages SET turn_id = 'turn-1' WHERE id IN (?, ?)",
            (user.id, assistant.id),
        )
        connection.execute(
            "INSERT INTO assistant_turns"
            " (id, conversation_id, user_message_id, assistant_message_id,"
            " request_fingerprint, status, created_at, updated_at)"
            " VALUES ('turn-1', ?, ?, ?, 'fingerprint-1', 'active', 1, 1)",
            (conversation.id, user.id, assistant.id),
        )
    return Seed(conversation.id, assistant.id)


def _card(text: str = "买菜") -> ProposalCardFields:
    return ProposalCardFields(
        text=text,
        priority="medium",
        category="other",
        time_start=None,
        time_end=None,
        notes=None,
    )


def _create_draft(
    *, batch_id: str = "b1", proposal_id: str = "p1", text: str = "买菜"
) -> BatchDraft:
    return BatchDraft(
        id=batch_id,
        supersedes_batch_id=None,
        proposals=[
            ProposalDraft(
                id=proposal_id,
                action="create",
                target_task_id=None,
                before_snapshot=None,
                payload=_card(text),
            )
        ],
    )


def test_insert_batches_is_idempotent_and_writes_complete_payload(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    draft = _create_draft()

    with database.transaction() as connection:
        first = batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[draft],
        )
        second = batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[draft],
        )
        batch_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_proposal_batches WHERE id = 'b1'"
        ).fetchone()[0]
        proposal_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone()[0]
        raw_payload = connection.execute(
            "SELECT payload FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone()["payload"]

    assert [batch.id for batch in first] == ["b1"]
    assert [batch.id for batch in second] == ["b1"]
    assert batch_count == 1
    assert proposal_count == 1
    assert set(json.loads(raw_payload)) == {
        "text",
        "priority",
        "category",
        "time_start",
        "time_end",
        "notes",
    }

    with database.transaction() as connection:
        assert [batch.id for batch in batches.list_for_conversation(
            connection, seeded_turn.conversation_id
        )] == ["b1"]
        assert batches.get_proposal(connection, "p1").batch_id == "b1"
        assert batches.list_batch_ids(connection, seeded_turn.conversation_id) == ["b1"]


def test_insert_batches_rejects_stable_id_owned_by_another_message(
    database: Database, seeded_turn: Seed
) -> None:
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[_create_draft()],
        )
        other_message = conversations.insert_message(
            connection, seeded_turn.conversation_id, "assistant", "另一个回复", []
        )

    with pytest.raises(ValueError, match="batch.*message"):
        with database.transaction() as connection:
            batches.insert_batches(
                connection,
                conversation_id=seeded_turn.conversation_id,
                message_id=other_message.id,
                drafts=[_create_draft()],
            )


def test_insert_batches_rejects_stable_proposal_id_owned_by_another_batch(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[_create_draft()],
        )

    with pytest.raises(ValueError, match="proposal.*batch"):
        with database.transaction() as connection:
            batches.insert_batches(
                connection,
                conversation_id=seeded_turn.conversation_id,
                message_id=seeded_turn.assistant_message_id,
                drafts=[_create_draft(batch_id="b2", proposal_id="p1")],
            )


def test_insert_batches_rejects_null_draft_payload(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    draft = BatchDraft(
        id="b1",
        supersedes_batch_id=None,
        proposals=[
            ProposalDraft(
                id="p1",
                action="create",
                target_task_id=None,
                before_snapshot=None,
                payload=cast(ProposalCardFields, None),
            )
        ],
    )

    with pytest.raises(ValueError, match="payload"):
        with database.transaction() as connection:
            batches.insert_batches(
                connection,
                conversation_id=seeded_turn.conversation_id,
                message_id=seeded_turn.assistant_message_id,
                drafts=[draft],
            )


def test_batch_repository_hydrates_legacy_create_payload(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[_create_draft()],
        )
        connection.execute(
            "UPDATE assistant_proposals SET payload = ? WHERE id = 'p1'",
            ('{"text":"买菜"}',),
        )

    with database.transaction() as connection:
        proposal = batches.get_proposal(connection, "p1")

    assert proposal.payload is not None
    assert proposal.payload.text == "买菜"
    assert proposal.payload.priority == "medium"
    assert proposal.payload.category == "other"
    assert proposal.payload.time_start is None
    assert proposal.payload.time_end is None
    assert proposal.payload.notes is None


def test_batch_repository_hydrates_legacy_update_payload(
    database: Database, seeded_turn: Seed
) -> None:
    tasks = TaskRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        task = tasks.create(
            connection,
            CreateTaskCommand(
                text="会议",
                priority="high",
                category="work",
                time=TimeField(start="2026-07-22T15:00", end="2026-07-22T16:00"),
            ),
        )
        snapshot = task
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[
                BatchDraft(
                    id="b1",
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id="p1",
                            action="update",
                            target_task_id=task.id,
                            before_snapshot=snapshot,
                            payload=ProposalCardFields(
                                text="会议",
                                priority="high",
                                category="work",
                                time_start="2026-07-22T15:00",
                                time_end="2026-07-22T17:00",
                                notes=None,
                            ),
                        )
                    ],
                )
            ],
        )
        connection.execute(
            "UPDATE assistant_proposals SET payload = ? WHERE id = 'p1'",
            ('{"time_end":"2026-07-22T17:00"}',),
        )

    with database.transaction() as connection:
        batch = batches.get_batch(connection, "b1")

    proposal = batch.proposals[0]
    assert proposal.payload is not None
    assert proposal.payload.text == "会议"
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"


def test_delete_draft_with_null_payload_roundtrips_end_to_end(
    database: Database, seeded_turn: Seed
) -> None:
    tasks = TaskRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        task = tasks.create(
            connection,
            CreateTaskCommand(
                text="归档会议", priority="high", category="work", notes="纪要"
            ),
        )
    plan = IntentPlan(
        kind="mutations",
        evidence="删除请求",
        items=[
            PlannedMutation(
                action="delete", target_query=TargetQuery(title="归档会议")
            )
        ],
    )
    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=task)], superseded_batch=None
    )
    assert drafts[0].proposals[0].payload is None

    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=drafts,
        )
        proposal_id = drafts[0].proposals[0].id
        raw_payload = connection.execute(
            "SELECT payload FROM assistant_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()["payload"]
        proposal = batches.get_proposal(connection, proposal_id)

    assert raw_payload is None
    assert proposal.action == "delete"
    assert proposal.payload is None
    assert proposal.target_task_id == task.id
    assert proposal.before_snapshot == task


def test_batch_repository_reads_delete_payload_as_null_ignoring_legacy_column(
    database: Database, seeded_turn: Seed
) -> None:
    tasks = TaskRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        task = tasks.create(
            connection,
            CreateTaskCommand(
                text="归档会议",
                priority="high",
                category="work",
                notes="保留审计快照",
            ),
        )
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[
                BatchDraft(
                    id="b1",
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id="p1",
                            action="delete",
                            target_task_id=task.id,
                            before_snapshot=task,
                            payload=_card("过期标题"),
                        )
                    ],
                )
            ],
        )
        connection.execute(
            "UPDATE assistant_proposals SET payload = ? WHERE id = 'p1'",
            ('{"text":"过期标题"}',),
        )

    with database.transaction() as connection:
        proposal = batches.get_proposal(connection, "p1")

    assert proposal.payload is None
    assert proposal.before_snapshot is not None
    assert proposal.before_snapshot.text == "归档会议"
    assert proposal.before_snapshot.notes == "保留审计快照"


def test_missing_legacy_snapshots_remain_readable_with_null_payload(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        connection.executemany(
            "INSERT INTO assistant_proposal_batches"
            " (id, conversation_id, message_id, status, created_at, resolved_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("accepted-batch", seeded_turn.conversation_id,
                 seeded_turn.assistant_message_id, "accepted", 2, 3),
                ("pending-batch", seeded_turn.conversation_id,
                 seeded_turn.assistant_message_id, "pending", 4, None),
            ],
        )
        connection.executemany(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, batch_id, action, target_task_id,"
            " before_snapshot, payload, result_task_id, status, last_error,"
            " created_at, resolved_at)"
            " VALUES (?, ?, ?, ?, 'delete', ?, NULL, NULL, ?, ?, ?, ?, ?)",
            [
                ("accepted-delete", seeded_turn.conversation_id,
                 seeded_turn.assistant_message_id, "accepted-batch", "missing-accepted",
                 "missing-accepted", "accepted", None, 2, 3),
                ("pending-delete", seeded_turn.conversation_id,
                 seeded_turn.assistant_message_id, "pending-batch", "missing-pending",
                 None, "pending", "TASK_TARGET_NOT_FOUND", 4, None),
            ],
        )

    with database.transaction() as connection:
        listed = batches.list_for_conversation(connection, seeded_turn.conversation_id)
        accepted = batches.get_proposal(connection, "accepted-delete")
        pending = batches.get_proposal(connection, "pending-delete")

    assert [batch.id for batch in listed] == ["accepted-batch", "pending-batch"]
    assert accepted.before_snapshot is None
    assert accepted.payload is None
    assert accepted.status == "accepted"
    assert pending.before_snapshot is None
    assert pending.payload is None
    assert pending.last_error == "TASK_TARGET_NOT_FOUND"


def test_get_batch_and_proposal_raise_typed_not_found_errors(
    database: Database,
) -> None:
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        with pytest.raises(ProposalBatchNotFoundError):
            batches.get_batch(connection, "missing")
        with pytest.raises(ProposalNotFoundError):
            batches.get_proposal(connection, "missing")


def test_mark_item_persists_edited_audit_payload_and_set_last_error_only_changes_error(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    edited = ProposalCardFields(
        text="买水果",
        priority="high",
        category="life",
        time_start=None,
        time_end=None,
        notes="周末",
    )
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[_create_draft()],
        )
        accepted = batches.mark_item(
            connection,
            "p1",
            payload=edited,
            status="accepted",
            result_task_id="task-1",
            last_error=None,
            resolved_at=123,
        )
        before = dict(connection.execute(
            "SELECT payload, status, result_task_id, resolved_at, last_error"
            " FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone())
        with_error = batches.set_last_error(connection, "p1", "AUDIT_NOTE")
        after = dict(connection.execute(
            "SELECT payload, status, result_task_id, resolved_at, last_error"
            " FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone())

    assert accepted.payload == edited
    assert accepted.result_task_id == "task-1"
    assert with_error.last_error == "AUDIT_NOTE"
    assert after == {**before, "last_error": "AUDIT_NOTE"}


def test_mark_item_with_null_payload_preserves_stored_card(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[_create_draft()],
        )
        rejected = batches.mark_item(
            connection,
            "p1",
            payload=None,
            status="rejected",
            result_task_id=None,
            last_error="VALIDATION_ERROR",
            resolved_at=123,
        )

    assert rejected.payload == _card()
    assert rejected.status == "rejected"
    assert rejected.last_error == "VALIDATION_ERROR"


def test_recompute_batch_marks_accepted_and_rejected_terminal_batch_partial(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    draft = BatchDraft(
        id="b1",
        supersedes_batch_id=None,
        proposals=[
            _create_draft(proposal_id="p1").proposals[0],
            _create_draft(proposal_id="p2", text="买水果").proposals[0],
        ],
    )
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[draft],
        )
        batches.mark_item(
            connection,
            "p1",
            payload=None,
            status="accepted",
            result_task_id="task-1",
            last_error=None,
            resolved_at=100,
        )
        batches.mark_item(
            connection,
            "p2",
            payload=None,
            status="rejected",
            result_task_id=None,
            last_error=None,
            resolved_at=100,
        )
        batch = batches.recompute_batch(connection, "b1")

    assert batch.status == "partially_applied"
    assert batch.resolved_at is not None


def test_supersede_preserves_accepted_audit_and_terminal_batch_status(
    database: Database, seeded_turn: Seed
) -> None:
    batches = ProposalBatchesRepository()
    draft = BatchDraft(
        id="b1",
        supersedes_batch_id=None,
        proposals=[
            _create_draft(proposal_id="p1").proposals[0],
            _create_draft(proposal_id="p2", text="买水果").proposals[0],
        ],
    )
    edited = _card("买蔬菜")
    with database.transaction() as connection:
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[draft],
        )
        batches.mark_item(
            connection,
            "p1",
            payload=edited,
            status="accepted",
            result_task_id="task-1",
            last_error=None,
            resolved_at=100,
        )
        batches.supersede(connection, "b1", 200)
        after_supersede = batches.get_batch(connection, "b1")
        after_recompute = batches.recompute_batch(connection, "b1")

    assert after_supersede.status == "superseded"
    assert after_supersede.resolved_at == 200
    assert [proposal.status for proposal in after_supersede.proposals] == [
        "accepted",
        "superseded",
    ]
    assert after_supersede.proposals[0].payload == edited
    assert after_supersede.proposals[0].result_task_id == "task-1"
    assert after_recompute.status == "superseded"
    assert after_recompute.resolved_at == 200
