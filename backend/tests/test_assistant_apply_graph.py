# pyright: reportUnknownMemberType=false

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from todo_backend.agent.apply_graph import ProposalApplyWorkflow
from todo_backend.agent.checkpoints import CheckpointStore
from todo_backend.database import Database
from todo_backend.models import (
    AssistantProposal,
    AssistantProposalBatch,
    ConfirmProposalBatchCommand,
    ConfirmProposalItem,
    ProposalApplyItemResult,
    ProposalBatchResolveResponse,
    ProposalBatchStatus,
    ProposalCardFields,
    ProposalStatus,
)
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchesRepository,
    ProposalDraft,
)
from todo_backend.services.proposal_batches import (
    ProposalBatchExecutor,
    ProposalBatchNotConfirmableError,
)


def _card(text: str = "待确认") -> ProposalCardFields:
    return ProposalCardFields(
        text=text,
        priority="medium",
        category="other",
        time_start=None,
        time_end=None,
        notes=None,
    )


def command_for(proposal_id: str, text: str = "编辑后") -> ConfirmProposalBatchCommand:
    return ConfirmProposalBatchCommand(
        items=[
            ConfirmProposalItem(
                proposalId=proposal_id,
                payload=ProposalCardFields(
                    text=text,
                    priority="high",
                    category="work",
                    time_start=None,
                    time_end=None,
                    notes="确认卡修改",
                ),
            )
        ]
    )


class FakeExecutor(ProposalBatchExecutor):
    def __init__(
        self,
        *,
        status: ProposalBatchStatus,
        status_after_confirm: ProposalBatchStatus = "accepted",
        pending_proposal_ids: set[str] | None = None,
        verify_error: str | None = None,
    ) -> None:
        proposal_ids = {"p1"} | (pending_proposal_ids or set())
        initial_status: ProposalStatus = (
            "accepted"
            if status == "accepted"
            else "rejected"
            if status == "rejected"
            else "superseded"
            if status == "superseded"
            else "pending"
        )
        self._status = status
        self._status_after_confirm = status_after_confirm
        self._pending_after_confirm = set(pending_proposal_ids or set())
        self._proposal_statuses = {
            proposal_id: initial_status for proposal_id in sorted(proposal_ids)
        }
        self._errors: dict[str, str | None] = {
            proposal_id: None for proposal_id in proposal_ids
        }
        self._verify_error = verify_error
        self.confirm_calls: list[tuple[str, ConfirmProposalBatchCommand]] = []
        self.reject_calls: list[str] = []
        self.fail_pending_calls: list[tuple[str, str]] = []
        self.verify_calls: list[str] = []
        self.recompute_calls: list[str] = []

    def current(self, batch_id: str) -> ProposalBatchResolveResponse:
        proposals = [
            AssistantProposal(
                id=proposal_id,
                messageId="m1",
                batchId=batch_id,
                action="create",
                targetTaskId=None,
                beforeSnapshot=None,
                payload=_card(),
                resultTaskId=None,
                status=status,
                lastError=self._errors[proposal_id],
                createdAt=1,
            )
            for proposal_id, status in self._proposal_statuses.items()
        ]
        batch = AssistantProposalBatch(
            id=batch_id,
            messageId="m1",
            status=self._status,
            supersedesBatchId=None,
            proposals=proposals,
            createdAt=1,
            resolvedAt=None,
        )
        return ProposalBatchResolveResponse(
            batch=batch,
            items=[
                ProposalApplyItemResult(
                    proposal=proposal,
                    task=None,
                    error=proposal.last_error,
                )
                for proposal in proposals
            ],
        )

    def confirm(
        self, batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        self.confirm_calls.append((batch_id, command))
        for item in command.items:
            if item.proposal_id not in self._pending_after_confirm:
                self._proposal_statuses[item.proposal_id] = "accepted"
                self._errors[item.proposal_id] = None
        self._status = self._status_after_confirm
        return self.current(batch_id)

    def reject(self, batch_id: str) -> ProposalBatchResolveResponse:
        self.reject_calls.append(batch_id)
        for proposal_id, status in self._proposal_statuses.items():
            if status == "pending":
                self._proposal_statuses[proposal_id] = "rejected"
                self._errors[proposal_id] = None
        self._status = "rejected"
        return self.current(batch_id)

    def fail_pending(
        self, batch_id: str, error_code: str
    ) -> ProposalBatchResolveResponse:
        self.fail_pending_calls.append((batch_id, error_code))
        for proposal_id, status in self._proposal_statuses.items():
            if status == "pending":
                self._errors[proposal_id] = error_code
        return self.current(batch_id)

    def verify(self, batch_id: str) -> ProposalBatchResolveResponse:
        self.verify_calls.append(batch_id)
        if self._verify_error is not None:
            for proposal_id, status in self._proposal_statuses.items():
                if status == "accepted":
                    self._errors[proposal_id] = self._verify_error
        return self.current(batch_id)

    def recompute(self, batch_id: str) -> ProposalBatchResolveResponse:
        self.recompute_calls.append(batch_id)
        return self.current(batch_id)


@dataclass(frozen=True, slots=True)
class SeededBatch:
    executor: ProposalBatchExecutor
    batch: AssistantProposalBatch
    confirm_command: ConfirmProposalBatchCommand


@pytest.fixture
def seeded_batch(tmp_path: Path) -> SeededBatch:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    payload = _card("持久化确认")
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "", []
        )
        batch = batches.insert_batches(
            connection,
            conversation_id=conversation.id,
            message_id=message.id,
            drafts=[
                BatchDraft(
                    id="b-persisted",
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id="p-persisted",
                            action="create",
                            target_task_id=None,
                            before_snapshot=None,
                            payload=payload,
                        )
                    ],
                )
            ],
        )[0]
    return SeededBatch(
        executor=ProposalBatchExecutor(database),
        batch=batch,
        confirm_command=ConfirmProposalBatchCommand(
            items=[
                ConfirmProposalItem(
                    proposalId=batch.proposals[0].id,
                    payload=payload,
                )
            ]
        ),
    )


def test_apply_graph_waits_before_any_write() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())

    workflow.start("b1")

    assert executor.confirm_calls == []
    assert executor.reject_calls == []
    assert executor.fail_pending_calls == []
    assert executor.verify_calls == []
    assert executor.recompute_calls == []


def test_start_is_idempotent_on_an_interrupted_thread() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())

    workflow.start("b1")
    first = workflow.graph.get_state(workflow.config("b1"))
    workflow.start("b1")
    second = workflow.graph.get_state(workflow.config("b1"))

    assert first.config == second.config
    assert second.next == ("interrupt_review",)


def test_confirm_resumes_with_edited_payload_without_model_call() -> None:
    executor = FakeExecutor(status="pending", status_after_confirm="accepted")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")
    command = command_for("p1")

    result = workflow.confirm("b1", command)

    assert executor.confirm_calls == [("b1", command)]
    assert result.batch.status == "accepted"


def test_reject_routes_to_executor_without_confirming() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")

    result = workflow.reject("b1")

    assert executor.reject_calls == ["b1"]
    assert executor.confirm_calls == []
    assert result.batch.status == "rejected"


def test_malformed_resume_marks_pending_items_and_interrupts_again() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")

    workflow.graph.invoke(
        Command(resume={"decision": "confirm", "items": []}),
        config=workflow.config("b1"),
    )

    assert executor.fail_pending_calls == [
        ("b1", "INVALID_CONFIRMATION_PAYLOAD")
    ]
    assert executor.current("b1").items[0].error == "INVALID_CONFIRMATION_PAYLOAD"
    snapshot = workflow.graph.get_state(workflow.config("b1"))
    assert snapshot.next == ("interrupt_review",)


def test_partial_result_interrupts_again_for_remaining_items() -> None:
    executor = FakeExecutor(
        status="pending",
        status_after_confirm="partially_applied",
        pending_proposal_ids={"p2"},
    )
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")

    workflow.confirm("b1", command_for("p1"))

    snapshot = workflow.graph.get_state(workflow.config("b1"))
    assert snapshot.next == ("interrupt_review",)


def test_checkpoint_state_is_json_safe() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())

    workflow.start("b1")

    snapshot = workflow.graph.get_state(workflow.config("b1"))
    json.dumps(snapshot.values, allow_nan=False)
    assert snapshot.values["batch_id"] == "b1"
    assert isinstance(snapshot.values["result"], dict)


def test_repeat_confirmation_returns_terminal_executor_result() -> None:
    executor = FakeExecutor(status="pending", status_after_confirm="accepted")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    command = command_for("p1")

    first = workflow.confirm("b1", command)
    second = workflow.confirm("b1", command)

    assert first == second
    assert executor.confirm_calls == [("b1", command)]


@pytest.mark.parametrize("operation", ["confirm", "reject"])
def test_superseded_batch_cannot_be_resolved(operation: str) -> None:
    executor = FakeExecutor(status="superseded")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())

    with pytest.raises(ProposalBatchNotConfirmableError):
        if operation == "confirm":
            workflow.confirm("b1", command_for("p1"))
        else:
            workflow.reject("b1")

    assert executor.confirm_calls == []
    assert executor.reject_calls == []


def test_verify_mismatch_is_visible_after_rebuilding_workflow() -> None:
    executor = FakeExecutor(
        status="pending",
        status_after_confirm="accepted",
        verify_error="RESULT_VERIFICATION_FAILED",
    )
    saver = InMemorySaver()
    immediate = ProposalApplyWorkflow(executor, saver).confirm(
        "b1", command_for("p1")
    )

    rebuilt = ProposalApplyWorkflow(executor, saver)
    reloaded = rebuilt.start("b1")

    assert immediate.items[0].error == "RESULT_VERIFICATION_FAILED"
    assert reloaded.items[0].error == "RESULT_VERIFICATION_FAILED"
    assert executor.current("b1").items[0].error == "RESULT_VERIFICATION_FAILED"
    assert executor.confirm_calls == [("b1", command_for("p1"))]


def test_sqlite_checkpoint_resumes_confirmation_after_reopen(
    seeded_batch: SeededBatch, tmp_path: Path
) -> None:
    checkpoint_path = tmp_path / "assistant_graph.sqlite3"
    first_store = CheckpointStore(checkpoint_path)
    ProposalApplyWorkflow(seeded_batch.executor, first_store.saver).start(
        seeded_batch.batch.id
    )
    first_store.close()

    second_store = CheckpointStore(checkpoint_path)
    result = ProposalApplyWorkflow(
        seeded_batch.executor, second_store.saver
    ).confirm(seeded_batch.batch.id, seeded_batch.confirm_command)
    second_store.close()

    assert result.batch.status == "accepted"
    assert seeded_batch.executor.current(seeded_batch.batch.id).items[0].task is not None
