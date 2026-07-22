import sqlite3
import time

from pydantic import ValidationError

from todo_backend.database import Database
from todo_backend.models import (
    AssistantProposal,
    ConfirmProposalBatchCommand,
    ConfirmProposalItem,
    CreateTaskCommand,
    ProposalApplyItemResult,
    ProposalBatchResolveResponse,
    ProposalCardFields,
    Task,
    TimeField,
    UpdateTaskCommand,
)
from todo_backend.repositories.proposal_batches import ProposalBatchesRepository
from todo_backend.repositories.tasks import TaskNotFoundError
from todo_backend.services.tasks import TaskService


EDITABLE_FIELDS = {"text", "priority", "category", "time_start", "time_end", "notes"}


class InvalidProposalBatchCommandError(ValueError):
    pass


class ProposalResultVerificationError(RuntimeError):
    pass


class ProposalBatchNotConfirmableError(RuntimeError):
    pass


class _ProposalBusinessError(ValueError):
    def __init__(
        self, code: str, payload: ProposalCardFields | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.payload = payload


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class ProposalBatchExecutor:
    def __init__(
        self,
        database: Database,
        batches: ProposalBatchesRepository | None = None,
        tasks: TaskService | None = None,
    ) -> None:
        self._database = database
        self._batches = batches or ProposalBatchesRepository()
        self._tasks = tasks or TaskService(database)

    def confirm(
        self, batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        proposal_ids = [item.proposal_id for item in command.items]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise InvalidProposalBatchCommandError("DUPLICATE_PROPOSAL_ID")
        with self._database.transaction() as connection:
            batch = self._batches.get_batch(connection, batch_id)
            batch_proposal_ids = {proposal.id for proposal in batch.proposals}
        if not set(proposal_ids) <= batch_proposal_ids:
            raise InvalidProposalBatchCommandError("PROPOSAL_NOT_IN_BATCH")

        edits = {item.proposal_id: item for item in command.items}
        results = [
            self._apply_one(batch_id, proposal_id, edits[proposal_id])
            for proposal_id in edits
        ]
        with self._database.transaction() as connection:
            batch = self._batches.recompute_batch(connection, batch_id)
        return ProposalBatchResolveResponse(batch=batch, items=results)

    def reject(self, batch_id: str) -> ProposalBatchResolveResponse:
        with self._database.transaction() as connection:
            batch = self._batches.get_batch(connection, batch_id)
            if batch.status == "superseded":
                raise ProposalBatchNotConfirmableError
            for proposal in batch.proposals:
                if proposal.status == "pending":
                    self._batches.mark_item(
                        connection,
                        proposal.id,
                        payload=None,
                        status="rejected",
                        result_task_id=proposal.result_task_id,
                        last_error=None,
                        resolved_at=_now_ms(),
                    )
            self._batches.recompute_batch(connection, batch_id)
        return self.current(batch_id)

    def verify(self, batch_id: str) -> ProposalBatchResolveResponse:
        current = self.current(batch_id)
        for item in current.items:
            if item.proposal.status != "accepted":
                continue
            try:
                self._verify_accepted(item.proposal)
            except ProposalResultVerificationError:
                with self._database.transaction() as connection:
                    self._batches.set_last_error(
                        connection, item.proposal.id, "RESULT_VERIFICATION_FAILED"
                    )
        return self.current(batch_id)

    def current(self, batch_id: str) -> ProposalBatchResolveResponse:
        with self._database.transaction() as connection:
            batch = self._batches.get_batch(connection, batch_id)
            items = [
                ProposalApplyItemResult(
                    proposal=proposal,
                    task=self._result_task(connection, proposal),
                    error=proposal.last_error,
                )
                for proposal in batch.proposals
            ]
        return ProposalBatchResolveResponse(batch=batch, items=items)

    def fail_pending(
        self, batch_id: str, error_code: str
    ) -> ProposalBatchResolveResponse:
        with self._database.transaction() as connection:
            batch = self._batches.get_batch(connection, batch_id)
            for proposal in batch.proposals:
                if proposal.status == "pending":
                    self._batches.mark_item(
                        connection,
                        proposal.id,
                        payload=None,
                        status="pending",
                        result_task_id=proposal.result_task_id,
                        last_error=error_code,
                        resolved_at=None,
                    )
            self._batches.recompute_batch(connection, batch_id)
        return self.current(batch_id)

    def recompute(self, batch_id: str) -> ProposalBatchResolveResponse:
        with self._database.transaction() as connection:
            self._batches.recompute_batch(connection, batch_id)
        return self.current(batch_id)

    def _apply_one(
        self, batch_id: str, proposal_id: str, item: ConfirmProposalItem
    ) -> ProposalApplyItemResult:
        payload: ProposalCardFields | None = None
        try:
            with self._database.transaction() as connection:
                batch = self._batches.get_batch(connection, batch_id)
                proposal = self._batches.get_proposal(connection, proposal_id)
                if proposal.status == "accepted":
                    return self._accepted_result(connection, proposal)
                if proposal.status != "pending" or batch.status == "superseded":
                    return ProposalApplyItemResult(
                        proposal=proposal,
                        task=self._result_task(connection, proposal),
                        error="PROPOSAL_NOT_CONFIRMABLE",
                    )

                try:
                    payload = self._validated_full_payload(proposal, item)
                except ValidationError as error:
                    raise _ProposalBusinessError(
                        "INVALID_PROPOSAL_PAYLOAD"
                    ) from error
                if proposal.action in {"update", "delete"}:
                    if proposal.target_task_id is None or proposal.before_snapshot is None:
                        raise _ProposalBusinessError(
                            "TASK_TARGET_NOT_FOUND",
                            None if proposal.action == "delete" else payload,
                        )
                    current = self._tasks.repository.get(
                        connection, proposal.target_task_id
                    )
                    if current != proposal.before_snapshot:
                        return self._pending_error(
                            connection,
                            proposal,
                            "TASK_CHANGED_SINCE_PROPOSAL",
                            payload=payload,
                        )

                task: Task | None
                if proposal.action == "create":
                    try:
                        create_command = self._create_command(payload)
                    except ValidationError as error:
                        raise _ProposalBusinessError(
                            "INVALID_PROPOSAL_PAYLOAD", payload
                        ) from error
                    task = self._tasks.create_in_transaction(
                        connection, create_command
                    )
                elif proposal.action == "update":
                    try:
                        update_command = self._update_command(
                            payload, proposal.before_snapshot
                        )
                    except ValidationError as error:
                        raise _ProposalBusinessError(
                            "INVALID_PROPOSAL_PAYLOAD", payload
                        ) from error
                    task = self._tasks.update_in_transaction(
                        connection,
                        proposal.target_task_id or "",
                        update_command,
                    )
                else:
                    self._tasks.delete_in_transaction(
                        connection, proposal.target_task_id or ""
                    )
                    task = None

                if proposal.action in {"create", "update"}:
                    stored = self._tasks.repository.get(
                        connection, task.id if task else ""
                    )
                    if not self._matches_payload(stored, payload):
                        raise ProposalResultVerificationError(
                            "RESULT_VERIFICATION_FAILED"
                        )
                else:
                    try:
                        self._tasks.repository.get(
                            connection, proposal.target_task_id or ""
                        )
                    except TaskNotFoundError:
                        pass
                    else:
                        raise ProposalResultVerificationError(
                            "RESULT_VERIFICATION_FAILED"
                        )

                resolved = self._batches.mark_item(
                    connection,
                    proposal.id,
                    payload=payload,
                    status="accepted",
                    result_task_id=task.id if task else proposal.target_task_id,
                    last_error=None,
                    resolved_at=_now_ms(),
                )
                return ProposalApplyItemResult(
                    proposal=resolved, task=task, error=None
                )
        except _ProposalBusinessError as error:
            return self._record_pending_error(
                batch_id, proposal_id, error.code, payload=error.payload
            )
        except TaskNotFoundError:
            return self._record_pending_error(
                batch_id, proposal_id, "TASK_TARGET_NOT_FOUND", payload=payload
            )
        except ProposalResultVerificationError:
            return self._record_pending_error(
                batch_id,
                proposal_id,
                "RESULT_VERIFICATION_FAILED",
                payload=payload,
            )

    def _validated_full_payload(
        self, proposal: AssistantProposal, item: ConfirmProposalItem
    ) -> ProposalCardFields:
        if proposal.action == "delete":
            if (
                proposal.target_task_id is None
                or proposal.before_snapshot is None
                or proposal.payload is None
            ):
                raise _ProposalBusinessError("TASK_TARGET_NOT_FOUND")
            raw_payload = proposal.payload.model_dump()
        else:
            if item.payload is None:
                raise _ProposalBusinessError("INVALID_PROPOSAL_PAYLOAD")
            raw_payload = item.payload.model_dump()
            if set(raw_payload) != EDITABLE_FIELDS:
                raise _ProposalBusinessError("INVALID_PROPOSAL_PAYLOAD")

        payload = ProposalCardFields.model_validate(raw_payload)
        if not payload.text.strip():
            raise _ProposalBusinessError("CREATE_TITLE_REQUIRED", payload)
        if payload.time_end is not None and payload.time_start is None:
            raise _ProposalBusinessError("TIME_END_REQUIRES_START", payload)
        if (
            payload.time_start is not None
            and payload.time_end is not None
            and payload.time_end < payload.time_start
        ):
            raise _ProposalBusinessError("TIME_END_BEFORE_START", payload)
        return payload

    def _create_command(self, payload: ProposalCardFields) -> CreateTaskCommand:
        return CreateTaskCommand(
            text=payload.text,
            priority=payload.priority,
            category=payload.category,
            time=self._time_field(payload),
            notes=payload.notes,
        )

    def _update_command(
        self, payload: ProposalCardFields, before: Task | None
    ) -> UpdateTaskCommand:
        if before is None:
            raise _ProposalBusinessError("TASK_TARGET_NOT_FOUND", payload)

        values: dict[str, object] = {}
        for field_name in ("text", "priority", "category", "notes"):
            if getattr(payload, field_name) != getattr(before, field_name):
                values[field_name] = getattr(payload, field_name)

        updated_time = self._time_field(payload)
        if updated_time != before.time:
            values["time"] = updated_time
        if not values:
            raise _ProposalBusinessError("UPDATE_HAS_NO_CHANGES", payload)
        return UpdateTaskCommand.model_validate(values)

    def _time_field(self, payload: ProposalCardFields) -> TimeField | None:
        if payload.time_start is None:
            return None
        return TimeField(start=payload.time_start, end=payload.time_end)

    def _matches_payload(self, task: Task, payload: ProposalCardFields) -> bool:
        return (
            task.text == payload.text
            and task.priority == payload.priority
            and task.category == payload.category
            and task.time == self._time_field(payload)
            and task.notes == payload.notes
        )

    def _pending_error(
        self,
        connection: sqlite3.Connection,
        proposal: AssistantProposal,
        error_code: str,
        *,
        payload: ProposalCardFields | None,
    ) -> ProposalApplyItemResult:
        resolved = self._batches.mark_item(
            connection,
            proposal.id,
            payload=None if proposal.action == "delete" else payload,
            status="pending",
            result_task_id=proposal.result_task_id,
            last_error=error_code,
            resolved_at=None,
        )
        return ProposalApplyItemResult(
            proposal=resolved, task=None, error=error_code
        )

    def _record_pending_error(
        self,
        batch_id: str,
        proposal_id: str,
        error_code: str,
        *,
        payload: ProposalCardFields | None,
    ) -> ProposalApplyItemResult:
        with self._database.transaction() as connection:
            batch = self._batches.get_batch(connection, batch_id)
            proposal = self._batches.get_proposal(connection, proposal_id)
            if proposal.status != "pending" or batch.status == "superseded":
                return ProposalApplyItemResult(
                    proposal=proposal,
                    task=self._result_task(connection, proposal),
                    error="PROPOSAL_NOT_CONFIRMABLE",
                )
            return self._pending_error(
                connection, proposal, error_code, payload=payload
            )

    def _accepted_result(
        self, connection: sqlite3.Connection, proposal: AssistantProposal
    ) -> ProposalApplyItemResult:
        return ProposalApplyItemResult(
            proposal=proposal,
            task=self._result_task(connection, proposal),
            error=proposal.last_error,
        )

    def _result_task(
        self, connection: sqlite3.Connection, proposal: AssistantProposal
    ) -> Task | None:
        if (
            proposal.status != "accepted"
            or proposal.action == "delete"
            or proposal.result_task_id is None
        ):
            return None
        try:
            return self._tasks.repository.get(connection, proposal.result_task_id)
        except TaskNotFoundError:
            return None

    def _verify_accepted(self, proposal: AssistantProposal) -> None:
        with self._database.transaction() as connection:
            if proposal.action in {"create", "update"}:
                if proposal.result_task_id is None or proposal.payload is None:
                    raise ProposalResultVerificationError(
                        "RESULT_VERIFICATION_FAILED"
                    )
                try:
                    task = self._tasks.repository.get(
                        connection, proposal.result_task_id
                    )
                except TaskNotFoundError as error:
                    raise ProposalResultVerificationError(
                        "RESULT_VERIFICATION_FAILED"
                    ) from error
                if not self._matches_payload(task, proposal.payload):
                    raise ProposalResultVerificationError(
                        "RESULT_VERIFICATION_FAILED"
                    )
                return

            target_task_id = proposal.result_task_id or proposal.target_task_id
            if target_task_id is None:
                raise ProposalResultVerificationError("RESULT_VERIFICATION_FAILED")
            try:
                self._tasks.repository.get(connection, target_task_id)
            except TaskNotFoundError:
                return
            raise ProposalResultVerificationError("RESULT_VERIFICATION_FAILED")
