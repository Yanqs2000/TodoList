# pyright: reportUnknownMemberType=false

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError

from todo_backend.database import Database
from todo_backend.models import (
    AssistantProposal,
    AssistantProposalBatch,
    ConfirmProposalBatchCommand,
    ConfirmProposalItem,
    CreateTaskCommand,
    ProposalCardFields,
    Task,
    TimeField,
    UpdateTaskCommand,
)
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchesRepository,
    ProposalDraft,
)
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.proposal_batches import (
    InvalidProposalBatchCommandError,
    ProposalBatchExecutor,
)
from todo_backend.services.tasks import TaskService


@dataclass(frozen=True, slots=True)
class SeededBatch:
    database: Database
    executor: ProposalBatchExecutor
    task_service: TaskService
    batch: AssistantProposalBatch
    proposal: AssistantProposal
    confirm_command: ConfirmProposalBatchCommand
    task: Task | None = None


class HydrationValidationTaskRepository(TaskRepository):
    def get(self, connection: sqlite3.Connection, task_id: str) -> Task:
        del connection
        return Task.model_validate({"id": task_id})


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


def _card(
    text: str = "买菜",
    *,
    priority: str = "medium",
    category: str = "other",
    time_start: str | None = None,
    time_end: str | None = None,
    notes: str | None = None,
) -> ProposalCardFields:
    return ProposalCardFields.model_validate(
        {
            "text": text,
            "priority": priority,
            "category": category,
            "time_start": time_start,
            "time_end": time_end,
            "notes": notes,
        }
    )


def _card_from_task(task: Task, **updates: object) -> ProposalCardFields:
    values: dict[str, object] = {
        "text": task.text,
        "priority": task.priority,
        "category": task.category,
        "time_start": task.time.start if task.time else None,
        "time_end": task.time.end if task.time else None,
        "notes": task.notes,
    }
    values.update(updates)
    return ProposalCardFields.model_validate(values)


def _insert_batch(
    database: Database,
    draft: BatchDraft,
) -> AssistantProposalBatch:
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "", []
        )
        return batches.insert_batches(
            connection,
            conversation_id=conversation.id,
            message_id=message.id,
            drafts=[draft],
        )[0]


@pytest.fixture
def create_batch(database: Database) -> SeededBatch:
    payload = _card()
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-create",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id="p-create",
                    action="create",
                    target_task_id=None,
                    before_snapshot=None,
                    payload=payload,
                )
            ],
        ),
    )
    proposal = batch.proposals[0]
    return SeededBatch(
        database=database,
        executor=ProposalBatchExecutor(database),
        task_service=TaskService(database),
        batch=batch,
        proposal=proposal,
        confirm_command=ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=proposal.id, payload=payload)]
        ),
    )


@pytest.fixture
def update_batch(database: Database) -> SeededBatch:
    task_service = TaskService(database)
    task = task_service.create(
        CreateTaskCommand(
            text="会议",
            priority="high",
            category="work",
            time=TimeField(start="2026-07-22T15:00", end="2026-07-22T16:00"),
        )
    )
    payload = _card_from_task(task, time_end="2026-07-22T17:00")
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-update",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id="p-update",
                    action="update",
                    target_task_id=task.id,
                    before_snapshot=task,
                    payload=payload,
                )
            ],
        ),
    )
    proposal = batch.proposals[0]
    return SeededBatch(
        database=database,
        executor=ProposalBatchExecutor(database),
        task_service=task_service,
        batch=batch,
        proposal=proposal,
        confirm_command=ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=proposal.id, payload=payload)]
        ),
        task=task,
    )


@pytest.fixture
def delete_batch(database: Database) -> SeededBatch:
    task_service = TaskService(database)
    task = task_service.create(CreateTaskCommand(text="删除我", priority="medium"))
    payload = _card_from_task(task)
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-delete",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id="p-delete",
                    action="delete",
                    target_task_id=task.id,
                    before_snapshot=task,
                    payload=payload,
                )
            ],
        ),
    )
    proposal = batch.proposals[0]
    return SeededBatch(
        database=database,
        executor=ProposalBatchExecutor(database),
        task_service=task_service,
        batch=batch,
        proposal=proposal,
        confirm_command=ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=proposal.id, payload=payload)]
        ),
        task=task,
    )


def test_confirm_update_preserves_start_when_card_changes_only_end(
    update_batch: SeededBatch,
) -> None:
    result = update_batch.executor.confirm(
        update_batch.batch.id, update_batch.confirm_command
    )

    assert result.items[0].error is None
    assert result.items[0].task is not None
    assert result.items[0].task.time == TimeField(
        start="2026-07-22T15:00", end="2026-07-22T17:00"
    )


def test_confirm_is_idempotent_and_returns_same_created_task(
    create_batch: SeededBatch,
) -> None:
    first = create_batch.executor.confirm(
        create_batch.batch.id, create_batch.confirm_command
    )
    second = create_batch.executor.confirm(
        create_batch.batch.id, create_batch.confirm_command
    )

    assert first.items[0].task == second.items[0].task
    assert first.items[0].proposal.result_task_id == second.items[0].proposal.result_task_id
    assert len(create_batch.task_service.list_all()) == 1


def test_stale_update_stays_pending_without_overwrite(
    update_batch: SeededBatch,
) -> None:
    assert update_batch.task is not None
    update_batch.task_service.update(
        update_batch.task.id, UpdateTaskCommand(text="用户在别处改过")
    )

    result = update_batch.executor.confirm(
        update_batch.batch.id, update_batch.confirm_command
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "TASK_CHANGED_SINCE_PROPOSAL"
    assert update_batch.task_service.list_all()[0].text == "用户在别处改过"


def test_batch_commits_successes_and_keeps_failures_pending(database: Database) -> None:
    create_payload = _card("成功创建")
    missing_payload = _card("不存在的删除目标")
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-mixed",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id="p1-create",
                    action="create",
                    target_task_id=None,
                    before_snapshot=None,
                    payload=create_payload,
                ),
                ProposalDraft(
                    id="p2-missing",
                    action="delete",
                    target_task_id="missing",
                    before_snapshot=None,
                    payload=missing_payload,
                ),
            ],
        ),
    )
    executor = ProposalBatchExecutor(database)
    result = executor.confirm(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[
                ConfirmProposalItem(proposalId="p1-create", payload=create_payload),
                ConfirmProposalItem(proposalId="p2-missing", payload=missing_payload),
            ]
        ),
    )

    assert [item.proposal.status for item in result.items] == ["accepted", "pending"]
    assert [item.error for item in result.items] == [None, "TASK_TARGET_NOT_FOUND"]
    assert result.batch.status == "partially_applied"
    assert [task.text for task in TaskService(database).list_all()] == ["成功创建"]


def test_confirm_persists_edited_payload_for_reload(
    create_batch: SeededBatch,
) -> None:
    assert create_batch.proposal.payload is not None
    payload = create_batch.proposal.payload.model_copy(update={"text": "卡片编辑后"})
    command = ConfirmProposalBatchCommand(
        items=[ConfirmProposalItem(proposalId=create_batch.proposal.id, payload=payload)]
    )

    create_batch.executor.confirm(create_batch.batch.id, command)
    reloaded = create_batch.executor.current(create_batch.batch.id)

    assert reloaded.items[0].proposal.payload is not None
    assert reloaded.items[0].proposal.payload.text == "卡片编辑后"
    assert reloaded.items[0].task is not None
    assert reloaded.items[0].task.text == "卡片编辑后"


def test_failed_item_keeps_parsed_card_edits_for_retry(
    update_batch: SeededBatch,
) -> None:
    assert update_batch.task is not None
    update_batch.task_service.update(
        update_batch.task.id, UpdateTaskCommand(text="外部修改")
    )
    assert update_batch.proposal.payload is not None
    edited = update_batch.proposal.payload.model_copy(update={"notes": "保留我"})
    result = update_batch.executor.confirm(
        update_batch.batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=update_batch.proposal.id, payload=edited)]
        ),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].proposal.payload is not None
    assert result.items[0].proposal.payload.notes == "保留我"
    current_payload = update_batch.executor.current(update_batch.batch.id).items[0].proposal.payload
    assert current_payload is not None
    assert current_payload.notes == "保留我"


def test_blank_edited_title_stays_pending_and_preserves_payload(
    create_batch: SeededBatch,
) -> None:
    assert create_batch.proposal.payload is not None
    payload = create_batch.proposal.payload.model_copy(update={"text": "   "})

    result = create_batch.executor.confirm(
        create_batch.batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=create_batch.proposal.id, payload=payload)]
        ),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "CREATE_TITLE_REQUIRED"
    assert result.items[0].proposal.payload == payload
    assert create_batch.task_service.list_all() == []


def test_end_before_start_stays_pending_and_preserves_payload(
    create_batch: SeededBatch,
) -> None:
    assert create_batch.proposal.payload is not None
    payload = create_batch.proposal.payload.model_copy(
        update={
            "time_start": "2026-07-22T17:00",
            "time_end": "2026-07-22T16:00",
        }
    )

    result = create_batch.executor.confirm(
        create_batch.batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=create_batch.proposal.id, payload=payload)]
        ),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "TIME_END_BEFORE_START"
    assert result.items[0].proposal.payload == payload
    assert create_batch.task_service.list_all() == []


def test_noop_update_stays_pending(update_batch: SeededBatch) -> None:
    assert update_batch.task is not None
    payload = _card_from_task(update_batch.task)

    result = update_batch.executor.confirm(
        update_batch.batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=update_batch.proposal.id, payload=payload)]
        ),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "UPDATE_HAS_NO_CHANGES"
    assert result.items[0].proposal.payload == payload
    assert update_batch.task_service.list_all() == [update_batch.task]


def test_duplicate_proposal_ids_reject_entire_command_before_writes(
    create_batch: SeededBatch,
) -> None:
    item = create_batch.confirm_command.items[0]
    command = ConfirmProposalBatchCommand(items=[item, item])

    with pytest.raises(
        InvalidProposalBatchCommandError, match="DUPLICATE_PROPOSAL_ID"
    ):
        create_batch.executor.confirm(create_batch.batch.id, command)

    assert create_batch.task_service.list_all() == []
    assert create_batch.executor.current(create_batch.batch.id).batch.status == "pending"


def test_unknown_proposal_id_rejects_valid_sibling_before_writes(
    create_batch: SeededBatch,
) -> None:
    command = ConfirmProposalBatchCommand(
        items=[
            create_batch.confirm_command.items[0],
            ConfirmProposalItem(proposalId="unknown", payload=_card("不应创建")),
        ]
    )

    with pytest.raises(InvalidProposalBatchCommandError, match="PROPOSAL_NOT_IN_BATCH"):
        create_batch.executor.confirm(create_batch.batch.id, command)

    assert create_batch.task_service.list_all() == []
    assert create_batch.executor.current(create_batch.batch.id).batch.status == "pending"


def test_proposal_from_another_batch_rejects_command_before_writes(
    create_batch: SeededBatch,
) -> None:
    other_payload = _card("另一个批次")
    other = _insert_batch(
        create_batch.database,
        BatchDraft(
            id="b-other",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id="p-other",
                    action="create",
                    target_task_id=None,
                    before_snapshot=None,
                    payload=other_payload,
                )
            ],
        ),
    )
    command = ConfirmProposalBatchCommand(
        items=[
            create_batch.confirm_command.items[0],
            ConfirmProposalItem(
                proposalId=other.proposals[0].id, payload=other_payload
            ),
        ]
    )

    with pytest.raises(InvalidProposalBatchCommandError, match="PROPOSAL_NOT_IN_BATCH"):
        create_batch.executor.confirm(create_batch.batch.id, command)

    assert create_batch.task_service.list_all() == []
    assert create_batch.executor.current(create_batch.batch.id).batch.status == "pending"
    assert create_batch.executor.current(other.id).batch.status == "pending"


def test_partial_retry_can_omit_unrelated_pending_proposals(database: Database) -> None:
    first_payload = _card("第一个")
    second_payload = _card("第二个")
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-partial",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft("p-first", "create", None, None, first_payload),
                ProposalDraft("p-second", "create", None, None, second_payload),
            ],
        ),
    )
    executor = ProposalBatchExecutor(database)

    first = executor.confirm(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId="p-first", payload=first_payload)]
        ),
    )

    assert first.batch.status == "partially_applied"
    assert [proposal.status for proposal in first.batch.proposals] == ["accepted", "pending"]
    second = executor.confirm(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId="p-second", payload=second_payload)]
        ),
    )
    assert second.batch.status == "accepted"
    assert sorted(task.text for task in TaskService(database).list_all()) == [
        "第一个",
        "第二个",
    ]


def test_delete_is_idempotent(delete_batch: SeededBatch) -> None:
    first = delete_batch.executor.confirm(
        delete_batch.batch.id, delete_batch.confirm_command
    )
    second = delete_batch.executor.confirm(
        delete_batch.batch.id, delete_batch.confirm_command
    )

    assert first.items[0].proposal.status == "accepted"
    assert first.items[0].proposal.result_task_id == second.items[0].proposal.result_task_id
    assert first.items[0].task is None
    assert second.items[0].task is None
    assert delete_batch.task_service.list_all() == []


@pytest.mark.parametrize("missing", ["snapshot", "target"])
def test_delete_without_snapshot_or_target_does_not_execute(
    database: Database, missing: str
) -> None:
    task_service = TaskService(database)
    task = task_service.create(CreateTaskCommand(text="必须保留", priority="medium"))
    payload = _card_from_task(task)
    batch = _insert_batch(
        database,
        BatchDraft(
            id=f"b-missing-{missing}",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft(
                    id=f"p-missing-{missing}",
                    action="delete",
                    target_task_id=None if missing == "target" else task.id,
                    before_snapshot=None if missing == "snapshot" else task,
                    payload=payload,
                )
            ],
        ),
    )
    executor = ProposalBatchExecutor(database)

    result = executor.confirm(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[ConfirmProposalItem(proposalId=batch.proposals[0].id, payload=payload)]
        ),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "TASK_TARGET_NOT_FOUND"
    assert task_service.list_all() == [task]


def test_reject_changes_only_remaining_pending_items(database: Database) -> None:
    accepted_payload = _card("已接受")
    pending_payload = _card("待拒绝")
    batch = _insert_batch(
        database,
        BatchDraft(
            id="b-reject",
            supersedes_batch_id=None,
            proposals=[
                ProposalDraft("p-accepted", "create", None, None, accepted_payload),
                ProposalDraft("p-pending", "create", None, None, pending_payload),
            ],
        ),
    )
    executor = ProposalBatchExecutor(database)
    executor.confirm(
        batch.id,
        ConfirmProposalBatchCommand(
            items=[
                ConfirmProposalItem(proposalId="p-accepted", payload=accepted_payload)
            ]
        ),
    )

    result = executor.reject(batch.id)

    assert [item.proposal.status for item in result.items] == ["accepted", "rejected"]
    assert result.batch.status == "partially_applied"
    assert [task.text for task in TaskService(database).list_all()] == ["已接受"]


def test_create_and_result_task_id_rollback_together_when_marking_fails(
    create_batch: SeededBatch,
) -> None:
    with create_batch.database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER fail_accept BEFORE UPDATE OF status ON assistant_proposals "
            "WHEN NEW.status = 'accepted' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="blocked"):
        create_batch.executor.confirm(create_batch.batch.id, create_batch.confirm_command)

    assert create_batch.task_service.list_all() == []
    proposal = create_batch.executor.current(create_batch.batch.id).items[0].proposal
    assert proposal.status == "pending"
    assert proposal.result_task_id is None


def test_repository_hydration_validation_error_propagates_and_rolls_back(
    create_batch: SeededBatch,
) -> None:
    tasks = TaskService(
        create_batch.database, repository=HydrationValidationTaskRepository()
    )
    executor = ProposalBatchExecutor(create_batch.database, tasks=tasks)

    with pytest.raises(ValidationError):
        executor.confirm(create_batch.batch.id, create_batch.confirm_command)

    assert TaskService(create_batch.database).list_all() == []
    proposal = executor.current(create_batch.batch.id).items[0].proposal
    assert proposal.status == "pending"
    assert proposal.last_error is None


def test_create_success_stores_result_task_id_with_task(
    create_batch: SeededBatch,
) -> None:
    result = create_batch.executor.confirm(
        create_batch.batch.id, create_batch.confirm_command
    )

    task = result.items[0].task
    assert task is not None
    assert result.items[0].proposal.result_task_id == task.id
    assert create_batch.executor.current(create_batch.batch.id).items[0].task == task


def test_post_commit_verify_records_error_without_replaying_write(
    create_batch: SeededBatch,
) -> None:
    applied = create_batch.executor.confirm(
        create_batch.batch.id, create_batch.confirm_command
    )
    task = applied.items[0].task
    assert task is not None
    create_batch.task_service.update(task.id, UpdateTaskCommand(text="提交后被修改"))

    first = create_batch.executor.verify(create_batch.batch.id)
    second = create_batch.executor.verify(create_batch.batch.id)

    assert first.items[0].proposal.status == "accepted"
    assert first.items[0].error == "RESULT_VERIFICATION_FAILED"
    assert second.items[0].error == "RESULT_VERIFICATION_FAILED"
    stored = create_batch.task_service.list_all()
    assert len(stored) == 1
    assert stored[0].text == "提交后被修改"


def test_fail_pending_persists_graph_error_without_changing_payload(
    create_batch: SeededBatch,
) -> None:
    original_payload = create_batch.proposal.payload

    result = create_batch.executor.fail_pending(
        create_batch.batch.id, "INVALID_CONFIRMATION_PAYLOAD"
    )

    assert result.batch.status == "pending"
    assert result.items[0].proposal.status == "pending"
    assert result.items[0].proposal.payload == original_payload
    assert result.items[0].error == "INVALID_CONFIRMATION_PAYLOAD"


def test_recompute_refreshes_batch_status_from_item_status(
    create_batch: SeededBatch,
) -> None:
    with create_batch.database.transaction() as connection:
        ProposalBatchesRepository().mark_item(
            connection,
            create_batch.proposal.id,
            payload=None,
            status="rejected",
            result_task_id=None,
            last_error=None,
            resolved_at=1,
        )

    before = create_batch.executor.current(create_batch.batch.id)
    result = create_batch.executor.recompute(create_batch.batch.id)

    assert before.batch.status == "pending"
    assert before.items[0].proposal.status == "rejected"
    assert result.batch.status == "rejected"


def test_current_tolerates_missing_accepted_task_and_verify_surfaces_error(
    create_batch: SeededBatch,
) -> None:
    applied = create_batch.executor.confirm(
        create_batch.batch.id, create_batch.confirm_command
    )
    task = applied.items[0].task
    assert task is not None
    create_batch.task_service.delete(task.id)

    current = create_batch.executor.current(create_batch.batch.id)
    verified = create_batch.executor.verify(create_batch.batch.id)

    assert current.items[0].proposal.status == "accepted"
    assert current.items[0].task is None
    assert current.items[0].error is None
    assert verified.items[0].task is None
    assert verified.items[0].error == "RESULT_VERIFICATION_FAILED"
