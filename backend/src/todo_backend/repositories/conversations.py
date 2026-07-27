import json
import sqlite3
import time
import uuid
from typing import Any

from todo_backend.models import (
    AssistantAttachment,
    AssistantConversationSummary,
    AssistantMessage,
    AssistantMessageStatus,
    AssistantProposal,
    AssistantRole,
    AssistantTurnRecord,
    AssistantTurnStatus,
    ProposalAction,
    ProposalCardFields,
    ProposalFields,
    ProposalStatus,
    Task,
    TimeField,
)
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchesRepository,
    ProposalDraft,
    ProposalNotFoundError as ProposalNotFoundError,
)


class ConversationNotFoundError(LookupError):
    pass


class AssistantTurnNotFoundError(LookupError):
    pass


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class ConversationsRepository:
    def create_conversation(
        self, connection: sqlite3.Connection, title: str
    ) -> AssistantConversationSummary:
        now = _now_ms()
        conversation_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO assistant_conversations (id, title, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (conversation_id, title, now, now),
        )
        return AssistantConversationSummary(
            id=conversation_id, title=title, createdAt=now, updatedAt=now
        )

    def list_conversations(
        self, connection: sqlite3.Connection
    ) -> list[AssistantConversationSummary]:
        rows = connection.execute(
            "SELECT id, title, created_at, updated_at"
            " FROM assistant_conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def get_conversation(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> AssistantConversationSummary:
        row = connection.execute(
            "SELECT id, title, created_at, updated_at"
            " FROM assistant_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ConversationNotFoundError
        return self._conversation_from_row(row)

    def delete_conversation(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> None:
        cursor = connection.execute(
            "DELETE FROM assistant_conversations WHERE id = ?", (conversation_id,)
        )
        if cursor.rowcount == 0:
            raise ConversationNotFoundError

    def touch(self, connection: sqlite3.Connection, conversation_id: str) -> None:
        connection.execute(
            "UPDATE assistant_conversations SET updated_at = ? WHERE id = ?",
            (_now_ms(), conversation_id),
        )

    def insert_message(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        role: AssistantRole,
        content: str,
        attachments: list[AssistantAttachment],
        status: AssistantMessageStatus = "done",
        *,
        turn_id: str | None = None,
    ) -> AssistantMessage:
        now = _now_ms()
        message_id = uuid.uuid4().hex
        serialized = [a.model_dump(mode="json", by_alias=True) for a in attachments]
        connection.execute(
            "INSERT INTO assistant_messages"
            " (id, conversation_id, role, content, attachments, status, created_at, turn_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                conversation_id,
                role,
                content,
                json.dumps(serialized),
                status,
                now,
                turn_id,
            ),
        )
        return AssistantMessage(
            id=message_id,
            role=role,
            content=content,
            attachments=attachments,
            status=status,
            createdAt=now,
            turnId=turn_id,
        )

    def list_messages(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantMessage]:
        rows = connection.execute(
            "SELECT id, role, content, attachments, status, created_at, turn_id"
            " FROM assistant_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def get_message(
        self, connection: sqlite3.Connection, message_id: str
    ) -> AssistantMessage:
        row = connection.execute(
            "SELECT id, role, content, attachments, status, created_at, turn_id"
            " FROM assistant_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise LookupError("assistant message not found")
        return self._message_from_row(row)

    def insert_turn(
        self,
        connection: sqlite3.Connection,
        turn_id: str,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
        request_fingerprint: str,
    ) -> AssistantTurnRecord:
        now = _now_ms()
        connection.execute(
            "INSERT INTO assistant_turns"
            " (id, conversation_id, user_message_id, assistant_message_id,"
            " request_fingerprint, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                turn_id,
                conversation_id,
                user_message_id,
                assistant_message_id,
                request_fingerprint,
                now,
                now,
            ),
        )
        return self.get_turn(connection, turn_id)

    def get_turn(
        self, connection: sqlite3.Connection, turn_id: str
    ) -> AssistantTurnRecord:
        row = connection.execute(
            "SELECT id, conversation_id, user_message_id, assistant_message_id,"
            " request_fingerprint, status, last_error FROM assistant_turns WHERE id = ?",
            (turn_id,),
        ).fetchone()
        if row is None:
            raise AssistantTurnNotFoundError
        return AssistantTurnRecord.model_validate(dict(row))

    def mark_turn(
        self,
        connection: sqlite3.Connection,
        turn_id: str,
        status: AssistantTurnStatus,
        last_error: str | None,
    ) -> AssistantTurnRecord:
        connection.execute(
            "UPDATE assistant_turns SET status = ?, last_error = ?, updated_at = ?"
            " WHERE id = ?",
            (status, last_error, _now_ms(), turn_id),
        )
        return self.get_turn(connection, turn_id)

    def list_turn_ids(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[str]:
        return [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM assistant_turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        ]

    def update_message(
        self,
        connection: sqlite3.Connection,
        message_id: str,
        *,
        content: str,
        status: AssistantMessageStatus,
        tool_trace: str | None,
    ) -> None:
        connection.execute(
            "UPDATE assistant_messages SET content = ?, status = ?, tool_trace = ?"
            " WHERE id = ?",
            (content, status, tool_trace, message_id),
        )

    def update_message_attachments(
        self,
        connection: sqlite3.Connection,
        message_id: str,
        attachments: list[AssistantAttachment],
    ) -> None:
        serialized = [a.model_dump(mode="json", by_alias=True) for a in attachments]
        connection.execute(
            "UPDATE assistant_messages SET attachments = ? WHERE id = ?",
            (json.dumps(serialized), message_id),
        )

    def insert_proposal(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        message_id: str,
        action: ProposalAction,
        task_id: str | None,
        payload: ProposalFields,
    ) -> AssistantProposal:
        proposal_id = uuid.uuid4().hex
        before_snapshot = self._task_snapshot(connection, task_id) if task_id else None
        raw_fields = payload.model_dump(exclude_unset=True)
        if action == "create":
            card = ProposalCardFields.model_validate(
                {
                    "text": None,
                    "priority": "medium",
                    "category": "other",
                    "time_start": None,
                    "time_end": None,
                    "notes": None,
                    **raw_fields,
                }
            )
        elif before_snapshot is not None:
            base_fields = self._card_fields_from_task(before_snapshot)
            if action == "update":
                base_fields.update(raw_fields)
            card = ProposalCardFields.model_validate(base_fields)
        else:
            raise ValueError("proposal target task not found")
        batch = ProposalBatchesRepository().insert_batches(
            connection,
            conversation_id=conversation_id,
            message_id=message_id,
            drafts=[
                BatchDraft(
                    id=proposal_id,
                    supersedes_batch_id=None,
                    proposals=[
                        ProposalDraft(
                            id=proposal_id,
                            action=action,
                            target_task_id=task_id,
                            before_snapshot=before_snapshot,
                            payload=card,
                        )
                    ],
                )
            ],
        )
        return batch[0].proposals[0]

    def list_proposals(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposal]:
        return [
            proposal
            for batch in ProposalBatchesRepository().list_for_conversation(
                connection, conversation_id
            )
            for proposal in batch.proposals
        ]

    def list_pending_proposals(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposal]:
        return [p for p in self.list_proposals(connection, conversation_id) if p.status == "pending"]

    def get_proposal(
        self, connection: sqlite3.Connection, proposal_id: str
    ) -> AssistantProposal:
        return ProposalBatchesRepository().get_proposal(connection, proposal_id)

    def mark_proposal(
        self,
        connection: sqlite3.Connection,
        proposal_id: str,
        status: ProposalStatus,
        resolved_at: int,
    ) -> AssistantProposal:
        batches = ProposalBatchesRepository()
        proposal = batches.get_proposal(connection, proposal_id)
        marked = batches.mark_item(
            connection,
            proposal_id,
            payload=None,
            status=status,
            result_task_id=(
                proposal.target_task_id
                if status == "accepted" and proposal.action in {"update", "delete"}
                else proposal.result_task_id
            ),
            last_error=proposal.last_error,
            resolved_at=resolved_at,
        )
        batches.recompute_batch(connection, proposal.batch_id)
        return marked

    def list_conversation_file_ids(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[str]:
        rows = connection.execute(
            "SELECT attachments FROM assistant_messages"
            " WHERE conversation_id = ? AND attachments IS NOT NULL",
            (conversation_id,),
        ).fetchall()
        file_ids: list[str] = []
        for row in rows:
            for item in json.loads(row["attachments"]):
                file_ids.append(item["fileId"])
        return file_ids

    def _conversation_from_row(self, row: sqlite3.Row) -> AssistantConversationSummary:
        return AssistantConversationSummary(
            id=row["id"], title=row["title"],
            createdAt=row["created_at"], updatedAt=row["updated_at"],
        )

    def _message_from_row(self, row: sqlite3.Row) -> AssistantMessage:
        raw_attachments: list[dict[str, Any]] = (
            json.loads(row["attachments"]) if row["attachments"] else []
        )
        return AssistantMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            attachments=[AssistantAttachment.model_validate(a) for a in raw_attachments],
            status=row["status"],
            createdAt=row["created_at"],
            turnId=row["turn_id"],
        )

    def _task_snapshot(
        self, connection: sqlite3.Connection, task_id: str
    ) -> Task | None:
        row = connection.execute(
            "SELECT id, text, completed, priority, created_at, time_start, time_end,"
            " category, notes FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        task_time = (
            TimeField(start=row["time_start"], end=row["time_end"])
            if row["time_start"] is not None
            else None
        )
        return Task(
            id=row["id"],
            text=row["text"],
            completed=bool(row["completed"]),
            priority=row["priority"],
            createdAt=row["created_at"],
            time=task_time,
            category=row["category"],
            notes=row["notes"],
        )

    def _card_fields_from_task(self, task: Task) -> dict[str, object]:
        return {
            "text": task.text,
            "priority": task.priority,
            "category": task.category,
            "time_start": task.time.start if task.time is not None else None,
            "time_end": task.time.end if task.time is not None else None,
            "notes": task.notes,
        }
