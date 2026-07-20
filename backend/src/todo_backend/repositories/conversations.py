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
    ProposalAction,
    ProposalFields,
    ProposalStatus,
)


class ConversationNotFoundError(LookupError):
    pass


class ProposalNotFoundError(LookupError):
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
    ) -> AssistantMessage:
        now = _now_ms()
        message_id = uuid.uuid4().hex
        serialized = [a.model_dump(mode="json", by_alias=True) for a in attachments]
        connection.execute(
            "INSERT INTO assistant_messages"
            " (id, conversation_id, role, content, attachments, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, conversation_id, role, content, json.dumps(serialized), status, now),
        )
        return AssistantMessage(
            id=message_id, role=role, content=content,
            attachments=attachments, status=status, createdAt=now,
        )

    def list_messages(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantMessage]:
        rows = connection.execute(
            "SELECT id, role, content, attachments, status, created_at"
            " FROM assistant_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [self._message_from_row(row) for row in rows]

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
        now = _now_ms()
        proposal_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, action, task_id, payload, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                proposal_id, conversation_id, message_id, action, task_id,
                payload.model_dump_json(exclude_unset=True), now,
            ),
        )
        return AssistantProposal(
            id=proposal_id, messageId=message_id, action=action, taskId=task_id,
            payload=payload, status="pending", createdAt=now,
        )

    def list_proposals(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposal]:
        rows = connection.execute(
            "SELECT id, message_id, action, task_id, payload, status, created_at"
            " FROM assistant_proposals WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [self._proposal_from_row(row) for row in rows]

    def list_pending_proposals(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposal]:
        return [p for p in self.list_proposals(connection, conversation_id) if p.status == "pending"]

    def get_proposal(
        self, connection: sqlite3.Connection, proposal_id: str
    ) -> AssistantProposal:
        row = connection.execute(
            "SELECT id, message_id, action, task_id, payload, status, created_at"
            " FROM assistant_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ProposalNotFoundError
        return self._proposal_from_row(row)

    def mark_proposal(
        self,
        connection: sqlite3.Connection,
        proposal_id: str,
        status: ProposalStatus,
        resolved_at: int,
    ) -> AssistantProposal:
        connection.execute(
            "UPDATE assistant_proposals SET status = ?, resolved_at = ? WHERE id = ?",
            (status, resolved_at, proposal_id),
        )
        return self.get_proposal(connection, proposal_id)

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
            id=row["id"], role=row["role"], content=row["content"],
            attachments=[AssistantAttachment.model_validate(a) for a in raw_attachments],
            status=row["status"], createdAt=row["created_at"],
        )

    def _proposal_from_row(self, row: sqlite3.Row) -> AssistantProposal:
        return AssistantProposal(
            id=row["id"], messageId=row["message_id"], action=row["action"],
            taskId=row["task_id"],
            payload=ProposalFields.model_validate(json.loads(row["payload"])),
            status=row["status"], createdAt=row["created_at"],
        )
