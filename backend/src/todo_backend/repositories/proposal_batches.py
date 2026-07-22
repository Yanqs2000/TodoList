import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, cast

from todo_backend.models import (
    AssistantProposal,
    AssistantProposalBatch,
    ProposalAction,
    ProposalBatchStatus,
    ProposalCardFields,
    ProposalStatus,
    Task,
)


@dataclass(frozen=True, slots=True)
class ProposalDraft:
    id: str
    action: ProposalAction
    target_task_id: str | None
    before_snapshot: Task | None
    payload: ProposalCardFields
    source_batch_id: str | None = None
    source_proposal_id: str | None = None


@dataclass(frozen=True, slots=True)
class BatchDraft:
    id: str
    supersedes_batch_id: str | None
    proposals: list[ProposalDraft]


class ProposalBatchNotFoundError(LookupError):
    pass


class ProposalNotFoundError(LookupError):
    pass


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class ProposalBatchesRepository:
    def insert_batches(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        message_id: str,
        drafts: list[BatchDraft],
    ) -> list[AssistantProposalBatch]:
        now = _now_ms()
        for draft in drafts:
            connection.execute(
                "INSERT OR IGNORE INTO assistant_proposal_batches"
                " (id, conversation_id, message_id, status, supersedes_batch_id, created_at)"
                " VALUES (?, ?, ?, 'pending', ?, ?)",
                (draft.id, conversation_id, message_id, draft.supersedes_batch_id, now),
            )
            batch_owner = connection.execute(
                "SELECT conversation_id, message_id"
                " FROM assistant_proposal_batches WHERE id = ?",
                (draft.id,),
            ).fetchone()
            if (
                batch_owner is None
                or batch_owner["conversation_id"] != conversation_id
                or batch_owner["message_id"] != message_id
            ):
                raise ValueError("batch belongs to another conversation or message")

            for proposal in draft.proposals:
                payload = cast(ProposalCardFields | None, proposal.payload)
                if payload is None:
                    raise ValueError("proposal payload cannot be null")
                connection.execute(
                    "INSERT OR IGNORE INTO assistant_proposals"
                    " (id, conversation_id, message_id, batch_id, action, target_task_id,"
                    " before_snapshot, payload, status, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (
                        proposal.id,
                        conversation_id,
                        message_id,
                        draft.id,
                        proposal.action,
                        proposal.target_task_id,
                        (
                            proposal.before_snapshot.model_dump_json(by_alias=True)
                            if proposal.before_snapshot is not None
                            else None
                        ),
                        payload.model_dump_json(by_alias=True),
                        now,
                    ),
                )
                proposal_owner = connection.execute(
                    "SELECT conversation_id, message_id, batch_id"
                    " FROM assistant_proposals WHERE id = ?",
                    (proposal.id,),
                ).fetchone()
                if (
                    proposal_owner is None
                    or proposal_owner["conversation_id"] != conversation_id
                    or proposal_owner["message_id"] != message_id
                    or proposal_owner["batch_id"] != draft.id
                ):
                    raise ValueError(
                        "proposal belongs to another batch, conversation, or message"
                    )

        return [self.get_batch(connection, draft.id) for draft in drafts]

    def list_for_conversation(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposalBatch]:
        rows = connection.execute(
            "SELECT id, message_id, status, supersedes_batch_id, created_at, resolved_at"
            " FROM assistant_proposal_batches WHERE conversation_id = ?"
            " ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        ).fetchall()
        return [self._batch_from_row(connection, row) for row in rows]

    def list_for_message(
        self, connection: sqlite3.Connection, message_id: str
    ) -> list[AssistantProposalBatch]:
        rows = connection.execute(
            "SELECT id, message_id, status, supersedes_batch_id, created_at, resolved_at"
            " FROM assistant_proposal_batches WHERE message_id = ?"
            " ORDER BY created_at ASC, id ASC",
            (message_id,),
        ).fetchall()
        return [self._batch_from_row(connection, row) for row in rows]

    def get_batch(
        self, connection: sqlite3.Connection, batch_id: str
    ) -> AssistantProposalBatch:
        row = connection.execute(
            "SELECT id, message_id, status, supersedes_batch_id, created_at, resolved_at"
            " FROM assistant_proposal_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise ProposalBatchNotFoundError
        return self._batch_from_row(connection, row)

    def get_proposal(
        self, connection: sqlite3.Connection, proposal_id: str
    ) -> AssistantProposal:
        row = connection.execute(
            "SELECT id, message_id, batch_id, action, target_task_id, before_snapshot,"
            " payload, result_task_id, status, last_error, created_at"
            " FROM assistant_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ProposalNotFoundError
        return self._proposal_from_row(row)

    def mark_item(
        self,
        connection: sqlite3.Connection,
        proposal_id: str,
        *,
        payload: ProposalCardFields | None,
        status: ProposalStatus,
        result_task_id: str | None,
        last_error: str | None,
        resolved_at: int | None,
    ) -> AssistantProposal:
        if payload is None:
            cursor = connection.execute(
                "UPDATE assistant_proposals"
                " SET status = ?, result_task_id = ?, last_error = ?, resolved_at = ?"
                " WHERE id = ?",
                (status, result_task_id, last_error, resolved_at, proposal_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE assistant_proposals"
                " SET payload = ?, status = ?, result_task_id = ?, last_error = ?,"
                " resolved_at = ? WHERE id = ?",
                (
                    payload.model_dump_json(by_alias=True),
                    status,
                    result_task_id,
                    last_error,
                    resolved_at,
                    proposal_id,
                ),
            )
        if cursor.rowcount == 0:
            raise ProposalNotFoundError
        return self.get_proposal(connection, proposal_id)

    def recompute_batch(
        self, connection: sqlite3.Connection, batch_id: str
    ) -> AssistantProposalBatch:
        batch_row = connection.execute(
            "SELECT status, resolved_at FROM assistant_proposal_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if batch_row is None:
            raise ProposalBatchNotFoundError

        proposals = self._list_proposals_for_batch(connection, batch_id)
        statuses = {proposal.status for proposal in proposals}
        current_batch_status = cast(ProposalBatchStatus, batch_row["status"])
        status: ProposalBatchStatus
        if current_batch_status == "superseded":
            status = "superseded"
        elif statuses == {"accepted"}:
            status = "accepted"
        elif "accepted" in statuses and len(statuses) > 1:
            status = "partially_applied"
        elif statuses <= {"rejected"}:
            status = "rejected"
        elif statuses <= {"superseded"}:
            status = "superseded"
        else:
            status = "pending"

        resolved_at = cast(int | None, batch_row["resolved_at"])
        if "pending" not in statuses and resolved_at is None:
            resolved_at = _now_ms()
        connection.execute(
            "UPDATE assistant_proposal_batches SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved_at, batch_id),
        )
        return self.get_batch(connection, batch_id)

    def set_last_error(
        self, connection: sqlite3.Connection, proposal_id: str, last_error: str | None
    ) -> AssistantProposal:
        cursor = connection.execute(
            "UPDATE assistant_proposals SET last_error = ? WHERE id = ?",
            (last_error, proposal_id),
        )
        if cursor.rowcount == 0:
            raise ProposalNotFoundError
        return self.get_proposal(connection, proposal_id)

    def supersede(
        self, connection: sqlite3.Connection, batch_id: str, resolved_at: int
    ) -> None:
        cursor = connection.execute(
            "UPDATE assistant_proposal_batches"
            " SET status = 'superseded', resolved_at = ? WHERE id = ?",
            (resolved_at, batch_id),
        )
        if cursor.rowcount == 0:
            raise ProposalBatchNotFoundError
        connection.execute(
            "UPDATE assistant_proposals"
            " SET status = 'superseded', resolved_at = ?"
            " WHERE batch_id = ? AND status = 'pending'",
            (resolved_at, batch_id),
        )

    def list_batch_ids(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[str]:
        return [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM assistant_proposal_batches"
                " WHERE conversation_id = ? ORDER BY created_at ASC, id ASC",
                (conversation_id,),
            ).fetchall()
        ]

    def _batch_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> AssistantProposalBatch:
        return AssistantProposalBatch(
            id=row["id"],
            messageId=row["message_id"],
            status=row["status"],
            supersedesBatchId=row["supersedes_batch_id"],
            proposals=self._list_proposals_for_batch(connection, row["id"]),
            createdAt=row["created_at"],
            resolvedAt=row["resolved_at"],
        )

    def _list_proposals_for_batch(
        self, connection: sqlite3.Connection, batch_id: str
    ) -> list[AssistantProposal]:
        rows = connection.execute(
            "SELECT id, message_id, batch_id, action, target_task_id, before_snapshot,"
            " payload, result_task_id, status, last_error, created_at"
            " FROM assistant_proposals WHERE batch_id = ? ORDER BY created_at ASC, id ASC",
            (batch_id,),
        ).fetchall()
        return [self._proposal_from_row(row) for row in rows]

    def _proposal_from_row(self, row: sqlite3.Row) -> AssistantProposal:
        action = cast(ProposalAction, row["action"])
        before_snapshot = (
            Task.model_validate_json(row["before_snapshot"])
            if row["before_snapshot"] is not None
            else None
        )
        raw_payload = self._payload_dict(row["payload"])
        payload: ProposalCardFields | None
        if action == "create":
            payload = ProposalCardFields.model_validate(
                {
                    "text": None,
                    "priority": "medium",
                    "category": "other",
                    "time_start": None,
                    "time_end": None,
                    "notes": None,
                    **raw_payload,
                }
            )
        elif before_snapshot is None:
            payload = None
        elif action == "update":
            payload = ProposalCardFields.model_validate(
                {**self._fields_from_task(before_snapshot), **raw_payload}
            )
        else:
            payload = ProposalCardFields.model_validate(
                self._fields_from_task(before_snapshot)
            )

        return AssistantProposal(
            id=row["id"],
            messageId=row["message_id"],
            batchId=row["batch_id"],
            action=action,
            targetTaskId=row["target_task_id"],
            beforeSnapshot=before_snapshot,
            payload=payload,
            resultTaskId=row["result_task_id"],
            status=row["status"],
            lastError=row["last_error"],
            createdAt=row["created_at"],
        )

    def _payload_dict(self, raw: str | None) -> dict[str, Any]:
        if raw is None:
            return {}
        payload: object = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("proposal payload must be a JSON object")
        return cast(dict[str, Any], payload)

    def _fields_from_task(self, task: Task) -> dict[str, object]:
        return {
            "text": task.text,
            "priority": task.priority,
            "category": task.category,
            "time_start": task.time.start if task.time is not None else None,
            "time_end": task.time.end if task.time is not None else None,
            "notes": task.notes,
        }
