# TodoList AI Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI assistant (agent) that analyzes text/voice/files via Volcano Engine Ark, proposes todo changes in a chat drawer, and writes tasks only after user confirmation.

**Architecture:** The Python backend owns the agent loop: it calls Ark chat completions with tool definitions, executes read tools directly, and turns write tools into proposal rows. A right-side React drawer holds the conversation; accepting a proposal calls the existing task layer. Voice recordings are encoded as WAV in the frontend and either transcribed (editable) or sent directly (backend cascades audio → transcription → main agent loop).

**Tech Stack:** FastAPI, Pydantic, sqlite3, `openai` Python SDK (Ark-compatible), pypdf, python-docx, pytest; React 19, TypeScript, Vitest, Web Audio API.

**Spec:** `docs/superpowers/specs/2026-07-20-ai-assistant-design.md`

## Global Constraints

- Ark base URL is exactly `https://ark.cn-beijing.volces.com/api/v3`; auth is `Authorization: Bearer <key>`.
- Default models (both user-configurable): chat `doubao-seed-2-1-pro-260628`, audio `doubao-seed-2-0-lite-260428`.
- The API key lives only in SQLite `app_settings.assistant_api_key`; no endpoint ever returns it and it is never logged.
- Logs must not contain message content, task text, tokens, or file paths (existing convention).
- Do not modify `backend/migrations/001_initial.sql` or `002_add_language_setting.sql`; add migration `003`.
- Agent writes go through proposal rows; real task writes happen only in the accept endpoint via the existing repositories.
- `todo_backend/agent/ark_client.py` is the only module that talks to Ark; every test injects fakes — no real network in tests.
- Assistant routes mount under `/api/v1/assistant/*` with the existing Bearer-token dependency.
- Backend code must pass `uv run --directory backend pyright` (strict) and `uv run --directory backend ruff check src tests`.
- Frontend code must pass `npm --prefix frontend test` and `npm --prefix frontend run build`.
- All new UI copy goes through `features/i18n` with both `zh-CN` and `en` entries.
- Keep every package and application version at `1.0.0`.

---

## File Structure

New backend files:

- `backend/migrations/003_add_assistant.sql` — conversations/messages/proposals tables + 3 settings columns.
- `backend/src/todo_backend/agent/__init__.py` — empty package marker.
- `backend/src/todo_backend/agent/ark_client.py` — Ark HTTP boundary (`ArkClient`, `ArkChatResult`, `ArkToolCall`, `ArkUnavailableError`).
- `backend/src/todo_backend/agent/tools.py` — tool JSON schemas + `AgentTools` executors.
- `backend/src/todo_backend/agent/orchestrator.py` — the agent loop (`AgentOrchestrator`, `AgentTurn`).
- `backend/src/todo_backend/repositories/assistant_settings.py` — `AssistantSettingsRepository`.
- `backend/src/todo_backend/repositories/conversations.py` — `ConversationsRepository` + not-found errors.
- `backend/src/todo_backend/services/documents.py` — `extract_document_text` + extraction errors.
- `backend/src/todo_backend/services/assistant.py` — `AssistantService` + service errors.
- `backend/src/todo_backend/assistant_api.py` — `build_assistant_router(service)` and error handlers.
- Tests: `backend/tests/test_assistant_*.py` (one per concern).

Modified backend files: `models.py` (assistant wire models), `api.py` (mount router + handlers), `pyproject.toml` (+ `openai`, `pypdf`, `python-docx`, `python-multipart`), `uv.lock`.

New frontend files:

- `frontend/src/features/assistant/hooks/useAssistant.ts`
- `frontend/src/features/assistant/components/{AssistantDrawer,MessageList,Composer,ProposalCard,AssistantSettingsPanel}.tsx`
- `frontend/src/features/assistant/recorder/wav.ts` — `encodeWav` + `WavRecorder`.
- `frontend/src/features/assistant/styles/assistant.css`
- Tests under `frontend/src/features/assistant/__tests__/` and `.../recorder/__tests__/`.

Modified frontend files: `shared/api/contracts.ts` (+ assistant types and `TodoApi` methods), `shared/api/client.ts` (+ implementations incl. multipart upload), `features/i18n/translations.ts` (+ keys and error mapping), `features/tasks/hooks/useTodos.ts` (+ `upsertExternalTask`, `removeExternalTask`), `features/header/components/Header.tsx` (+ assistant button), `app/App.tsx` (+ drawer wiring), `desktop/src-tauri/Info.plist` (new, mic usage description).

Docs: `docs/backend/api.md`, `docs/backend/database.md`, `README.md` (feature list).

---

### Task 1: Migration 003 + Assistant Settings Storage

**Files:**
- Create: `backend/migrations/003_add_assistant.sql`
- Create: `backend/src/todo_backend/repositories/assistant_settings.py`
- Modify: `backend/src/todo_backend/models.py`
- Test: `backend/tests/test_assistant_settings.py`

**Interfaces:**
- Produces: `AssistantSettings(api_key: str, chat_model: str, audio_model: str)` (internal, never serialized raw).
- Produces: `AssistantSettingsView(hasApiKey: bool, chatModel: str, audioModel: str)`.
- Produces: `AssistantSettingsPatchCommand(apiKey: str | None, chatModel: str | None, audioModel: str | None)`.
- Produces: `DEFAULT_CHAT_MODEL = "doubao-seed-2-1-pro-260628"`, `DEFAULT_AUDIO_MODEL = "doubao-seed-2-0-lite-260428"`.
- Produces: `AssistantSettingsRepository.get(connection) -> AssistantSettings` and `.patch(connection, command) -> AssistantSettings`.
- Produces: tables `assistant_conversations`, `assistant_messages`, `assistant_proposals` (used by Task 2).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assistant_settings.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import sqlite3
from pathlib import Path

import pytest

from todo_backend.database import Database
from todo_backend.models import AssistantSettingsPatchCommand
from todo_backend.repositories.assistant_settings import (
    DEFAULT_AUDIO_MODEL,
    DEFAULT_CHAT_MODEL,
    AssistantSettingsRepository,
)


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
    assert version == 3
    assert {
        "assistant_conversations",
        "assistant_messages",
        "assistant_proposals",
    } <= tables
    assert {
        "assistant_api_key",
        "assistant_chat_model",
        "assistant_audio_model",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_settings.py -v`
Expected: FAIL — `todo_backend.repositories.assistant_settings` does not exist; `PRAGMA user_version` is 2.

- [ ] **Step 3: Implement migration, model, and repository**

Create `backend/migrations/003_add_assistant.sql`:

```sql
CREATE TABLE assistant_conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE assistant_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES assistant_conversations (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    attachments TEXT,
    tool_trace TEXT,
    status TEXT NOT NULL DEFAULT 'done' CHECK (status IN ('pending', 'done', 'failed')),
    created_at INTEGER NOT NULL
);
CREATE INDEX idx_assistant_messages_conversation
    ON assistant_messages (conversation_id, created_at);

CREATE TABLE assistant_proposals (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES assistant_conversations (id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES assistant_messages (id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    task_id TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
);
CREATE INDEX idx_assistant_proposals_conversation
    ON assistant_proposals (conversation_id);

ALTER TABLE app_settings
ADD COLUMN assistant_api_key TEXT NOT NULL DEFAULT '';

ALTER TABLE app_settings
ADD COLUMN assistant_chat_model TEXT NOT NULL DEFAULT 'doubao-seed-2-1-pro-260628';

ALTER TABLE app_settings
ADD COLUMN assistant_audio_model TEXT NOT NULL DEFAULT 'doubao-seed-2-0-lite-260428';
```

Append to `backend/src/todo_backend/models.py`:

```python
DEFAULT_CHAT_MODEL = "doubao-seed-2-1-pro-260628"
DEFAULT_AUDIO_MODEL = "doubao-seed-2-0-lite-260428"


class AssistantSettings(WireModel):
    api_key: str
    chat_model: str
    audio_model: str


class AssistantSettingsView(WireModel):
    has_api_key: bool = Field(alias="hasApiKey")
    chat_model: str = Field(alias="chatModel")
    audio_model: str = Field(alias="audioModel")


class AssistantSettingsPatchCommand(WireModel):
    api_key: Annotated[str, Field(strict=True, max_length=200)] | None = Field(
        default=None, alias="apiKey"
    )
    chat_model: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = Field(
        default=None, alias="chatModel"
    )
    audio_model: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = Field(
        default=None, alias="audioModel"
    )

    @model_validator(mode="after")
    def reject_empty_or_null_patch(self) -> "AssistantSettingsPatchCommand":
        if not self.model_fields_set:
            raise ValueError("settings patch cannot be empty")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("settings fields cannot be null")
        return self
```

Create `backend/src/todo_backend/repositories/assistant_settings.py`:

```python
import sqlite3

from todo_backend.models import (
    DEFAULT_AUDIO_MODEL,
    DEFAULT_CHAT_MODEL,
    AssistantSettings,
    AssistantSettingsPatchCommand,
)

__all__ = ["DEFAULT_AUDIO_MODEL", "DEFAULT_CHAT_MODEL", "AssistantSettingsRepository"]


class AssistantSettingsRepository:
    def get(self, connection: sqlite3.Connection) -> AssistantSettings:
        row = connection.execute(
            "SELECT assistant_api_key, assistant_chat_model, assistant_audio_model"
            " FROM app_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Application settings are not initialized")
        return AssistantSettings(
            api_key=row["assistant_api_key"],
            chat_model=row["assistant_chat_model"],
            audio_model=row["assistant_audio_model"],
        )

    def patch(
        self,
        connection: sqlite3.Connection,
        command: AssistantSettingsPatchCommand,
    ) -> AssistantSettings:
        column_by_field = {
            "api_key": "assistant_api_key",
            "chat_model": "assistant_chat_model",
            "audio_model": "assistant_audio_model",
        }
        assignments: list[str] = []
        values: list[object] = []
        for field_name in command.model_fields_set:
            assignments.append(f"{column_by_field[field_name]} = ?")
            values.append(getattr(command, field_name))
        connection.execute(
            f"UPDATE app_settings SET {', '.join(assignments)} WHERE id = 1",
            values,
        )
        return self.get(connection)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_settings.py tests/test_database.py -v && uv run --directory backend pyright && uv run --directory backend ruff check src tests`
Expected: all PASS; pyright and ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/003_add_assistant.sql backend/src/todo_backend/models.py \
  backend/src/todo_backend/repositories/assistant_settings.py backend/tests/test_assistant_settings.py
git commit -m "feat: add assistant schema and settings storage"
```

---

### Task 2: Conversations Repository

**Files:**
- Create: `backend/src/todo_backend/repositories/conversations.py`
- Modify: `backend/src/todo_backend/models.py`
- Test: `backend/tests/test_assistant_conversations.py`

**Interfaces:**
- Consumes: Task 1 migration tables.
- Produces: `AssistantAttachment(fileId, kind, name, mime, extractedText?)` with `kind: Literal["image","document","audio"]`.
- Produces: `AssistantMessage(id, role, content, attachments, status, createdAt)`.
- Produces: `AssistantProposal(id, messageId, action, taskId, payload: ProposalFields, status, createdAt)`.
- Produces: `ProposalFields(text?, priority?, category?, time_start?, time_end?, notes?)` — all optional; `model_fields_set` distinguishes "clear" (explicit null) from "unset".
- Produces: `AssistantConversationSummary(id, title, createdAt, updatedAt)`.
- Produces: `ConversationsRepository` methods used by Tasks 5/7: `create_conversation`, `list_conversations`, `get_conversation`, `delete_conversation`, `touch`, `insert_message`, `list_messages`, `update_message`, `insert_proposal`, `list_proposals`, `list_pending_proposals`, `get_proposal`, `mark_proposal`, `list_conversation_file_ids`.
- Produces: `ConversationNotFoundError`, `ProposalNotFoundError`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assistant_conversations.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest

from todo_backend.database import Database
from todo_backend.models import AssistantAttachment, ProposalFields
from todo_backend.repositories.conversations import (
    ConversationNotFoundError,
    ConversationsRepository,
    ProposalNotFoundError,
)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


@pytest.fixture
def repository() -> ConversationsRepository:
    return ConversationsRepository()


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
            connection, conversation.id, "user", "分析这个", attachments,
        )
        repository.update_message(
            connection, message.id,
            content="更新后", status="done", tool_trace='[{"name": "list_tasks"}]',
        )
        messages = repository.list_messages(connection, conversation.id)

        assert len(messages) == 1
        assert messages[0].content == "更新后"
        assert messages[0].attachments[0].extracted_text == "文档正文"
        assert repository.list_conversation_file_ids(connection, conversation.id) == ["abc.pdf"]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_conversations.py -v`
Expected: FAIL — module `todo_backend.repositories.conversations` missing.

- [ ] **Step 3: Implement models and repository**

Append to `backend/src/todo_backend/models.py`:

```python
AssistantRole = Literal["user", "assistant"]
AssistantMessageStatus = Literal["pending", "done", "failed"]
AttachmentKind = Literal["image", "document", "audio"]
ProposalAction = Literal["create", "update", "delete"]
ProposalStatus = Literal["pending", "accepted", "rejected"]


class AssistantAttachment(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )
    kind: AttachmentKind
    name: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    mime: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    extracted_text: str | None = Field(default=None, alias="extractedText")


class ProposalFields(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    category: Category | None = None
    time_start: LocalDateTime | None = None
    time_end: LocalDateTime | None = None
    notes: StrictNotes | None = None


class AssistantMessage(WireModel):
    id: str
    role: AssistantRole
    content: str
    attachments: list[AssistantAttachment] = []
    status: AssistantMessageStatus = "done"
    created_at: int = Field(alias="createdAt")


class AssistantProposal(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    action: ProposalAction
    task_id: str | None = Field(default=None, alias="taskId")
    payload: ProposalFields
    status: ProposalStatus
    created_at: int = Field(alias="createdAt")


class AssistantConversationSummary(WireModel):
    id: str
    title: str
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")
```

Create `backend/src/todo_backend/repositories/conversations.py`:

```python
import json
import sqlite3
import time
import uuid

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
        raw_attachments = json.loads(row["attachments"]) if row["attachments"] else []
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_conversations.py -v && uv run --directory backend pyright && uv run --directory backend ruff check src tests`
Expected: all PASS; pyright and ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/todo_backend/models.py backend/src/todo_backend/repositories/conversations.py \
  backend/tests/test_assistant_conversations.py
git commit -m "feat: add assistant conversations repository"
```

---

### Task 3: Ark Client (the only network boundary)

**Files:**
- Create: `backend/src/todo_backend/agent/__init__.py` (empty)
- Create: `backend/src/todo_backend/agent/ark_client.py`
- Modify: `backend/pyproject.toml` (+ `openai`)
- Test: `backend/tests/test_assistant_ark_client.py`

**Interfaces:**
- Produces: `ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"`.
- Produces: `ArkUnavailableError(RuntimeError)`.
- Produces: `ArkToolCall(id: str, name: str, arguments: dict[str, Any])` (frozen dataclass).
- Produces: `ArkChatResult(content: str, tool_calls: list[ArkToolCall], raw_message: dict[str, Any])` (frozen dataclass).
- Produces: `ArkClient(api_key, chat_model, audio_model, *, timeout=60.0, client=None)` with `.chat(messages, tools=None) -> ArkChatResult` and `.transcribe(audio_base64, audio_format) -> str`.
- Consumed by: Task 6 orchestrator, Task 7 service.

- [ ] **Step 1: Add dependency and write the failing tests**

Run: `uv add --directory backend openai`

Create `backend/tests/test_assistant_ark_client.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError


def _completion(content: str | None, tool_calls: list[Any] | None = None) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.model_dump.return_value = {"role": "assistant", "content": content}
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def test_chat_returns_text_when_no_tool_calls() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("你好")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    result = client.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])

    assert result.content == "你好"
    assert result.tool_calls == []
    _, kwargs = sdk.chat.completions.create.call_args
    assert kwargs["model"] == "chat-model"
    assert kwargs["tools"] == [{"type": "function"}]
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_chat_parses_tool_calls() -> None:
    function = MagicMock()
    function.name = "list_tasks"
    function.arguments = '{"status": "active"}'
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function = function
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion(None, [tool_call])
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result.tool_calls[0].name == "list_tasks"
    assert result.tool_calls[0].arguments == {"status": "active"}
    assert result.raw_message["role"] == "assistant"


def test_chat_omits_tools_when_not_provided() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("ok")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    client.chat([{"role": "user", "content": "hi"}])

    _, kwargs = sdk.chat.completions.create.call_args
    assert "tools" not in kwargs


def test_transcribe_uses_audio_model_and_input_audio_part() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("明天下午三点开会")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    text = client.transcribe("QUJD", "wav")

    assert text == "明天下午三点开会"
    _, kwargs = sdk.chat.completions.create.call_args
    assert kwargs["model"] == "audio-model"
    parts = kwargs["messages"][0]["content"]
    assert parts[0] == {
        "type": "input_audio",
        "input_audio": {"data": "QUJD", "format": "wav"},
    }


def test_api_errors_become_ark_unavailable() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = RuntimeError("boom")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    with pytest.raises(ArkUnavailableError):
        client.chat([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_ark_client.py -v`
Expected: FAIL — module `todo_backend.agent.ark_client` missing.

- [ ] **Step 3: Implement the Ark client**

Create `backend/src/todo_backend/agent/__init__.py` (empty file).

Create `backend/src/todo_backend/agent/ark_client.py`:

```python
import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

_TRANSCRIBE_PROMPT = (
    "请识别音频中的内容，以文字形式返回识别结果。只输出识别出的文字，不要输出其他内容。"
)
_DISABLED_THINKING = {"thinking": {"type": "disabled"}}


class ArkUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArkToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ArkChatResult:
    content: str
    tool_calls: list[ArkToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)


class ArkClient:
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        audio_model: str,
        *,
        timeout: float = 60.0,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(
            base_url=ARK_BASE_URL,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )
        self._chat_model = chat_model
        self._audio_model = audio_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ArkChatResult:
        kwargs: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "extra_body": _DISABLED_THINKING,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as error:  # openai raises a broad exception tree
            raise ArkUnavailableError("chat completion failed") from error
        message = completion.choices[0].message
        tool_calls = [
            ArkToolCall(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in message.tool_calls or []
        ]
        return ArkChatResult(
            content=message.content or "",
            tool_calls=tool_calls,
            raw_message=message.model_dump(exclude_none=True),
        )

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_base64, "format": audio_format},
                    },
                    {"type": "text", "text": _TRANSCRIBE_PROMPT},
                ],
            }
        ]
        try:
            completion = self._client.chat.completions.create(
                model=self._audio_model,
                messages=messages,  # type: ignore[arg-type]
            )
        except Exception as error:
            raise ArkUnavailableError("audio transcription failed") from error
        return completion.choices[0].message.content or ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_ark_client.py -v && uv run --directory backend pyright`
Expected: PASS. If pyright flags the untyped SDK call, add targeted `# type: ignore[...]` comments — do not loosen global config.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/todo_backend/agent/ \
  backend/tests/test_assistant_ark_client.py
git commit -m "feat: add Volcano Ark chat client"
```

---

### Task 4: Document Text Extraction

**Files:**
- Create: `backend/src/todo_backend/services/documents.py`
- Modify: `backend/pyproject.toml` (+ `pypdf`, `python-docx`)
- Test: `backend/tests/test_assistant_documents.py`

**Interfaces:**
- Produces: `DOCUMENT_MAX_CHARS = 20_000`.
- Produces: `DocumentExtractionError(RuntimeError)` (corrupt/unreadable file), `DocumentEmptyError(DocumentExtractionError)` (no extractable text — e.g. scanned PDF).
- Produces: `extract_document_text(path: Path) -> str` — supports `.pdf`, `.docx`, `.txt`, `.md`; truncates at `DOCUMENT_MAX_CHARS` and appends `"\n...[TRUNCATED]"`.
- Consumed by: Task 7 service.

- [ ] **Step 1: Add dependencies and write the failing tests**

Run: `uv add --directory backend pypdf python-docx`

Create `backend/tests/test_assistant_documents.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from todo_backend.services.documents import (
    DOCUMENT_MAX_CHARS,
    DocumentEmptyError,
    extract_document_text,
)

_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 58>>stream
BT /F1 12 Tf 40 100 Td (Hello Plan) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
"""


def test_extracts_plain_text_and_markdown(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("周一例会 10:00", encoding="utf-8")
    md = tmp_path / "plan.md"
    md.write_text("# 计划\n- 买菜", encoding="utf-8")

    assert extract_document_text(txt) == "周一例会 10:00"
    assert "买菜" in extract_document_text(md)


def test_extracts_docx(tmp_path: Path) -> None:
    path = tmp_path / "schedule.docx"
    document = Document()
    document.add_paragraph("周三下午评审")
    document.save(path)

    assert "周三下午评审" in extract_document_text(path)


def test_extracts_pdf_text(tmp_path: Path) -> None:
    path = tmp_path / "hello.pdf"
    path.write_bytes(_MINIMAL_PDF)

    assert "Hello Plan" in extract_document_text(path)


def test_blank_pdf_raises_document_empty(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with path.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(DocumentEmptyError):
        extract_document_text(path)


def test_long_text_is_truncated(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text("x" * (DOCUMENT_MAX_CHARS + 100), encoding="utf-8")

    result = extract_document_text(path)

    assert len(result) == DOCUMENT_MAX_CHARS + len("\n...[TRUNCATED]")
    assert result.endswith("\n...[TRUNCATED]")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_documents.py -v`
Expected: FAIL — module `todo_backend.services.documents` missing.

- [ ] **Step 3: Implement the extraction service**

Create `backend/src/todo_backend/services/documents.py`:

```python
from pathlib import Path

from docx import Document
from pypdf import PdfReader

DOCUMENT_MAX_CHARS = 20_000
_TRUNCATION_MARKER = "\n...[TRUNCATED]"


class DocumentExtractionError(RuntimeError):
    pass


class DocumentEmptyError(DocumentExtractionError):
    pass


def extract_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text = _extract_pdf(path)
        elif suffix == ".docx":
            text = _extract_docx(path)
        else:  # .txt / .md
            text = path.read_text(encoding="utf-8")
    except DocumentExtractionError:
        raise
    except Exception as error:
        raise DocumentExtractionError("document could not be read") from error
    text = text.strip()
    if not text:
        raise DocumentEmptyError("document has no extractable text")
    if len(text) > DOCUMENT_MAX_CHARS:
        return text[:DOCUMENT_MAX_CHARS] + _TRUNCATION_MARKER
    return text


def _extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_documents.py -v && uv run --directory backend pyright`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/todo_backend/services/documents.py \
  backend/tests/test_assistant_documents.py
git commit -m "feat: extract text from uploaded documents"
```

---

### Task 5: Agent Tools

**Files:**
- Create: `backend/src/todo_backend/agent/tools.py`
- Test: `backend/tests/test_assistant_tools.py`

**Interfaces:**
- Consumes: Task 2 `ConversationsRepository`, existing `TaskRepository`/`ReminderRepository`.
- Produces: `TOOL_SCHEMAS: list[dict[str, Any]]` — OpenAI-format tool definitions for `list_tasks`, `get_task`, `propose_create_tasks`, `propose_update_task`, `propose_delete_task`.
- Produces: `AgentTools(database, conversation_id, message_id)` with `.execute(name, arguments) -> str` (JSON tool result) and `.created_proposal_ids: list[str]`.
- Consumed by: Task 6 orchestrator; Task 7 constructs it per turn.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assistant_tools.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import json
from pathlib import Path

import pytest

from todo_backend.agent.tools import TOOL_SCHEMAS, AgentTools
from todo_backend.database import Database
from todo_backend.models import CreateTaskCommand
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.tasks import TaskRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


@pytest.fixture
def seeded(database: Database) -> tuple[str, str]:
    conversations = ConversationsRepository()
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "", [], status="pending"
        )
    return conversation.id, message.id


def _tools(database: Database, conversation_id: str, message_id: str) -> AgentTools:
    return AgentTools(database, conversation_id=conversation_id, message_id=message_id)


def test_tool_schemas_cover_five_tools() -> None:
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert names == {
        "list_tasks",
        "get_task",
        "propose_create_tasks",
        "propose_update_task",
        "propose_delete_task",
    }


def test_list_tasks_filters(database: Database, seeded: tuple[str, str]) -> None:
    conversation_id, message_id = seeded
    tasks = TaskRepository()
    with database.transaction() as connection:
        tasks.create(connection, CreateTaskCommand(text="写周报", priority="high"))
        tasks.create(connection, CreateTaskCommand(text="买菜", priority="low"))

    tools = _tools(database, conversation_id, message_id)
    all_tasks = json.loads(tools.execute("list_tasks", {}))
    searched = json.loads(tools.execute("list_tasks", {"search": "周报"}))

    assert len(all_tasks["tasks"]) == 2
    assert [t["text"] for t in searched["tasks"]] == ["写周报"]


def test_propose_create_persists_proposals_only(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    tools = _tools(database, conversation_id, message_id)

    result = json.loads(
        tools.execute(
            "propose_create_tasks",
            {
                "items": [
                    {
                        "text": "明天下午三点开会",
                        "priority": "high",
                        "category": "work",
                        "time_start": "2026-07-21T15:00",
                    }
                ]
            },
        )
    )

    conversations = ConversationsRepository()
    with database.transaction() as connection:
        proposals = conversations.list_pending_proposals(connection, conversation_id)
        real_tasks = TaskRepository().list_all(connection)

    assert len(result["proposal_ids"]) == 1
    assert real_tasks == []  # propose 不动真实任务
    assert proposals[0].payload.text == "明天下午三点开会"
    assert proposals[0].payload.time_start == "2026-07-21T15:00"
    assert proposals[0].message_id == message_id
    assert tools.created_proposal_ids == result["proposal_ids"]


def test_propose_create_rejects_invalid_item(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    tools = _tools(database, conversation_id, message_id)

    result = json.loads(
        tools.execute("propose_create_tasks", {"items": [{"priority": "high"}]})
    )

    assert "error" in result


def test_propose_update_and_delete_target_existing_task(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    with database.transaction() as connection:
        task = TaskRepository().create(
            connection, CreateTaskCommand(text="旧标题", priority="low")
        )
    tools = _tools(database, conversation_id, message_id)

    updated = json.loads(
        tools.execute(
            "propose_update_task",
            {"task_id": task.id, "changes": {"text": "新标题", "time_start": None}},
        )
    )
    deleted = json.loads(tools.execute("propose_delete_task", {"task_id": task.id}))
    missing = json.loads(tools.execute("propose_delete_task", {"task_id": "nope"}))
    unknown = json.loads(tools.execute("does_not_exist", {}))

    conversations = ConversationsRepository()
    with database.transaction() as connection:
        proposals = conversations.list_pending_proposals(connection, conversation_id)

    assert "error" not in updated and "error" not in deleted
    assert "error" in missing and "error" in unknown
    by_action = {p.action: p for p in proposals}
    assert by_action["update"].payload.text == "新标题"
    assert "time_start" in by_action["update"].payload.model_fields_set  # 显式清除时间
    assert by_action["delete"].task_id == task.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_tools.py -v`
Expected: FAIL — module `todo_backend.agent.tools` missing.

- [ ] **Step 3: Implement the tool schemas and executors**

Create `backend/src/todo_backend/agent/tools.py`:

```python
import json
from typing import Any

from pydantic import ValidationError

from todo_backend.database import Database
from todo_backend.models import Priority, ProposalFields
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.reminders import ReminderRepository
from todo_backend.repositories.tasks import TaskRepository

_TASK_SUMMARY_CAP = 50

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "查询现有任务，可按完成状态、开始时间和标题关键词过滤",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "completed"],
                        "description": "完成状态过滤，默认 all",
                    },
                    "due_before": {
                        "type": "string",
                        "description": "本地时间 YYYY-MM-DDTHH:MM，只返回开始时间早于它的任务",
                    },
                    "due_after": {
                        "type": "string",
                        "description": "本地时间 YYYY-MM-DDTHH:MM，只返回开始时间晚于它的任务",
                    },
                    "search": {"type": "string", "description": "标题关键词"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task",
            "description": "读取单个任务的完整字段（含备注）",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_tasks",
            "description": "提议新建任务。只生成待用户确认的提议，不会直接创建任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "任务标题"},
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                                "category": {
                                    "type": "string",
                                    "enum": ["work", "study", "life", "other"],
                                },
                                "time_start": {
                                    "type": "string",
                                    "description": "开始时间，本地 YYYY-MM-DDTHH:MM",
                                },
                                "time_end": {
                                    "type": "string",
                                    "description": "结束时间，本地 YYYY-MM-DDTHH:MM",
                                },
                                "notes": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_update_task",
            "description": "提议修改现有任务字段。只生成待用户确认的提议。把字段设为 null 表示清除该字段",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "changes": {
                        "type": "object",
                        "properties": {
                            "text": {"type": ["string", "null"]},
                            "priority": {
                                "type": ["string", "null"],
                                "enum": ["low", "medium", "high", None],
                            },
                            "category": {
                                "type": ["string", "null"],
                                "enum": ["work", "study", "life", "other", None],
                            },
                            "time_start": {"type": ["string", "null"]},
                            "time_end": {"type": ["string", "null"]},
                            "notes": {"type": ["string", "null"]},
                        },
                    },
                },
                "required": ["task_id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_delete_task",
            "description": "提议删除现有任务。只生成待用户确认的提议",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
]


class AgentTools:
    def __init__(
        self,
        database: Database,
        *,
        conversation_id: str,
        message_id: str,
        task_repository: TaskRepository | None = None,
        reminder_repository: ReminderRepository | None = None,
        conversations: ConversationsRepository | None = None,
    ) -> None:
        self._database = database
        self._conversation_id = conversation_id
        self._message_id = message_id
        self._tasks = task_repository or TaskRepository()
        self._reminders = reminder_repository or ReminderRepository()
        self._conversations = conversations or ConversationsRepository()
        self.created_proposal_ids: list[str] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        handlers = {
            "list_tasks": self._list_tasks,
            "get_task": self._get_task,
            "propose_create_tasks": self._propose_create,
            "propose_update_task": self._propose_update,
            "propose_delete_task": self._propose_delete,
        }
        handler = handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            return handler(arguments)
        except (ValidationError, ValueError, TypeError, KeyError) as error:
            return json.dumps({"error": f"invalid arguments: {type(error).__name__}"})

    def _list_tasks(self, arguments: dict[str, Any]) -> str:
        connection = self._database.connect()
        try:
            tasks = self._tasks.list_all(connection)
        finally:
            connection.close()
        status = arguments.get("status", "all")
        if status == "active":
            tasks = [t for t in tasks if not t.completed]
        elif status == "completed":
            tasks = [t for t in tasks if t.completed]
        if arguments.get("search"):
            needle = str(arguments["search"])
            tasks = [t for t in tasks if needle in t.text]
        if arguments.get("due_before"):
            bound = str(arguments["due_before"])
            tasks = [t for t in tasks if t.time and t.time.start < bound]
        if arguments.get("due_after"):
            bound = str(arguments["due_after"])
            tasks = [t for t in tasks if t.time and t.time.start > bound]
        summaries = [
            {
                "id": t.id,
                "text": t.text,
                "completed": t.completed,
                "priority": t.priority,
                "category": t.category,
                "time_start": t.time.start if t.time else None,
                "time_end": t.time.end if t.time else None,
            }
            for t in tasks[:_TASK_SUMMARY_CAP]
        ]
        return json.dumps(
            {"tasks": summaries, "truncated": len(tasks) > _TASK_SUMMARY_CAP},
            ensure_ascii=False,
        )

    def _get_task(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        connection = self._database.connect()
        try:
            tasks = {t.id: t for t in self._tasks.list_all(connection)}
        finally:
            connection.close()
        task = tasks.get(task_id)
        if task is None:
            return json.dumps({"error": "task not found"})
        return task.model_dump_json()

    def _propose_create(self, arguments: dict[str, Any]) -> str:
        items = arguments.get("items") or []
        if not items:
            return json.dumps({"error": "items must not be empty"})
        proposal_ids: list[str] = []
        with self._database.transaction() as connection:
            for item in items:
                fields = ProposalFields.model_validate(item)
                if fields.text is None:
                    raise ValueError("text is required")
                if fields.priority is None:
                    fields.priority = Priority.__args__[1]  # "medium"
                if fields.category is None:
                    fields.category = "other"
                proposal = self._conversations.insert_proposal(
                    connection, self._conversation_id, self._message_id,
                    "create", None, fields,
                )
                proposal_ids.append(proposal.id)
        self.created_proposal_ids.extend(proposal_ids)
        return json.dumps({"proposal_ids": proposal_ids})

    def _propose_update(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        if not self._task_exists(task_id):
            return json.dumps({"error": "task not found"})
        changes = arguments.get("changes") or {}
        fields = ProposalFields.model_validate(changes)
        if not fields.model_fields_set:
            return json.dumps({"error": "changes must not be empty"})
        with self._database.transaction() as connection:
            proposal = self._conversations.insert_proposal(
                connection, self._conversation_id, self._message_id,
                "update", task_id, fields,
            )
        self.created_proposal_ids.append(proposal.id)
        return json.dumps({"proposal_ids": [proposal.id]})

    def _propose_delete(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        if not self._task_exists(task_id):
            return json.dumps({"error": "task not found"})
        with self._database.transaction() as connection:
            proposal = self._conversations.insert_proposal(
                connection, self._conversation_id, self._message_id,
                "delete", task_id, ProposalFields(),
            )
        self.created_proposal_ids.append(proposal.id)
        return json.dumps({"proposal_ids": [proposal.id]})

    def _task_exists(self, task_id: str) -> bool:
        connection = self._database.connect()
        try:
            return any(t.id == task_id for t in self._tasks.list_all(connection))
        finally:
            connection.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_tools.py -v && uv run --directory backend pyright && uv run --directory backend ruff check src tests`
Expected: PASS. (Note: `fields.priority = ...` mutates a validated model — if pyright complains, construct a replacement with `fields.model_copy(update={"priority": "medium"})` instead.)

- [ ] **Step 5: Commit**

```bash
git add backend/src/todo_backend/agent/tools.py backend/tests/test_assistant_tools.py
git commit -m "feat: add assistant agent tools"
```

---

### Task 6: Agent Orchestrator

**Files:**
- Create: `backend/src/todo_backend/agent/orchestrator.py`
- Test: `backend/tests/test_assistant_orchestrator.py`

**Interfaces:**
- Consumes: Task 3 `ArkClient`/`ArkChatResult`, Task 5 `AgentTools`/`TOOL_SCHEMAS`.
- Produces: `MAX_TOOL_ITERATIONS = 8`, `HISTORY_LIMIT = 20`.
- Produces: `AgentTurn(content: str, proposal_ids: list[str], tool_trace: list[dict], capped: bool)` (frozen dataclass).
- Produces: `AgentOrchestrator(ark, tools, *, language: str, now_local: str, pending_summary: str)` with `.system_prompt() -> str` and `.run(messages: list[dict]) -> AgentTurn`. `messages` is mutated in place (assistant/tool entries appended).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assistant_orchestrator.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Any
from unittest.mock import MagicMock

from todo_backend.agent.ark_client import ArkChatResult, ArkToolCall
from todo_backend.agent.orchestrator import MAX_TOOL_ITERATIONS, AgentOrchestrator


class _ScriptedArk:
    def __init__(self, results: list[ArkChatResult]) -> None:
        self._results = list(results)
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ArkChatResult:
        self.calls.append(list(messages))
        return self._results.pop(0)


def _final(text: str) -> ArkChatResult:
    return ArkChatResult(content=text, tool_calls=[], raw_message={"role": "assistant"})


def _tool_turn(call_id: str, name: str, arguments: dict[str, Any]) -> ArkChatResult:
    return ArkChatResult(
        content="",
        tool_calls=[ArkToolCall(id=call_id, name=name, arguments=arguments)],
        raw_message={
            "role": "assistant",
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": "{}"}}],
        },
    )


def _orchestrator(ark: _ScriptedArk) -> AgentOrchestrator:
    tools = MagicMock()
    tools.execute.return_value = '{"tasks": []}'
    tools.created_proposal_ids = ["p1"]
    return AgentOrchestrator(
        ark, tools, language="zh-CN",
        now_local="2026-07-20T09:30", pending_summary="- [p1] create: 买菜",
    )


def test_returns_final_text_when_model_stops() -> None:
    ark = _ScriptedArk([_final("好的")])
    turn = _orchestrator(ark).run([{"role": "user", "content": "你好"}])

    assert turn.content == "好的"
    assert turn.capped is False
    assert len(ark.calls) == 1


def test_tool_loop_appends_results_and_collects_proposals() -> None:
    ark = _ScriptedArk([_tool_turn("c1", "list_tasks", {}), _final("查到 0 条任务")])
    orchestrator = _orchestrator(ark)

    turn = orchestrator.run([{"role": "user", "content": "我有哪些任务"}])

    assert turn.content == "查到 0 条任务"
    assert turn.proposal_ids == ["p1"]
    assert turn.tool_trace == [{"name": "list_tasks", "arguments": {}, "output": '{"tasks": []}'}]
    second_call_messages = ark.calls[1]
    assert second_call_messages[-1] == {
        "role": "tool", "tool_call_id": "c1", "content": '{"tasks": []}',
    }
    assert second_call_messages[-2]["tool_calls"][0]["id"] == "c1"


def test_loop_is_capped_and_returns_fallback() -> None:
    ark = _ScriptedArk(
        [_tool_turn(f"c{i}", "list_tasks", {}) for i in range(MAX_TOOL_ITERATIONS)]
    )
    turn = _orchestrator(ark).run([{"role": "user", "content": "循环"}])

    assert turn.capped is True
    assert "上限" in turn.content
    assert len(ark.calls) == MAX_TOOL_ITERATIONS


def test_system_prompt_contains_time_and_pending_summary() -> None:
    prompt = _orchestrator(_ScriptedArk([])).system_prompt()

    assert "2026-07-20T09:30" in prompt
    assert "[p1] create: 买菜" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_orchestrator.py -v`
Expected: FAIL — module `todo_backend.agent.orchestrator` missing.

- [ ] **Step 3: Implement the orchestrator**

Create `backend/src/todo_backend/agent/orchestrator.py`:

```python
from dataclasses import dataclass, field
from typing import Any, Protocol

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.agent.tools import TOOL_SCHEMAS, AgentTools

MAX_TOOL_ITERATIONS = 8
HISTORY_LIMIT = 20

_SYSTEM_PROMPTS = {
    "zh-CN": (
        "你是 TodoList 应用的待办助手。当前本地时间：{now}。\n"
        "规则：\n"
        "1. 创建、修改或删除任务时，必须调用对应的 propose_ 工具生成提议，"
        "不要声称已直接执行。\n"
        "2. 所有时间使用本地时间，格式 YYYY-MM-DDTHH:MM。\n"
        "3. 使用与用户最近一条消息相同的语言回复。\n"
        "4. 需要了解现有任务时，先调用 list_tasks 查询。\n"
        "当前待用户确认的提议：\n{pending}"
    ),
    "en": (
        "You are the todo assistant inside the TodoList app. Current local time: {now}.\n"
        "Rules:\n"
        "1. To create, update, or delete tasks you MUST call the matching propose_ tool; "
        "never claim you did it directly.\n"
        "2. All times are local, formatted YYYY-MM-DDTHH:MM.\n"
        "3. Reply in the language of the user's latest message.\n"
        "4. Call list_tasks first whenever you need existing tasks.\n"
        "Proposals awaiting user confirmation:\n{pending}"
    ),
}

_FALLBACK = {
    "zh-CN": "分析过程超出了处理上限，请换个方式描述需求。",
    "en": "The analysis exceeded the processing limit. Please rephrase your request.",
}


class _Ark(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ArkChatResult: ...


@dataclass(frozen=True)
class AgentTurn:
    content: str
    proposal_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    capped: bool = False


class AgentOrchestrator:
    def __init__(
        self,
        ark: _Ark,
        tools: AgentTools,
        *,
        language: str,
        now_local: str,
        pending_summary: str,
    ) -> None:
        self._ark = ark
        self._tools = tools
        self._language = language
        self._now_local = now_local
        self._pending_summary = pending_summary

    def system_prompt(self) -> str:
        template = _SYSTEM_PROMPTS.get(self._language, _SYSTEM_PROMPTS["en"])
        return template.format(now=self._now_local, pending=self._pending_summary or "无")

    def run(self, messages: list[dict[str, Any]]) -> AgentTurn:
        trace: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ITERATIONS):
            result = self._ark.chat(messages, tools=TOOL_SCHEMAS)
            if not result.tool_calls:
                return AgentTurn(
                    content=result.content,
                    proposal_ids=list(self._tools.created_proposal_ids),
                    tool_trace=trace,
                )
            messages.append(result.raw_message)
            for call in result.tool_calls:
                output = self._tools.execute(call.name, call.arguments)
                trace.append(
                    {"name": call.name, "arguments": call.arguments, "output": output}
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": output}
                )
        return AgentTurn(
            content=_FALLBACK.get(self._language, _FALLBACK["en"]),
            proposal_ids=list(self._tools.created_proposal_ids),
            tool_trace=trace,
            capped=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_orchestrator.py -v && uv run --directory backend pyright`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/todo_backend/agent/orchestrator.py backend/tests/test_assistant_orchestrator.py
git commit -m "feat: add assistant agent orchestrator"
```

---

### Task 7: Assistant Service

**Files:**
- Create: `backend/src/todo_backend/services/assistant.py`
- Modify: `backend/src/todo_backend/repositories/conversations.py` (add `update_message_attachments`)
- Modify: `backend/src/todo_backend/models.py` (wire commands/responses)
- Test: `backend/tests/test_assistant_service.py`

**Interfaces:**
- Consumes: Tasks 1–6; existing `TaskRepository`, `ReminderRepository`.
- Produces service errors: `AssistantNotConfiguredError`, `AssistantUnavailableError`, `UnsupportedFileTypeError`, `UploadTooLargeError`, `UploadNotFoundError`, `ProposalAlreadyResolvedError`.
- Produces: `UPLOAD_RULES` — image {.jpg/.jpeg/.png/.webp, 10MB}, document {.pdf/.docx/.txt/.md, 10MB}, audio {.mp3/.wav/.m4a, 25MB}; `MAX_UPLOAD_BYTES = 25 * 1024 * 1024`.
- Produces: `AssistantService(database, settings, *, ark_factory=None)` methods: `create_conversation()`, `list_conversations()`, `get_conversation_detail(id)`, `delete_conversation(id)`, `save_upload(filename, data) -> AssistantAttachment`, `transcribe(command) -> str`, `send_message(id, command) -> AssistantTurnResponse`, `accept_proposal(id) -> tuple[AssistantProposal, Task | None]`, `reject_proposal(id) -> AssistantProposal`, `get_settings_view()`, `patch_settings(command) -> AssistantSettingsView`.
- Produces wire models: `SendAssistantMessageCommand`, `TranscribeCommand`, `AssistantTurnResponse`, `AssistantConversationDetail`, `AssistantConversationListResponse`, `AssistantProposalResolveResponse`, `UploadResponse`, `TranscribeResponse`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assistant_service.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

import pytest

from todo_backend.agent.ark_client import ArkChatResult, ArkToolCall, ArkUnavailableError
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantAttachment,
    AssistantSettingsPatchCommand,
    SendAssistantMessageCommand,
    TranscribeCommand,
)
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.assistant import (
    AssistantNotConfiguredError,
    AssistantService,
    ProposalAlreadyResolvedError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
)


class _FakeArk:
    def __init__(self, results=None, transcription="转写结果") -> None:
        self._results = list(results or [])
        self.transcription = transcription

    def chat(self, messages, tools=None):
        return self._results.pop(0)

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        return self.transcription


@pytest.fixture
def service(tmp_path: Path) -> AssistantService:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    svc = AssistantService(database, settings, ark_factory=lambda _s: _FAKE_ARK)
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_settings (id, theme, muted, shortcut)"
            " VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT')"
        )
    return svc


_FAKE_ARK = _FakeArk()


def _configure(service: AssistantService) -> None:
    service.patch_settings(AssistantSettingsPatchCommand(apiKey="sk-test"))


def test_send_message_requires_api_key(service: AssistantService) -> None:
    conversation = service.create_conversation()
    with pytest.raises(AssistantNotConfiguredError):
        service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))


def test_send_message_persists_turn(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk([ArkChatResult(content="你好！我可以帮你规划。", tool_calls=[])])
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))

    detail = service.get_conversation_detail(conversation.id)
    assert turn.message.content == "你好！我可以帮你规划。"
    assert turn.message.status == "done"
    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert detail.conversation.title == "你好"


def test_proposal_accept_creates_real_task(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk([
        ArkChatResult(
            content="",
            tool_calls=[ArkToolCall(id="c1", name="propose_create_tasks", arguments={
                "items": [{"text": "明天下午三点开会", "priority": "high",
                           "time_start": "2026-07-21T15:00"}],
            })],
            raw_message={"role": "assistant", "tool_calls": []},
        ),
        ArkChatResult(content="已整理好提议", tool_calls=[]),
    ])
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="安排会议"))
    assert len(turn.proposals) == 1

    proposal, task = service.accept_proposal(turn.proposals[0].id)

    assert proposal.status == "accepted"
    assert task is not None and task.text == "明天下午三点开会"
    with service.database.transaction() as connection:
        assert len(TaskRepository().list_all(connection)) == 1

    with pytest.raises(ProposalAlreadyResolvedError):
        service.accept_proposal(turn.proposals[0].id)


def test_failed_ark_marks_message_failed(service: AssistantService) -> None:
    _configure(service)

    class _BrokenArk:
        def chat(self, messages, tools=None):
            raise ArkUnavailableError("down")

        def transcribe(self, a, b):
            raise ArkUnavailableError("down")

    global _FAKE_ARK
    _FAKE_ARK = _BrokenArk()
    conversation = service.create_conversation()

    turn = service.send_message(conversation.id, SendAssistantMessageCommand(content="你好"))

    assert turn.message.status == "failed"
    assert turn.message.content == ""


def test_audio_message_is_transcribed_into_attachment(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk(
        [ArkChatResult(content="已记录", tool_calls=[])], transcription="明天买菜"
    )
    conversation = service.create_conversation()
    attachment = service.save_upload("voice.wav", b"RIFF....")

    turn = service.send_message(
        conversation.id,
        SendAssistantMessageCommand(content="", attachments=[attachment]),
    )

    detail = service.get_conversation_detail(conversation.id)
    user_message = detail.messages[0]
    assert turn.message.status == "done"
    assert user_message.attachments[0].extracted_text == "明天买菜"


def test_upload_validation(service: AssistantService) -> None:
    saved = service.save_upload("截图.png", b"\x89PNG")
    assert saved.kind == "image"
    assert saved.file_id.endswith(".png")

    with pytest.raises(UnsupportedFileTypeError):
        service.save_upload("evil.exe", b"MZ")
    with pytest.raises(UploadTooLargeError):
        service.save_upload("big.png", b"x" * (10 * 1024 * 1024 + 1))


def test_transcribe_endpoint_flow(service: AssistantService) -> None:
    _configure(service)
    global _FAKE_ARK
    _FAKE_ARK = _FakeArk(transcription="识别文字")
    attachment = service.save_upload("voice.mp3", b"ID3....")

    assert service.transcribe(TranscribeCommand(fileId=attachment.file_id)) == "识别文字"


def test_settings_view_masks_api_key(service: AssistantService) -> None:
    empty = service.get_settings_view()
    assert empty.has_api_key is False

    _configure(service)
    view = service.get_settings_view()

    assert view.has_api_key is True
    assert not hasattr(view, "api_key")
```

Note: the module-level `_FAKE_ARK` + `global` pattern keeps the fixture simple; the executor may instead use `pytest` monkeypatching — the assertions are what matter.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_service.py -v`
Expected: FAIL — module `todo_backend.services.assistant` missing.

- [ ] **Step 3: Implement the service and wire models**

Append to `backend/src/todo_backend/models.py`:

```python
class SendAssistantMessageCommand(WireModel):
    content: Annotated[str, Field(strict=True, max_length=10_000)] = ""
    attachments: list[AssistantAttachment] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "SendAssistantMessageCommand":
        if not self.content.strip() and not self.attachments:
            raise ValueError("message requires content or attachments")
        return self


class TranscribeCommand(WireModel):
    file_id: Annotated[str, Field(strict=True, min_length=1, max_length=200)] = Field(
        alias="fileId"
    )


class AssistantTurnResponse(WireModel):
    message: AssistantMessage
    proposals: list[AssistantProposal]


class AssistantConversationDetail(WireModel):
    conversation: AssistantConversationSummary
    messages: list[AssistantMessage]
    proposals: list[AssistantProposal]


class AssistantConversationListResponse(WireModel):
    conversations: list[AssistantConversationSummary]


class AssistantProposalResolveResponse(WireModel):
    proposal: AssistantProposal
    task: Task | None = None


class UploadResponse(WireModel):
    file_id: str = Field(alias="fileId")
    kind: AttachmentKind
    name: str
    mime: str


class TranscribeResponse(WireModel):
    text: str
```

Append to `backend/src/todo_backend/repositories/conversations.py` (new method on `ConversationsRepository`):

```python
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
```

Create `backend/src/todo_backend/services/assistant.py`:

```python
import base64
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError
from todo_backend.agent.orchestrator import HISTORY_LIMIT, AgentOrchestrator, AgentTurn
from todo_backend.agent.tools import AgentTools
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantAttachment,
    AssistantConversationDetail,
    AssistantConversationSummary,
    AssistantMessage,
    AssistantProposal,
    AssistantSettings,
    AssistantSettingsPatchCommand,
    AssistantSettingsView,
    AssistantTurnResponse,
    CreateTaskCommand,
    SendAssistantMessageCommand,
    Task,
    TimeField,
    TranscribeCommand,
    UpdateTaskCommand,
)
from todo_backend.repositories.assistant_settings import AssistantSettingsRepository
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.reminders import ReminderRepository
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.documents import extract_document_text

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_RULES: dict[str, tuple[set[str], int]] = {
    "image": ({".jpg", ".jpeg", ".png", ".webp"}, 10 * 1024 * 1024),
    "document": ({".pdf", ".docx", ".txt", ".md"}, 10 * 1024 * 1024),
    "audio": ({".mp3", ".wav", ".m4a"}, 25 * 1024 * 1024),
}
_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain", ".md": "text/markdown",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/m4a",
}
_AUDIO_FORMAT_BY_EXT = {".mp3": "mp3", ".wav": "wav", ".m4a": "m4a"}
_TITLE_LENGTH = 30


class AssistantNotConfiguredError(RuntimeError):
    pass


class AssistantUnavailableError(RuntimeError):
    pass


class UnsupportedFileTypeError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class UploadNotFoundError(LookupError):
    pass


class ProposalAlreadyResolvedError(RuntimeError):
    pass


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class AssistantService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        ark_factory: Callable[[AssistantSettings], Any] | None = None,
    ) -> None:
        self.database = database
        self._settings = settings
        self._conversations = ConversationsRepository()
        self._assistant_settings = AssistantSettingsRepository()
        self._tasks = TaskRepository()
        self._reminders = ReminderRepository()
        self._ark_factory = ark_factory or (
            lambda cfg: ArkClient(cfg.api_key, cfg.chat_model, cfg.audio_model)
        )

    @property
    def _uploads_dir(self) -> Path:
        return self._settings.database_path.parent / "assistant_uploads"

    # ---- settings ----

    def get_settings_view(self) -> AssistantSettingsView:
        with self.database.transaction() as connection:
            config = self._assistant_settings.get(connection)
        return self._view(config)

    def patch_settings(
        self, command: AssistantSettingsPatchCommand
    ) -> AssistantSettingsView:
        with self.database.transaction() as connection:
            config = self._assistant_settings.patch(connection, command)
        return self._view(config)

    def _view(self, config: AssistantSettings) -> AssistantSettingsView:
        return AssistantSettingsView(
            hasApiKey=bool(config.api_key),
            chatModel=config.chat_model,
            audioModel=config.audio_model,
        )

    def _require_ark(self) -> Any:
        with self.database.transaction() as connection:
            config = self._assistant_settings.get(connection)
        if not config.api_key:
            raise AssistantNotConfiguredError
        return self._ark_factory(config)

    # ---- conversations ----

    def create_conversation(self) -> AssistantConversationSummary:
        with self.database.transaction() as connection:
            return self._conversations.create_conversation(connection, "")

    def list_conversations(self) -> list[AssistantConversationSummary]:
        with self.database.transaction() as connection:
            return self._conversations.list_conversations(connection)

    def get_conversation_detail(self, conversation_id: str) -> AssistantConversationDetail:
        with self.database.transaction() as connection:
            return AssistantConversationDetail(
                conversation=self._conversations.get_conversation(connection, conversation_id),
                messages=self._conversations.list_messages(connection, conversation_id),
                proposals=self._conversations.list_proposals(connection, conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self.database.transaction() as connection:
            file_ids = self._conversations.list_conversation_file_ids(
                connection, conversation_id
            )
            self._conversations.delete_conversation(connection, conversation_id)
        for file_id in file_ids:
            (self._uploads_dir / file_id).unlink(missing_ok=True)

    # ---- uploads & transcription ----

    def save_upload(self, filename: str, data: bytes) -> AssistantAttachment:
        suffix = Path(filename).suffix.lower()
        rule = next(
            ((kind, limit) for kind, (exts, limit) in UPLOAD_RULES.items() if suffix in exts),
            None,
        )
        if rule is None:
            raise UnsupportedFileTypeError
        kind, limit = rule
        if len(data) > limit:
            raise UploadTooLargeError
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        file_id = f"{uuid.uuid4().hex}{suffix}"
        (self._uploads_dir / file_id).write_bytes(data)
        return AssistantAttachment(
            fileId=file_id, kind=kind, name=filename[:255], mime=_MIME_BY_EXT[suffix],
        )

    def transcribe(self, command: TranscribeCommand) -> str:
        ark = self._require_ark()
        path, audio_format = self._audio_path(command.file_id)
        audio_base64 = base64.b64encode(path.read_bytes()).decode()
        try:
            return ark.transcribe(audio_base64, audio_format)
        except ArkUnavailableError as error:
            raise AssistantUnavailableError from error

    def _audio_path(self, file_id: str) -> tuple[Path, str]:
        path = self._uploads_dir / file_id
        audio_format = _AUDIO_FORMAT_BY_EXT.get(path.suffix.lower())
        if audio_format is None:
            raise UnsupportedFileTypeError
        if not path.is_file():
            raise UploadNotFoundError
        return path, audio_format

    # ---- agent turn ----

    def send_message(
        self, conversation_id: str, command: SendAssistantMessageCommand
    ) -> AssistantTurnResponse:
        ark = self._require_ark()
        attachments = [self._verified_attachment(a) for a in command.attachments]
        attachments = [self._enrich_document(a) for a in attachments]

        with self.database.transaction() as connection:
            conversation = self._conversations.get_conversation(connection, conversation_id)
            user_message = self._conversations.insert_message(
                connection, conversation_id, "user", command.content, attachments,
            )
            assistant_message = self._conversations.insert_message(
                connection, conversation_id, "assistant", "", [], status="pending",
            )
            if not conversation.title:
                title_source = command.content.strip() or (
                    attachments[0].name if attachments else ""
                )
                connection.execute(
                    "UPDATE assistant_conversations SET title = ? WHERE id = ?",
                    (title_source[:_TITLE_LENGTH], conversation_id),
                )
            self._conversations.touch(connection, conversation_id)

        try:
            enriched = [self._enrich_audio(ark, a) for a in attachments]
            if enriched != attachments:
                with self.database.transaction() as connection:
                    self._conversations.update_message_attachments(
                        connection, user_message.id, enriched
                    )
            turn = self._run_agent(ark, conversation_id, assistant_message.id)
        except ArkUnavailableError:
            with self.database.transaction() as connection:
                self._conversations.update_message(
                    connection, assistant_message.id,
                    content="", status="failed", tool_trace=None,
                )
            failed = AssistantMessage(
                id=assistant_message.id, role="assistant", content="",
                attachments=[], status="failed", createdAt=assistant_message.created_at,
            )
            return AssistantTurnResponse(message=failed, proposals=[])

        with self.database.transaction() as connection:
            self._conversations.update_message(
                connection, assistant_message.id,
                content=turn.content, status="done",
                tool_trace=json.dumps(turn.tool_trace, ensure_ascii=False),
            )
            proposals = [
                self._conversations.get_proposal(connection, proposal_id)
                for proposal_id in turn.proposal_ids
            ]
        done = AssistantMessage(
            id=assistant_message.id, role="assistant", content=turn.content,
            attachments=[], status="done", createdAt=assistant_message.created_at,
        )
        return AssistantTurnResponse(message=done, proposals=proposals)

    def _verified_attachment(self, attachment: AssistantAttachment) -> AssistantAttachment:
        path = self._uploads_dir / attachment.file_id
        if not path.is_file():
            raise UploadNotFoundError
        suffix = path.suffix.lower()
        kind = next(
            (kind for kind, (exts, _limit) in UPLOAD_RULES.items() if suffix in exts), None
        )
        if kind is None:
            raise UnsupportedFileTypeError
        return attachment.model_copy(update={"kind": kind, "extracted_text": None})

    def _enrich_document(self, attachment: AssistantAttachment) -> AssistantAttachment:
        if attachment.kind != "document":
            return attachment
        text = extract_document_text(self._uploads_dir / attachment.file_id)
        return attachment.model_copy(update={"extracted_text": text})

    def _enrich_audio(self, ark: Any, attachment: AssistantAttachment) -> AssistantAttachment:
        if attachment.kind != "audio":
            return attachment
        path, audio_format = self._audio_path(attachment.file_id)
        audio_base64 = base64.b64encode(path.read_bytes()).decode()
        text = ark.transcribe(audio_base64, audio_format)
        return attachment.model_copy(update={"extracted_text": text})

    def _run_agent(
        self,
        ark: Any,
        conversation_id: str,
        assistant_message_id: str,
    ) -> AgentTurn:
        with self.database.transaction() as connection:
            messages = self._conversations.list_messages(connection, conversation_id)
            pending = self._conversations.list_pending_proposals(connection, conversation_id)
            language = connection.execute(
                "SELECT language FROM app_settings WHERE id = 1"
            ).fetchone()["language"]
        tools = AgentTools(
            self.database,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
        )
        orchestrator = AgentOrchestrator(
            ark,
            tools,
            language=language,
            now_local=time.strftime("%Y-%m-%dT%H:%M"),
            pending_summary=self._pending_summary(pending),
        )
        history = [{"role": "system", "content": orchestrator.system_prompt()}]
        history.extend(self._build_ark_messages(messages))
        return orchestrator.run(history)

    def _build_ark_messages(
        self, messages: list[AssistantMessage]
    ) -> list[dict[str, Any]]:
        ark_messages: list[dict[str, Any]] = []
        for message in messages[-HISTORY_LIMIT:]:
            if message.role == "assistant":
                if message.status == "done" and message.content:
                    ark_messages.append({"role": "assistant", "content": message.content})
                continue
            parts: list[dict[str, Any]] = []
            text = message.content
            for attachment in message.attachments:
                if attachment.kind == "image":
                    path = self._uploads_dir / attachment.file_id
                    encoded = base64.b64encode(path.read_bytes()).decode()
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{attachment.mime};base64,{encoded}"},
                    })
                elif attachment.extracted_text:
                    text += f"\n\n〈{attachment.name}〉\n{attachment.extracted_text}"
            parts.append({"type": "text", "text": text or "（附件消息）"})
            ark_messages.append({"role": "user", "content": parts})
        return ark_messages

    def _pending_summary(self, pending: list[AssistantProposal]) -> str:
        lines = []
        for proposal in pending:
            label = proposal.payload.text or proposal.task_id or ""
            lines.append(f"- [{proposal.id}] {proposal.action}: {label}")
        return "\n".join(lines)

    # ---- proposals ----

    def accept_proposal(
        self, proposal_id: str
    ) -> tuple[AssistantProposal, Task | None]:
        with self.database.transaction() as connection:
            proposal = self._conversations.get_proposal(connection, proposal_id)
            if proposal.status != "pending":
                raise ProposalAlreadyResolvedError
            task: Task | None = None
            if proposal.action == "create":
                task = self._tasks.create(
                    connection,
                    CreateTaskCommand(
                        text=proposal.payload.text or "",
                        priority=proposal.payload.priority or "medium",
                        category=proposal.payload.category or "other",
                        time=self._time_field(proposal.payload),
                        notes=proposal.payload.notes,
                    ),
                )
            elif proposal.action == "update":
                task = self._tasks.update(
                    connection,
                    proposal.task_id or "",
                    UpdateTaskCommand(**self._update_kwargs(proposal.payload)),
                )
                if {"time_start", "time_end"} & proposal.payload.model_fields_set:
                    self._reminders.prune_stale(
                        connection,
                        task.id,
                        task.time.start if task.time else None,
                    )
            else:
                self._tasks.delete(connection, proposal.task_id or "")
            resolved = self._conversations.mark_proposal(
                connection, proposal_id, "accepted", _now_ms()
            )
        return resolved, task

    def reject_proposal(self, proposal_id: str) -> AssistantProposal:
        with self.database.transaction() as connection:
            proposal = self._conversations.get_proposal(connection, proposal_id)
            if proposal.status != "pending":
                raise ProposalAlreadyResolvedError
            return self._conversations.mark_proposal(
                connection, proposal_id, "rejected", _now_ms()
            )

    def _time_field(self, payload: Any) -> TimeField | None:
        if not payload.time_start:
            return None
        return TimeField(start=payload.time_start, end=payload.time_end)

    def _update_kwargs(self, payload: Any) -> dict[str, Any]:
        fields_set = payload.model_fields_set
        kwargs: dict[str, Any] = {}
        for name in ("text", "priority", "category"):
            value = getattr(payload, name)
            if name in fields_set and value is not None:
                kwargs[name] = value
        if "notes" in fields_set:
            kwargs["notes"] = payload.notes
        if {"time_start", "time_end"} & fields_set:
            kwargs["time"] = (
                TimeField(start=payload.time_start, end=payload.time_end)
                if payload.time_start
                else None
            )
        return kwargs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest tests/test_assistant_service.py -v && uv run --directory backend pyright && uv run --directory backend ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/todo_backend/models.py backend/src/todo_backend/services/assistant.py \
  backend/src/todo_backend/repositories/conversations.py backend/tests/test_assistant_service.py
git commit -m "feat: add assistant service with agent turn and proposals"
```

---

### Task 8: Assistant API Routes

**Files:**
- Create: `backend/src/todo_backend/assistant_api.py`
- Modify: `backend/src/todo_backend/api.py` (mount router, register handlers, accept `assistant_service`)
- Modify: `backend/pyproject.toml` (+ `python-multipart`)
- Test: `backend/tests/test_assistant_api.py`

**Interfaces:**
- Consumes: Task 7 `AssistantService` and its errors; Task 2 repo errors.
- Produces: routes under `/api/v1/assistant/` (see table in spec §5) plus error codes `ASSISTANT_NOT_CONFIGURED` (409), `ASSISTANT_UNAVAILABLE` (503), `UNSUPPORTED_FILE_TYPE` (415), `UPLOAD_TOO_LARGE` (413), `UPLOAD_NOT_FOUND` (404), `CONVERSATION_NOT_FOUND` (404), `PROPOSAL_NOT_FOUND` (404), `PROPOSAL_ALREADY_RESOLVED` (409), `DOCUMENT_NOT_READABLE` (422).
- Produces: `create_app(settings, database, assistant_service=None)` — new optional parameter.

- [ ] **Step 1: Add dependency and write the failing tests**

Run: `uv add --directory backend python-multipart`

Create `backend/tests/test_assistant_api.py`:

```python
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.services.assistant import AssistantService

_HEADERS = {"Authorization": "Bearer test-token"}


class _FakeArk:
    def chat(self, messages, tools=None):
        return ArkChatResult(content="你好！", tool_calls=[])

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        return "转写文本"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    service = AssistantService(database, settings, ark_factory=lambda _s: _FakeArk())
    with TestClient(
        create_app(settings=settings, database=database, assistant_service=service)
    ) as test_client:
        test_client.post(
            "/api/v1/bootstrap", headers=_HEADERS, json={"preferredTheme": "workspace-light"}
        )
        yield test_client


def _configure_key(client: TestClient) -> None:
    response = client.put(
        "/api/v1/assistant/settings", headers=_HEADERS, json={"apiKey": "sk-test"}
    )
    assert response.status_code == 200


def test_settings_roundtrip_masks_key(client: TestClient) -> None:
    empty = client.get("/api/v1/assistant/settings", headers=_HEADERS)
    assert empty.status_code == 200
    assert empty.json()["hasApiKey"] is False

    _configure_key(client)
    view = client.get("/api/v1/assistant/settings", headers=_HEADERS)

    assert view.json()["hasApiKey"] is True
    assert "apiKey" not in view.json()
    assert view.json()["chatModel"] == "doubao-seed-2-1-pro-260628"


def test_send_message_without_key_returns_409(client: TestClient) -> None:
    created = client.post("/api/v1/assistant/conversations", headers=_HEADERS)
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"content": "你好", "attachments": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSISTANT_NOT_CONFIGURED"


def test_full_text_turn_over_http(client: TestClient) -> None:
    _configure_key(client)
    created = client.post("/api/v1/assistant/conversations", headers=_HEADERS)
    conversation_id = created.json()["id"]

    turn = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"content": "你好", "attachments": []},
    )
    assert turn.status_code == 200
    assert turn.json()["message"]["content"] == "你好！"

    detail = client.get(
        f"/api/v1/assistant/conversations/{conversation_id}", headers=_HEADERS
    )
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]

    listed = client.get("/api/v1/assistant/conversations", headers=_HEADERS)
    assert listed.json()["conversations"][0]["title"] == "你好"


def test_upload_and_transcribe_over_http(client: TestClient) -> None:
    _configure_key(client)
    upload = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("voice.wav", b"RIFF fake", "audio/wav")},
    )
    assert upload.status_code == 201
    assert upload.json()["kind"] == "audio"

    transcribed = client.post(
        "/api/v1/assistant/transcribe",
        headers=_HEADERS,
        json={"fileId": upload.json()["fileId"]},
    )
    assert transcribed.status_code == 200
    assert transcribed.json()["text"] == "转写文本"


def test_upload_rejects_bad_type_and_oversize(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 415

    big = client.post(
        "/api/v1/assistant/uploads",
        headers=_HEADERS,
        files={"file": ("big.wav", b"x" * (25 * 1024 * 1024 + 1), "audio/wav")},
    )
    assert big.status_code == 413


def test_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations/nope", headers=_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_assistant_routes_require_token(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/conversations")
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/test_assistant_api.py -v`
Expected: FAIL — `create_app()` has no `assistant_service` parameter; routes 404.

- [ ] **Step 3: Implement the router and wire it into `create_app`**

Create `backend/src/todo_backend/assistant_api.py`:

```python
from fastapi import APIRouter, File, Response, UploadFile, status

from todo_backend.models import (
    AssistantConversationDetail,
    AssistantConversationListResponse,
    AssistantConversationSummary,
    AssistantProposalResolveResponse,
    AssistantSettingsPatchCommand,
    AssistantSettingsView,
    AssistantTurnResponse,
    SendAssistantMessageCommand,
    TranscribeCommand,
    TranscribeResponse,
    UploadResponse,
)
from todo_backend.services.assistant import MAX_UPLOAD_BYTES, AssistantService


def build_assistant_router(service: AssistantService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/assistant/conversations",
        response_model=AssistantConversationSummary,
        status_code=status.HTTP_201_CREATED,
    )
    def _create_conversation() -> AssistantConversationSummary:
        return service.create_conversation()

    @router.get(
        "/assistant/conversations",
        response_model=AssistantConversationListResponse,
    )
    def _list_conversations() -> AssistantConversationListResponse:
        return AssistantConversationListResponse(
            conversations=service.list_conversations()
        )

    @router.get(
        "/assistant/conversations/{conversation_id}",
        response_model=AssistantConversationDetail,
        response_model_exclude_none=True,
    )
    def _get_conversation(conversation_id: str) -> AssistantConversationDetail:
        return service.get_conversation_detail(conversation_id)

    @router.delete("/assistant/conversations/{conversation_id}", status_code=204)
    def _delete_conversation(conversation_id: str) -> Response:
        service.delete_conversation(conversation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/assistant/conversations/{conversation_id}/messages",
        response_model=AssistantTurnResponse,
    )
    def _send_message(
        conversation_id: str, command: SendAssistantMessageCommand
    ) -> AssistantTurnResponse:
        return service.send_message(conversation_id, command)

    @router.post(
        "/assistant/uploads",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def _upload(file: UploadFile = File(...)) -> UploadResponse:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        attachment = service.save_upload(file.filename or "upload", data)
        return UploadResponse(
            fileId=attachment.file_id,
            kind=attachment.kind,
            name=attachment.name,
            mime=attachment.mime,
        )

    @router.post("/assistant/transcribe", response_model=TranscribeResponse)
    def _transcribe(command: TranscribeCommand) -> TranscribeResponse:
        return TranscribeResponse(text=service.transcribe(command))

    @router.post(
        "/assistant/proposals/{proposal_id}/accept",
        response_model=AssistantProposalResolveResponse,
        response_model_exclude_none=True,
    )
    def _accept_proposal(proposal_id: str) -> AssistantProposalResolveResponse:
        proposal, task = service.accept_proposal(proposal_id)
        return AssistantProposalResolveResponse(proposal=proposal, task=task)

    @router.post(
        "/assistant/proposals/{proposal_id}/reject",
        response_model=AssistantProposalResolveResponse,
        response_model_exclude_none=True,
    )
    def _reject_proposal(proposal_id: str) -> AssistantProposalResolveResponse:
        return AssistantProposalResolveResponse(
            proposal=service.reject_proposal(proposal_id), task=None
        )

    @router.get("/assistant/settings", response_model=AssistantSettingsView)
    def _get_settings() -> AssistantSettingsView:
        return service.get_settings_view()

    @router.put("/assistant/settings", response_model=AssistantSettingsView)
    def _put_settings(command: AssistantSettingsPatchCommand) -> AssistantSettingsView:
        return service.patch_settings(command)

    return router
```

Modify `backend/src/todo_backend/api.py`:

1. Add imports:

```python
from todo_backend.assistant_api import build_assistant_router
from todo_backend.repositories.conversations import (
    ConversationNotFoundError,
    ProposalNotFoundError,
)
from todo_backend.services.assistant import (
    AssistantNotConfiguredError,
    AssistantService,
    AssistantUnavailableError,
    ProposalAlreadyResolvedError,
    UnsupportedFileTypeError,
    UploadNotFoundError,
    UploadTooLargeError,
)
from todo_backend.services.documents import DocumentExtractionError
```

2. Change the signature and build the service:

```python
def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    assistant_service: AssistantService | None = None,
) -> FastAPI:
    ...
    settings_service = SettingsService(resolved_database)
    resolved_assistant_service = assistant_service or AssistantService(
        resolved_database, resolved_settings
    )
```

3. Register handlers next to the existing ones:

```python
    app.add_exception_handler(AssistantNotConfiguredError, _assistant_not_configured_handler)
    app.add_exception_handler(AssistantUnavailableError, _assistant_unavailable_handler)
    app.add_exception_handler(UnsupportedFileTypeError, _unsupported_file_type_handler)
    app.add_exception_handler(UploadTooLargeError, _upload_too_large_handler)
    app.add_exception_handler(UploadNotFoundError, _upload_not_found_handler)
    app.add_exception_handler(ConversationNotFoundError, _conversation_not_found_handler)
    app.add_exception_handler(ProposalNotFoundError, _proposal_not_found_handler)
    app.add_exception_handler(ProposalAlreadyResolvedError, _proposal_resolved_handler)
    app.add_exception_handler(DocumentExtractionError, _document_not_readable_handler)
```

4. Mount the router just before `app.include_router(router)`:

```python
    router.include_router(build_assistant_router(resolved_assistant_service))
```

5. Add the handler functions at the bottom of the file:

```python
def _assistant_not_configured_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(409, "ASSISTANT_NOT_CONFIGURED", "Assistant is not configured")


def _assistant_unavailable_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(503, "ASSISTANT_UNAVAILABLE", "Assistant service unavailable")


def _unsupported_file_type_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(415, "UNSUPPORTED_FILE_TYPE", "Unsupported file type")


def _upload_too_large_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(413, "UPLOAD_TOO_LARGE", "Upload too large")


def _upload_not_found_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(404, "UPLOAD_NOT_FOUND", "Upload not found")


def _conversation_not_found_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(404, "CONVERSATION_NOT_FOUND", "Conversation not found")


def _proposal_not_found_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(404, "PROPOSAL_NOT_FOUND", "Proposal not found")


def _proposal_resolved_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(409, "PROPOSAL_ALREADY_RESOLVED", "Proposal already resolved")


def _document_not_readable_handler(_request: Request, _error: Exception) -> JSONResponse:
    return _error_response(422, "DOCUMENT_NOT_READABLE", "Document has no readable text")
```

- [ ] **Step 4: Run the full backend suite**

Run: `uv run --directory backend pytest && uv run --directory backend pyright && uv run --directory backend ruff check src tests`
Expected: all tests PASS (including the pre-existing suite), pyright and ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/todo_backend/assistant_api.py backend/src/todo_backend/api.py \
  backend/pyproject.toml backend/uv.lock backend/tests/test_assistant_api.py
git commit -m "feat: expose assistant HTTP API"
```

---

### Task 9: Frontend API Contracts + Client

**Files:**
- Modify: `frontend/src/shared/api/contracts.ts`
- Modify: `frontend/src/shared/api/client.ts`
- Test: `frontend/src/shared/api/__tests__/assistant-client.test.ts`

**Interfaces:**
- Produces TS types: `AssistantAttachmentKind`, `AssistantAttachment`, `AssistantConversationSummary`, `AssistantMessage`, `ProposalFields`, `AssistantProposal`, `AssistantTurn`, `AssistantConversationDetail`, `AssistantSettingsView`, `AssistantSettingsPatch`, `ResolveProposalResult`, `SendAssistantMessageInput`.
- Produces `TodoApi` methods: `listAssistantConversations`, `createAssistantConversation`, `getAssistantConversation`, `deleteAssistantConversation`, `sendAssistantMessage`, `uploadAssistantFile`, `transcribeAssistantAudio`, `acceptAssistantProposal`, `rejectAssistantProposal`, `getAssistantSettings`, `updateAssistantSettings`.
- Consumed by: Tasks 12–14.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/shared/api/__tests__/assistant-client.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { createTodoApi } from '../client';

const connection = { baseUrl: 'http://localhost:8000', token: 'test-token' };

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('assistant api client', () => {
  it('sends a message and unwraps the turn', async () => {
    const turn = {
      message: { id: 'm2', role: 'assistant', content: '好', attachments: [], status: 'done', createdAt: 2 },
      proposals: [],
    };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(turn));
    const api = createTodoApi(connection, fetcher);

    const result = await api.sendAssistantMessage('c1', { content: '你好', attachments: [] });

    expect(result.message.content).toBe('好');
    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/assistant/conversations/c1/messages',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('uploads a file as multipart without a JSON content type', async () => {
    const attachment = { fileId: 'f1.png', kind: 'image', name: 'a.png', mime: 'image/png' };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(attachment, 201));
    const api = createTodoApi(connection, fetcher);
    const file = new File([new Uint8Array([1, 2])], 'a.png', { type: 'image/png' });

    const result = await api.uploadAssistantFile(file);

    expect(result).toEqual(attachment);
    const [, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer test-token');
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('resolves proposals and reads settings', async () => {
    const resolved = {
      proposal: { id: 'p1', messageId: 'm1', action: 'create', taskId: null,
        payload: { text: '买菜' }, status: 'accepted', createdAt: 1 },
      task: { id: 't1', text: '买菜', completed: false, priority: 'medium',
        createdAt: 1, category: 'life' },
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse(resolved))
      .mockResolvedValueOnce(jsonResponse({
        hasApiKey: true, chatModel: 'chat', audioModel: 'audio',
      }));
    const api = createTodoApi(connection, fetcher);

    const accepted = await api.acceptAssistantProposal('p1');
    const settings = await api.getAssistantSettings();

    expect(accepted.proposal.status).toBe('accepted');
    expect(accepted.task?.id).toBe('t1');
    expect(settings.hasApiKey).toBe(true);
  });

  it('returns transcribed text', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ text: '识别结果' }));
    const api = createTodoApi(connection, fetcher);

    await expect(api.transcribeAssistantAudio('f1.wav')).resolves.toBe('识别结果');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- src/shared/api/__tests__/assistant-client.test.ts`
Expected: FAIL — the assistant methods do not exist on `TodoApi`.

- [ ] **Step 3: Implement contracts and client**

Append to `frontend/src/shared/api/contracts.ts` (before the `TodoApi` interface):

```ts
export type AssistantAttachmentKind = 'image' | 'document' | 'audio';

export interface AssistantAttachment {
  fileId: string;
  kind: AssistantAttachmentKind;
  name: string;
  mime: string;
  extractedText?: string | null;
}

export interface AssistantConversationSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export interface AssistantMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments: AssistantAttachment[];
  status: 'pending' | 'done' | 'failed';
  createdAt: number;
}

export interface ProposalFields {
  text?: string;
  priority?: 'low' | 'medium' | 'high';
  category?: 'work' | 'study' | 'life' | 'other';
  time_start?: string | null;
  time_end?: string | null;
  notes?: string | null;
}

export interface AssistantProposal {
  id: string;
  messageId: string;
  action: 'create' | 'update' | 'delete';
  taskId: string | null;
  payload: ProposalFields;
  status: 'pending' | 'accepted' | 'rejected';
  createdAt: number;
}

export interface AssistantTurn {
  message: AssistantMessage;
  proposals: AssistantProposal[];
}

export interface AssistantConversationDetail {
  conversation: AssistantConversationSummary;
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
}

export interface AssistantSettingsView {
  hasApiKey: boolean;
  chatModel: string;
  audioModel: string;
}

export interface AssistantSettingsPatch {
  apiKey?: string;
  chatModel?: string;
  audioModel?: string;
}

export interface ResolveProposalResult {
  proposal: AssistantProposal;
  task: import('@/shared/types').Todo | null;
}

export interface SendAssistantMessageInput {
  content: string;
  attachments: AssistantAttachment[];
}
```

Extend the `TodoApi` interface in the same file:

```ts
  listAssistantConversations(): Promise<AssistantConversationSummary[]>;
  createAssistantConversation(): Promise<AssistantConversationSummary>;
  getAssistantConversation(id: string): Promise<AssistantConversationDetail>;
  deleteAssistantConversation(id: string): Promise<void>;
  sendAssistantMessage(id: string, input: SendAssistantMessageInput): Promise<AssistantTurn>;
  uploadAssistantFile(file: File): Promise<AssistantAttachment>;
  transcribeAssistantAudio(fileId: string): Promise<string>;
  acceptAssistantProposal(id: string): Promise<ResolveProposalResult>;
  rejectAssistantProposal(id: string): Promise<AssistantProposal>;
  getAssistantSettings(): Promise<AssistantSettingsView>;
  updateAssistantSettings(input: AssistantSettingsPatch): Promise<AssistantSettingsView>;
```

In `frontend/src/shared/api/client.ts`, add to the object returned by `createTodoApi`:

```ts
    listAssistantConversations: async () => (
      await request<{ conversations: AssistantConversationSummary[] }>(
        '/api/v1/assistant/conversations', 'GET',
      )
    ).conversations,
    createAssistantConversation: () => request<AssistantConversationSummary>(
      '/api/v1/assistant/conversations', 'POST', {},
    ),
    getAssistantConversation: id => request<AssistantConversationDetail>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}`, 'GET',
    ),
    deleteAssistantConversation: id => request<void>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}`, 'DELETE',
    ),
    sendAssistantMessage: (id, input) => request<AssistantTurn>(
      `/api/v1/assistant/conversations/${encodeURIComponent(id)}/messages`, 'POST', input,
    ),
    uploadAssistantFile: async file => {
      const form = new FormData();
      form.append('file', file, file.name);
      const response = await fetcher(`${baseUrl}/api/v1/assistant/uploads`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${connection.token}` },
        body: form,
      });
      if (!response.ok) throw await responseError(response);
      return (await response.json()) as AssistantAttachment;
    },
    transcribeAssistantAudio: async fileId => (
      await request<{ text: string }>('/api/v1/assistant/transcribe', 'POST', { fileId })
    ).text,
    acceptAssistantProposal: id => request<ResolveProposalResult>(
      `/api/v1/assistant/proposals/${encodeURIComponent(id)}/accept`, 'POST', {},
    ),
    rejectAssistantProposal: async id => (
      await request<{ proposal: AssistantProposal }>(
        `/api/v1/assistant/proposals/${encodeURIComponent(id)}/reject`, 'POST', {},
      )
    ).proposal,
    getAssistantSettings: () => request<AssistantSettingsView>(
      '/api/v1/assistant/settings', 'GET',
    ),
    updateAssistantSettings: input => request<AssistantSettingsView>(
      '/api/v1/assistant/settings', 'PUT', input,
    ),
```

Also extend the type imports from `./contracts` at the top of `client.ts` with the new assistant types.

Extending `TodoApi` with required methods breaks the two test factories that build complete literals. In both `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts` and `frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts`, append stubs to each factory's returned object:

```ts
    listAssistantConversations: vi.fn(),
    createAssistantConversation: vi.fn(),
    getAssistantConversation: vi.fn(),
    deleteAssistantConversation: vi.fn(),
    sendAssistantMessage: vi.fn(),
    uploadAssistantFile: vi.fn(),
    transcribeAssistantAudio: vi.fn(),
    acceptAssistantProposal: vi.fn(),
    rejectAssistantProposal: vi.fn(),
    getAssistantSettings: vi.fn(),
    updateAssistantSettings: vi.fn(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- src/shared/api/__tests__ && npm --prefix frontend run build`
Expected: PASS; TypeScript build clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/api/contracts.ts frontend/src/shared/api/client.ts \
  frontend/src/shared/api/__tests__/assistant-client.test.ts
git commit -m "feat: add assistant api client"
```

---

### Task 10: WAV Encoder + Recorder

**Files:**
- Create: `frontend/src/features/assistant/recorder/wav.ts`
- Test: `frontend/src/features/assistant/recorder/__tests__/wav.test.ts`

**Interfaces:**
- Produces: `encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer` — 16-bit PCM mono WAV.
- Produces: `WavRecorder` with `start(): Promise<void>`, `stop(): Promise<Blob>` (`audio/wav`), `cancel(): void`.
- Consumed by: Task 13 Composer.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/assistant/recorder/__tests__/wav.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { encodeWav } from '../wav';

function ascii(view: DataView, offset: number, length: number): string {
  let text = '';
  for (let i = 0; i < length; i += 1) text += String.fromCharCode(view.getUint8(offset + i));
  return text;
}

describe('encodeWav', () => {
  it('writes a valid RIFF/WAVE header', () => {
    const buffer = encodeWav(new Float32Array([0, 0.5, -0.5]), 16000);
    const view = new DataView(buffer);

    expect(ascii(view, 0, 4)).toBe('RIFF');
    expect(view.getUint32(4, true)).toBe(36 + 6);
    expect(ascii(view, 8, 4)).toBe('WAVE');
    expect(ascii(view, 12, 4)).toBe('fmt ');
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16); // bits
    expect(ascii(view, 36, 4)).toBe('data');
    expect(view.getUint32(40, true)).toBe(6);
    expect(buffer.byteLength).toBe(44 + 6);
  });

  it('converts float samples to int16 with clamping', () => {
    const buffer = encodeWav(new Float32Array([0, 1, -1, 2]), 16000);
    const view = new DataView(buffer);

    expect(view.getInt16(44, true)).toBe(0);
    expect(view.getInt16(46, true)).toBe(0x7fff);
    expect(view.getInt16(48, true)).toBe(-0x8000);
    expect(view.getInt16(50, true)).toBe(0x7fff); // 2 clamped to 1
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- src/features/assistant/recorder/__tests__/wav.test.ts`
Expected: FAIL — `../wav` does not exist.

- [ ] **Step 3: Implement encoder and recorder**

Create `frontend/src/features/assistant/recorder/wav.ts`:

```ts
export function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeAscii(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(8, 'WAVE');
  writeAscii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return buffer;
}

export class WavRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private chunks: Float32Array[] = [];

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.context = new AudioContext({ sampleRate: 16000 });
    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.processor.onaudioprocess = event => {
      this.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    };
    this.source.connect(this.processor);
    this.processor.connect(this.context.destination);
  }

  async stop(): Promise<Blob> {
    const chunks = this.chunks;
    const sampleRate = this.context?.sampleRate ?? 16000;
    this.release();
    const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    return new Blob([encodeWav(merged, sampleRate)], { type: 'audio/wav' });
  }

  cancel(): void {
    this.chunks = [];
    this.release();
  }

  private release(): void {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach(track => track.stop());
    void this.context?.close();
    this.processor = null;
    this.source = null;
    this.stream = null;
    this.context = null;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- src/features/assistant/recorder/__tests__/wav.test.ts && npm --prefix frontend run build`
Expected: PASS; build clean. (Only `encodeWav` is unit-tested; `WavRecorder` is exercised in the Task 15 manual run — jsdom has no audio devices.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assistant/recorder/
git commit -m "feat: add wav recorder for voice input"
```

---

### Task 11: i18n Copy

**Files:**
- Modify: `frontend/src/features/i18n/translations.ts`
- Test: `frontend/src/features/i18n/__tests__/translations.test.ts` (extend)

**Interfaces:**
- Produces: `assistant.*` keys and `errors.assistant*` keys in both dictionaries; `errorKeys` maps the new backend codes.
- Consumed by: Tasks 12–14.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/features/i18n/__tests__/translations.test.ts`:

```ts
  it('provides assistant copy in both languages', () => {
    const keys = [
      'assistant.title', 'assistant.newConversation', 'assistant.untitled',
      'assistant.inputPlaceholder', 'assistant.send', 'assistant.attach',
      'assistant.record', 'assistant.stopRecording', 'assistant.transcribe',
      'assistant.sendDirectly', 'assistant.thinking', 'assistant.retry',
      'assistant.failed', 'assistant.accept', 'assistant.reject',
      'assistant.accepted', 'assistant.rejected', 'assistant.proposalCreate',
      'assistant.proposalUpdate', 'assistant.proposalDelete',
      'assistant.setupRequired', 'assistant.setupHint', 'assistant.apiKey',
      'assistant.apiKeySaved', 'assistant.chatModel', 'assistant.audioModel',
      'assistant.save', 'assistant.saved', 'assistant.openAssistant',
      'assistant.deleteConversation', 'assistant.emptyConversation',
      'errors.assistantNotConfigured', 'errors.assistantUnavailable',
      'errors.uploadTooLarge', 'errors.unsupportedFileType',
      'errors.documentNotReadable', 'errors.conversationNotFound',
      'errors.proposalNotFound', 'errors.proposalAlreadyResolved',
    ] as const;
    for (const key of keys) {
      expect(translate('zh-CN', key)).not.toBe(key);
      expect(translate('en', key)).not.toBe(key);
    }
    expect(translationForError('zh-CN', 'ASSISTANT_NOT_CONFIGURED'))
      .toBe(translate('zh-CN', 'errors.assistantNotConfigured'));
    expect(translationForError('en', 'ASSISTANT_UNAVAILABLE'))
      .toBe(translate('en', 'errors.assistantUnavailable'));
    expect(translationForError('en', 'UPLOAD_TOO_LARGE'))
      .toBe(translate('en', 'errors.uploadTooLarge'));
  });
```

Check the existing test file's imports (`translate`, `translationForError`) and reuse them.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- src/features/i18n/__tests__/translations.test.ts`
Expected: FAIL — assistant keys missing.

- [ ] **Step 3: Add the copy**

Append to the `zhCN` dictionary in `translations.ts`:

```ts
  'assistant.title': 'AI 助手', 'assistant.newConversation': '新会话',
  'assistant.untitled': '未命名会话',
  'assistant.inputPlaceholder': '描述你的安排，或发送语音/文件…',
  'assistant.send': '发送', 'assistant.attach': '添加附件',
  'assistant.record': '开始录音', 'assistant.stopRecording': '停止录音',
  'assistant.transcribe': '转文字', 'assistant.sendDirectly': '直接发送',
  'assistant.thinking': '正在思考…', 'assistant.retry': '重试',
  'assistant.failed': '这条回复失败了，可以重试。',
  'assistant.accept': '接受', 'assistant.reject': '拒绝',
  'assistant.accepted': '已接受', 'assistant.rejected': '已拒绝',
  'assistant.proposalCreate': '新建任务', 'assistant.proposalUpdate': '修改任务',
  'assistant.proposalDelete': '删除任务',
  'assistant.setupRequired': '还没有配置模型服务',
  'assistant.setupHint': '填入火山引擎方舟的 API Key 后即可开始使用。',
  'assistant.apiKey': 'API Key', 'assistant.apiKeySaved': '已保存（不会回显）',
  'assistant.chatModel': '对话模型', 'assistant.audioModel': '音频模型',
  'assistant.save': '保存', 'assistant.saved': '已保存',
  'assistant.openAssistant': '打开 AI 助手',
  'assistant.deleteConversation': '删除会话',
  'assistant.emptyConversation': '告诉助手你的安排，它会帮你整理成任务。',
  'errors.assistantNotConfigured': '请先在助手设置中填入 API Key。',
  'errors.assistantUnavailable': '模型服务暂时不可用，请稍后重试。',
  'errors.uploadTooLarge': '文件超出大小限制。',
  'errors.unsupportedFileType': '不支持的文件类型。',
  'errors.documentNotReadable': '无法从该文档提取文字（可能是扫描件）。',
  'errors.conversationNotFound': '会话不存在。',
  'errors.proposalNotFound': '提议不存在。',
  'errors.proposalAlreadyResolved': '该提议已处理过。',
```

Append to the `en` dictionary:

```ts
  'assistant.title': 'AI Assistant', 'assistant.newConversation': 'New chat',
  'assistant.untitled': 'Untitled chat',
  'assistant.inputPlaceholder': 'Describe your plans, or send voice/files…',
  'assistant.send': 'Send', 'assistant.attach': 'Attach file',
  'assistant.record': 'Start recording', 'assistant.stopRecording': 'Stop recording',
  'assistant.transcribe': 'Transcribe', 'assistant.sendDirectly': 'Send directly',
  'assistant.thinking': 'Thinking…', 'assistant.retry': 'Retry',
  'assistant.failed': 'This reply failed. You can retry.',
  'assistant.accept': 'Accept', 'assistant.reject': 'Reject',
  'assistant.accepted': 'Accepted', 'assistant.rejected': 'Rejected',
  'assistant.proposalCreate': 'New task', 'assistant.proposalUpdate': 'Update task',
  'assistant.proposalDelete': 'Delete task',
  'assistant.setupRequired': 'Model service is not configured',
  'assistant.setupHint': 'Add your Volcano Engine Ark API key to get started.',
  'assistant.apiKey': 'API Key', 'assistant.apiKeySaved': 'Saved (never displayed)',
  'assistant.chatModel': 'Chat model', 'assistant.audioModel': 'Audio model',
  'assistant.save': 'Save', 'assistant.saved': 'Saved',
  'assistant.openAssistant': 'Open AI assistant',
  'assistant.deleteConversation': 'Delete chat',
  'assistant.emptyConversation': 'Tell the assistant your plans and it will draft tasks for you.',
  'errors.assistantNotConfigured': 'Add an API key in the assistant settings first.',
  'errors.assistantUnavailable': 'The model service is unavailable. Please try again later.',
  'errors.uploadTooLarge': 'The file exceeds the size limit.',
  'errors.unsupportedFileType': 'Unsupported file type.',
  'errors.documentNotReadable': 'No readable text in this document (it may be a scan).',
  'errors.conversationNotFound': 'The chat was not found.',
  'errors.proposalNotFound': 'The proposal was not found.',
  'errors.proposalAlreadyResolved': 'This proposal was already handled.',
```

Extend `errorKeys`:

```ts
  ASSISTANT_NOT_CONFIGURED: 'errors.assistantNotConfigured',
  ASSISTANT_UNAVAILABLE: 'errors.assistantUnavailable',
  UPLOAD_TOO_LARGE: 'errors.uploadTooLarge',
  UNSUPPORTED_FILE_TYPE: 'errors.unsupportedFileType',
  DOCUMENT_NOT_READABLE: 'errors.documentNotReadable',
  CONVERSATION_NOT_FOUND: 'errors.conversationNotFound',
  PROPOSAL_NOT_FOUND: 'errors.proposalNotFound',
  PROPOSAL_ALREADY_RESOLVED: 'errors.proposalAlreadyResolved',
  UPLOAD_NOT_FOUND: 'errors.notFound',
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- src/features/i18n/__tests__/translations.test.ts && npm --prefix frontend run build`
Expected: PASS. (The existing parity test enforces that both dictionaries hold the same keys.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/i18n/translations.ts \
  frontend/src/features/i18n/__tests__/translations.test.ts
git commit -m "feat: add assistant i18n copy"
```

---

### Task 12: useAssistant Hook

**Files:**
- Create: `frontend/src/features/assistant/hooks/useAssistant.ts`
- Test: `frontend/src/features/assistant/__tests__/useAssistant.test.ts`

**Interfaces:**
- Consumes: Task 9 `TodoApi` assistant methods.
- Produces: `AssistantState` (below), consumed by Task 13 components and Task 14 wiring.

```ts
export interface AssistantState {
  conversations: AssistantConversationSummary[];
  activeId: string | null;
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
  settingsView: AssistantSettingsView | null;
  sending: boolean;
  selectConversation(id: string): Promise<void>;
  startNewConversation(): void;
  deleteConversation(id: string): Promise<void>;
  send(content: string, attachments: AssistantAttachment[]): Promise<void>;
  retry(): Promise<void>;
  resolveProposal: (id: string, action: 'accept' | 'reject') => Promise<ResolveProposalResult | undefined>;
  saveSettings(patch: AssistantSettingsPatch): Promise<boolean>;
}
```

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/assistant/__tests__/useAssistant.test.ts`:

```ts
import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  AssistantConversationDetail,
  AssistantConversationSummary,
  ResolveProposalResult,
  TodoApi,
} from '@/shared/api/contracts';
import { useAssistant } from '../hooks/useAssistant';

const summary: AssistantConversationSummary = {
  id: 'c1', title: '你好', createdAt: 1, updatedAt: 1,
};

const detail: AssistantConversationDetail = {
  conversation: summary,
  messages: [
    { id: 'm1', role: 'user', content: '你好', attachments: [], status: 'done', createdAt: 1 },
    { id: 'm2', role: 'assistant', content: '你好！', attachments: [], status: 'done', createdAt: 2 },
  ],
  proposals: [
    { id: 'p1', messageId: 'm2', action: 'create', taskId: null,
      payload: { text: '买菜' }, status: 'pending', createdAt: 3 },
  ],
};

function fakeApi(): TodoApi {
  return {
    getAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat', audioModel: 'audio',
    }),
    listAssistantConversations: vi.fn().mockResolvedValue([summary]),
    getAssistantConversation: vi.fn().mockResolvedValue(detail),
    createAssistantConversation: vi.fn().mockResolvedValue({
      id: 'c2', title: '', createdAt: 4, updatedAt: 4,
    }),
    sendAssistantMessage: vi.fn().mockResolvedValue({
      message: detail.messages[1], proposals: [detail.proposals[0]],
    }),
    deleteAssistantConversation: vi.fn().mockResolvedValue(undefined),
    acceptAssistantProposal: vi.fn().mockResolvedValue({
      proposal: { ...detail.proposals[0], status: 'accepted' }, task: null,
    } satisfies ResolveProposalResult),
    rejectAssistantProposal: vi.fn().mockResolvedValue({
      ...detail.proposals[0], status: 'rejected',
    }),
    updateAssistantSettings: vi.fn().mockResolvedValue({
      hasApiKey: true, chatModel: 'chat2', audioModel: 'audio',
    }),
  } as unknown as TodoApi;
}

describe('useAssistant', () => {
  it('loads conversations and selects the newest on mount', async () => {
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(fakeApi(), onError));

    await waitFor(() => expect(result.current.activeId).toBe('c1'));
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.settingsView?.hasApiKey).toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });

  it('send creates a conversation when none is active', async () => {
    const api = fakeApi();
    const { result } = renderHook(() => useAssistant(api, vi.fn()));
    await waitFor(() => expect(result.current.settingsView).not.toBeNull());
    act(() => result.current.startNewConversation());
    expect(result.current.activeId).toBeNull();

    await act(() => result.current.send('安排明天', []));

    expect(api.createAssistantConversation).toHaveBeenCalled();
    expect(api.sendAssistantMessage).toHaveBeenCalledWith(
      'c2', { content: '安排明天', attachments: [] },
    );
  });

  it('resolving a proposal updates local state and returns the result', async () => {
    const { result } = renderHook(() => useAssistant(fakeApi(), vi.fn()));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    const resolved = await act(() => result.current.resolveProposal('p1', 'accept'));

    expect(resolved?.proposal.status).toBe('accepted');
    expect(result.current.proposals[0].status).toBe('accepted');
  });

  it('reports errors through onError', async () => {
    const api = fakeApi();
    api.sendAssistantMessage = vi.fn().mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { result } = renderHook(() => useAssistant(api, onError));
    await waitFor(() => expect(result.current.activeId).toBe('c1'));

    await act(() => result.current.send('hi', []));

    expect(onError).toHaveBeenCalled();
    expect(result.current.sending).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- src/features/assistant/__tests__/useAssistant.test.ts`
Expected: FAIL — hook does not exist.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/features/assistant/hooks/useAssistant.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AssistantAttachment,
  AssistantConversationSummary,
  AssistantMessage,
  AssistantProposal,
  AssistantSettingsPatch,
  AssistantSettingsView,
  ResolveProposalResult,
  TodoApi,
} from '@/shared/api/contracts';

export interface AssistantState {
  conversations: AssistantConversationSummary[];
  activeId: string | null;
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
  settingsView: AssistantSettingsView | null;
  sending: boolean;
  selectConversation: (id: string) => Promise<void>;
  startNewConversation: () => void;
  deleteConversation: (id: string) => Promise<void>;
  send: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  retry: () => Promise<void>;
  resolveProposal: (
    id: string,
    action: 'accept' | 'reject',
  ) => Promise<ResolveProposalResult | undefined>;
  saveSettings: (patch: AssistantSettingsPatch) => Promise<boolean>;
}

export function useAssistant(
  api: TodoApi,
  onError: (error: unknown) => void,
): AssistantState {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [proposals, setProposals] = useState<AssistantProposal[]>([]);
  const [settingsView, setSettingsView] = useState<AssistantSettingsView | null>(null);
  const [sending, setSending] = useState(false);
  const lastSendRef = useRef<{ content: string; attachments: AssistantAttachment[] } | null>(null);

  const selectConversation = useCallback(async (id: string) => {
    try {
      const detail = await api.getAssistantConversation(id);
      setActiveId(id);
      setMessages(detail.messages);
      setProposals(detail.proposals);
    } catch (error) {
      onError(error);
    }
  }, [api, onError]);

  useEffect(() => {
    void (async () => {
      try {
        const [view, list] = await Promise.all([
          api.getAssistantSettings(),
          api.listAssistantConversations(),
        ]);
        setSettingsView(view);
        setConversations(list);
        if (list.length > 0) await selectConversation(list[0].id);
      } catch (error) {
        onError(error);
      }
    })();
  }, [api, onError, selectConversation]);

  const startNewConversation = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setProposals([]);
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await api.deleteAssistantConversation(id);
      const list = await api.listAssistantConversations();
      setConversations(list);
      if (activeId === id) {
        if (list.length > 0) await selectConversation(list[0].id);
        else startNewConversation();
      }
    } catch (error) {
      onError(error);
    }
  }, [activeId, api, onError, selectConversation, startNewConversation]);

  const send = useCallback(async (content: string, attachments: AssistantAttachment[]) => {
    setSending(true);
    lastSendRef.current = { content, attachments };
    try {
      let conversationId = activeId;
      if (!conversationId) {
        const created = await api.createAssistantConversation();
        conversationId = created.id;
        setActiveId(created.id);
      }
      await api.sendAssistantMessage(conversationId, { content, attachments });
      const [list, detail] = await Promise.all([
        api.listAssistantConversations(),
        api.getAssistantConversation(conversationId),
      ]);
      setConversations(list);
      setMessages(detail.messages);
      setProposals(detail.proposals);
    } catch (error) {
      onError(error);
    } finally {
      setSending(false);
    }
  }, [activeId, api, onError]);

  const retry = useCallback(async () => {
    if (lastSendRef.current) {
      await send(lastSendRef.current.content, lastSendRef.current.attachments);
    }
  }, [send]);

  const resolveProposal = useCallback(async (
    id: string,
    action: 'accept' | 'reject',
  ): Promise<ResolveProposalResult | undefined> => {
    try {
      const result: ResolveProposalResult = action === 'accept'
        ? await api.acceptAssistantProposal(id)
        : { proposal: await api.rejectAssistantProposal(id), task: null };
      setProposals(prev => prev.map(p => (p.id === id ? result.proposal : p)));
      return result;
    } catch (error) {
      onError(error);
      return undefined;
    }
  }, [api, onError]);

  const saveSettings = useCallback(async (patch: AssistantSettingsPatch) => {
    try {
      setSettingsView(await api.updateAssistantSettings(patch));
      return true;
    } catch (error) {
      onError(error);
      return false;
    }
  }, [api, onError]);

  return {
    conversations, activeId, messages, proposals, settingsView, sending,
    selectConversation, startNewConversation, deleteConversation,
    send, retry, resolveProposal, saveSettings,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- src/features/assistant/__tests__/useAssistant.test.ts && npm --prefix frontend run build`
Expected: PASS; build clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assistant/hooks/useAssistant.ts \
  frontend/src/features/assistant/__tests__/useAssistant.test.ts
git commit -m "feat: add assistant state hook"
```

---

### Task 13: Assistant UI Components

**Files:**
- Create: `frontend/src/features/assistant/components/AssistantDrawer.tsx`
- Create: `frontend/src/features/assistant/components/MessageList.tsx`
- Create: `frontend/src/features/assistant/components/Composer.tsx`
- Create: `frontend/src/features/assistant/components/ProposalCard.tsx`
- Create: `frontend/src/features/assistant/components/AssistantSettingsPanel.tsx`
- Create: `frontend/src/features/assistant/styles/assistant.css`
- Modify: `frontend/src/features/i18n/translations.ts` (add `errors.micDenied` in both dictionaries and `MIC_DENIED: 'errors.micDenied'` to `errorKeys`)
- Test: `frontend/src/features/assistant/__tests__/assistant-components.test.tsx`

**Interfaces:**
- Consumes: Task 12 `AssistantState`, Task 10 `WavRecorder`, Task 11 copy.
- Produces: `<AssistantDrawer open onClose assistant onApplyProposal onError />` — consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/assistant/__tests__/assistant-components.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/features/i18n/I18nProvider';
import type { TodoApi } from '@/shared/api/contracts';
import type { AssistantState } from '../hooks/useAssistant';
import AssistantDrawer from '../components/AssistantDrawer';

function state(overrides: Partial<AssistantState> = {}): AssistantState {
  return {
    conversations: [], activeId: 'c1', sending: false,
    messages: [
      { id: 'm1', role: 'user', content: '安排明天', attachments: [], status: 'done', createdAt: 1 },
      { id: 'm2', role: 'assistant', content: '提议如下', attachments: [], status: 'done', createdAt: 2 },
    ],
    proposals: [
      { id: 'p1', messageId: 'm2', action: 'create', taskId: null,
        payload: { text: '买菜', priority: 'medium', time_start: '2026-07-21T09:00' },
        status: 'pending', createdAt: 3 },
    ],
    settingsView: { hasApiKey: true, chatModel: 'chat', audioModel: 'audio' },
    selectConversation: vi.fn(), startNewConversation: vi.fn(),
    deleteConversation: vi.fn(), send: vi.fn(), retry: vi.fn(),
    resolveProposal: vi.fn().mockResolvedValue(undefined), saveSettings: vi.fn(),
    ...overrides,
  };
}

function renderDrawer(assistant: AssistantState, onApplyProposal = vi.fn()) {
  return {
    onApplyProposal,
    ...render(
      <I18nProvider language="zh-CN">
        <AssistantDrawer
          open onClose={vi.fn()} assistant={assistant}
          api={{} as unknown as TodoApi}
          onApplyProposal={onApplyProposal} onError={vi.fn()}
        />
      </I18nProvider>,
    ),
  };
}

describe('AssistantDrawer', () => {
  it('renders messages and a pending proposal card', () => {
    renderDrawer(state());

    expect(screen.getByText('安排明天')).toBeTruthy();
    expect(screen.getByText('买菜')).toBeTruthy();
    expect(screen.getByText('新建任务')).toBeTruthy();
  });

  it('accepting a proposal resolves it and notifies the parent', async () => {
    const resolveResult = {
      proposal: { ...state().proposals[0], status: 'accepted' as const },
      task: null,
    };
    const assistant = state({
      resolveProposal: vi.fn().mockResolvedValue(resolveResult),
    });
    const { onApplyProposal } = renderDrawer(assistant);

    fireEvent.click(screen.getByText('接受'));

    expect(assistant.resolveProposal).toHaveBeenCalledWith('p1', 'accept');
    await screen.findByText('已接受');
    expect(onApplyProposal).toHaveBeenCalledWith(resolveResult);
  });

  it('shows a retry button on failed assistant messages', () => {
    const assistant = state({
      messages: [
        { id: 'm9', role: 'assistant', content: '', attachments: [], status: 'failed', createdAt: 9 },
      ],
      proposals: [],
    });
    renderDrawer(assistant);

    fireEvent.click(screen.getByText('重试'));

    expect(assistant.retry).toHaveBeenCalled();
  });

  it('shows the setup panel when the key is missing', () => {
    renderDrawer(state({ settingsView: { hasApiKey: false, chatModel: 'c', audioModel: 'a' } }));

    expect(screen.getByText('还没有配置模型服务')).toBeTruthy();
  });

  it('send button forwards composer content', () => {
    const assistant = state();
    renderDrawer(assistant);

    fireEvent.change(screen.getByPlaceholderText('描述你的安排，或发送语音/文件…'), {
      target: { value: '明天下午三点开会' },
    });
    fireEvent.click(screen.getByText('发送'));

    expect(assistant.send).toHaveBeenCalledWith('明天下午三点开会', []);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- src/features/assistant/__tests__/assistant-components.test.tsx`
Expected: FAIL — components do not exist.

- [ ] **Step 3: Implement the components and styles**

Create `frontend/src/features/assistant/components/AssistantDrawer.tsx`:

```tsx
import { useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { ResolveProposalResult, TodoApi } from '@/shared/api/contracts';
import type { AssistantState } from '../hooks/useAssistant';
import AssistantSettingsPanel from './AssistantSettingsPanel';
import Composer from './Composer';
import MessageList from './MessageList';
import '../styles/assistant.css';

interface AssistantDrawerProps {
  open: boolean;
  onClose: () => void;
  assistant: AssistantState;
  api: TodoApi;
  onApplyProposal: (result: ResolveProposalResult) => void;
  onError: (error: unknown) => void;
}

function AssistantDrawer({ open, onClose, assistant, api, onApplyProposal, onError }: AssistantDrawerProps) {
  const { t } = useI18n();
  const [settingsOpen, setSettingsOpen] = useState(false);
  if (!open) return null;

  const needsSetup = assistant.settingsView !== null && !assistant.settingsView.hasApiKey;
  const showSettings = needsSetup || settingsOpen;

  return (
    <aside className="assistant-drawer" aria-label={t('assistant.title')}>
      <div className="assistant-drawer__header">
        <span className="assistant-drawer__title">{t('assistant.title')}</span>
        <select
          className="assistant-drawer__conversations"
          value={assistant.activeId ?? ''}
          onChange={event => {
            if (event.target.value) void assistant.selectConversation(event.target.value);
          }}
          aria-label={t('assistant.title')}
        >
          {assistant.activeId === null && (
            <option value="">{t('assistant.newConversation')}</option>
          )}
          {assistant.conversations.map(conversation => (
            <option key={conversation.id} value={conversation.id}>
              {conversation.title || t('assistant.untitled')}
            </option>
          ))}
        </select>
        <button className="icon-btn" onClick={assistant.startNewConversation}
          title={t('assistant.newConversation')} aria-label={t('assistant.newConversation')}>＋</button>
        <button className="icon-btn" onClick={() => setSettingsOpen(prev => !prev)}
          title={t('header.settings')} aria-label={t('header.settings')}>⚙</button>
        <button className="icon-btn" onClick={onClose}
          title={t('common.close')} aria-label={t('common.close')}>✕</button>
      </div>
      {showSettings ? (
        <AssistantSettingsPanel
          view={assistant.settingsView}
          onSave={async patch => {
            const saved = await assistant.saveSettings(patch);
            if (saved) setSettingsOpen(false);
          }}
        />
      ) : (
        <>
          <MessageList
            messages={assistant.messages}
            proposals={assistant.proposals}
            sending={assistant.sending}
            onRetry={assistant.retry}
            onResolve={async (id, action) => {
              const result = await assistant.resolveProposal(id, action);
              if (result && action === 'accept') onApplyProposal(result);
            }}
          />
          <Composer
            sending={assistant.sending}
            onSend={assistant.send}
            onError={onError}
            uploadFile={file => api.uploadAssistantFile(file)}
            transcribe={fileId => api.transcribeAssistantAudio(fileId)}
          />
        </>
      )}
    </aside>
  );
}

export default AssistantDrawer;
```

Create `frontend/src/features/assistant/components/MessageList.tsx`:

```tsx
import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantMessage, AssistantProposal } from '@/shared/api/contracts';
import ProposalCard from './ProposalCard';

interface MessageListProps {
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
  sending: boolean;
  onRetry: () => void;
  onResolve: (id: string, action: 'accept' | 'reject') => Promise<void>;
}

function MessageList({ messages, proposals, sending, onRetry, onResolve }: MessageListProps) {
  const { t } = useI18n();
  if (messages.length === 0 && !sending) {
    return <div className="assistant-messages assistant-messages--empty">
      {t('assistant.emptyConversation')}
    </div>;
  }
  return (
    <div className="assistant-messages">
      {messages.map(message => (
        <div key={message.id}>
          <div className={`assistant-bubble assistant-bubble--${message.role}`}>
            {message.content && <p>{message.content}</p>}
            {message.attachments.map(attachment => (
              <span key={attachment.fileId} className="assistant-attachment">
                📎 {attachment.name}
              </span>
            ))}
            {message.status === 'failed' && (
              <p className="assistant-bubble__failed">
                {t('assistant.failed')}
                <button onClick={onRetry}>{t('assistant.retry')}</button>
              </p>
            )}
          </div>
          {proposals
            .filter(proposal => proposal.messageId === message.id)
            .map(proposal => (
              <ProposalCard key={proposal.id} proposal={proposal} onResolve={onResolve} />
            ))}
        </div>
      ))}
      {sending && <div className="assistant-bubble assistant-bubble--assistant">
        {t('assistant.thinking')}
      </div>}
    </div>
  );
}

export default MessageList;
```

Create `frontend/src/features/assistant/components/ProposalCard.tsx`:

```tsx
import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantProposal } from '@/shared/api/contracts';

interface ProposalCardProps {
  proposal: AssistantProposal;
  onResolve: (id: string, action: 'accept' | 'reject') => Promise<void>;
}

const ACTION_KEYS = {
  create: 'assistant.proposalCreate',
  update: 'assistant.proposalUpdate',
  delete: 'assistant.proposalDelete',
} as const;

const PRIORITY_KEYS = {
  low: 'priority.low',
  medium: 'priority.medium',
  high: 'priority.high',
} as const;

const CATEGORY_KEYS = {
  work: 'category.work',
  study: 'category.study',
  life: 'category.life',
  other: 'category.other',
} as const;

function ProposalCard({ proposal, onResolve }: ProposalCardProps) {
  const { t } = useI18n();
  const { payload } = proposal;
  return (
    <div className={`assistant-proposal assistant-proposal--${proposal.status}`}>
      <div className="assistant-proposal__header">
        <span>{t(ACTION_KEYS[proposal.action])}</span>
        {proposal.status !== 'pending' && (
          <span className="assistant-proposal__status">
            {proposal.status === 'accepted' ? t('assistant.accepted') : t('assistant.rejected')}
          </span>
        )}
      </div>
      {payload.text && <p className="assistant-proposal__text">{payload.text}</p>}
      <div className="assistant-proposal__fields">
        {payload.time_start && <span>{payload.time_start.replace('T', ' ')}</span>}
        {payload.priority && <span>{t(PRIORITY_KEYS[payload.priority])}</span>}
        {payload.category && <span>{t(CATEGORY_KEYS[payload.category])}</span>}
      </div>
      {proposal.status === 'pending' && (
        <div className="assistant-proposal__actions">
          <button className="assistant-proposal__accept"
            onClick={() => void onResolve(proposal.id, 'accept')}>
            {t('assistant.accept')}
          </button>
          <button onClick={() => void onResolve(proposal.id, 'reject')}>
            {t('assistant.reject')}
          </button>
        </div>
      )}
    </div>
  );
}

export default ProposalCard;
```

Create `frontend/src/features/assistant/components/Composer.tsx`:

```tsx
import { useRef, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import { ApiError, type AssistantAttachment } from '@/shared/api/contracts';
import { WavRecorder } from '../recorder/wav';

const ACCEPT = '.jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.md,.mp3,.wav,.m4a';

interface ComposerProps {
  sending: boolean;
  onSend: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  onError: (error: unknown) => void;
  uploadFile: (file: File) => Promise<AssistantAttachment>;
  transcribe: (fileId: string) => Promise<string>;
}

interface PendingAudio {
  attachment: AssistantAttachment;
}

function Composer({ sending, onSend, onError, uploadFile, transcribe }: ComposerProps) {
  const { t } = useI18n();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [recording, setRecording] = useState(false);
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const recorderRef = useRef<WavRecorder | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const upload = async (file: File) => {
    try {
      return await uploadFile(file);
    } catch (error) {
      onError(error);
      return null;
    }
  };

  const startRecording = async () => {
    try {
      const recorder = new WavRecorder();
      await recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      onError(new ApiError('business', 'MIC_DENIED', 'Microphone denied'));
    }
  };

  const stopRecording = async () => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    setRecording(false);
    if (!recorder) return;
    const blob = await recorder.stop();
    const file = new File([blob], `voice-${Date.now()}.wav`, { type: 'audio/wav' });
    const attachment = await upload(file);
    if (attachment) setPendingAudio({ attachment });
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const attachment = await upload(file);
    if (attachment) {
      if (attachment.kind === 'audio') setPendingAudio({ attachment });
      else setAttachments(prev => [...prev, attachment]);
    }
  };

  const handleSend = async () => {
    const content = text.trim();
    if (!content && attachments.length === 0 && !pendingAudio) return;
    const outgoing = pendingAudio ? [...attachments, pendingAudio.attachment] : attachments;
    await onSend(content, outgoing);
    setText('');
    setAttachments([]);
    setPendingAudio(null);
  };

  return (
    <div className="assistant-composer">
      {attachments.map(attachment => (
        <span key={attachment.fileId} className="assistant-attachment">
          📎 {attachment.name}
          <button
            aria-label={t('common.delete')}
            onClick={() => setAttachments(prev => prev.filter(a => a.fileId !== attachment.fileId))}
          >✕</button>
        </span>
      ))}
      {pendingAudio && (
        <div className="assistant-pending-audio">
          <span>🎙 {pendingAudio.attachment.name}</span>
          <button
            onClick={() => {
              const audio = pendingAudio;
              setPendingAudio(null);
              void (async () => {
                try {
                  setText(await transcribe(audio.attachment.fileId));
                } catch (error) {
                  onError(error);
                }
              })();
            }}
          >{t('assistant.transcribe')}</button>
          <button onClick={() => void handleSend()}>{t('assistant.sendDirectly')}</button>
          <button onClick={() => setPendingAudio(null)}>{t('common.cancel')}</button>
        </div>
      )}
      <div className="assistant-composer__row">
        <textarea
          value={text}
          onChange={event => setText(event.target.value)}
          placeholder={t('assistant.inputPlaceholder')}
          disabled={sending}
          rows={2}
          onKeyDown={event => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void handleSend();
          }}
        />
        <div className="assistant-composer__buttons">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={event => {
              void handleFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <button onClick={() => fileInputRef.current?.click()} disabled={sending}
            title={t('assistant.attach')} aria-label={t('assistant.attach')}>📎</button>
          <button
            onClick={() => void (recording ? stopRecording() : startRecording())}
            disabled={sending}
            title={recording ? t('assistant.stopRecording') : t('assistant.record')}
            aria-label={recording ? t('assistant.stopRecording') : t('assistant.record')}
          >{recording ? '⏹' : '🎙'}</button>
          <button
            onClick={() => void handleSend()}
            disabled={sending || (!text.trim() && attachments.length === 0 && !pendingAudio)}
          >{t('assistant.send')}</button>
        </div>
      </div>
    </div>
  );
}

export default Composer;
```

Create `frontend/src/features/assistant/components/AssistantSettingsPanel.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { AssistantSettingsPatch, AssistantSettingsView } from '@/shared/api/contracts';

interface AssistantSettingsPanelProps {
  view: AssistantSettingsView | null;
  onSave: (patch: AssistantSettingsPatch) => Promise<void>;
}

function AssistantSettingsPanel({ view, onSave }: AssistantSettingsPanelProps) {
  const { t } = useI18n();
  const [apiKey, setApiKey] = useState('');
  const [chatModel, setChatModel] = useState(view?.chatModel ?? '');
  const [audioModel, setAudioModel] = useState(view?.audioModel ?? '');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setChatModel(view?.chatModel ?? '');
    setAudioModel(view?.audioModel ?? '');
  }, [view]);

  return (
    <div className="assistant-settings">
      <h3>{t('assistant.setupRequired')}</h3>
      <p>{t('assistant.setupHint')}</p>
      <label>
        {t('assistant.apiKey')}
        <input
          type="password"
          value={apiKey}
          onChange={event => setApiKey(event.target.value)}
          placeholder={view?.hasApiKey ? t('assistant.apiKeySaved') : ''}
        />
      </label>
      <label>
        {t('assistant.chatModel')}
        <input value={chatModel} onChange={event => setChatModel(event.target.value)} />
      </label>
      <label>
        {t('assistant.audioModel')}
        <input value={audioModel} onChange={event => setAudioModel(event.target.value)} />
      </label>
      <button
        onClick={() => {
          const patch: AssistantSettingsPatch = { chatModel, audioModel };
          if (apiKey) patch.apiKey = apiKey;
          void onSave(patch).then(() => {
            setSaved(true);
            setApiKey('');
          });
        }}
      >{t('assistant.save')}</button>
      {saved && <span>{t('assistant.saved')}</span>}
    </div>
  );
}

export default AssistantSettingsPanel;
```

Create `frontend/src/features/assistant/styles/assistant.css`:

```css
.assistant-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 380px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg, #fff);
  border-left: 1px solid var(--border-color, #ddd);
  box-shadow: -4px 0 16px rgb(0 0 0 / 8%);
  z-index: 40;
}

.assistant-drawer__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--border-color, #ddd);
}

.assistant-drawer__title { font-weight: 600; }

.assistant-drawer__conversations {
  flex: 1;
  min-width: 0;
}

.assistant-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.assistant-messages--empty {
  align-items: center;
  justify-content: center;
  color: var(--text-secondary, #888);
}

.assistant-bubble {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-bubble--user {
  align-self: flex-end;
  background: var(--accent, #4a7dff);
  color: #fff;
}

.assistant-bubble--assistant {
  align-self: flex-start;
  background: var(--bubble-bg, #f1f1f1);
}

.assistant-bubble__failed { color: var(--danger, #c0392b); }

.assistant-attachment {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 8px;
  background: var(--bubble-bg, #eee);
}

.assistant-proposal {
  margin: 4px 0 4px 16px;
  padding: 10px 12px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.assistant-proposal__header {
  display: flex;
  justify-content: space-between;
  font-weight: 600;
}

.assistant-proposal__fields {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary, #888);
}

.assistant-proposal__actions { display: flex; gap: 8px; }

.assistant-composer {
  border-top: 1px solid var(--border-color, #ddd);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.assistant-composer__row { display: flex; gap: 8px; }
.assistant-composer__row textarea { flex: 1; resize: none; }
.assistant-composer__buttons { display: flex; flex-direction: column; gap: 4px; }

.assistant-pending-audio {
  display: flex;
  gap: 8px;
  align-items: center;
}

.assistant-settings {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.assistant-settings label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
```

Add to `zhCN`: `'errors.micDenied': '无法访问麦克风，请检查系统权限。'`
Add to `en`: `'errors.micDenied': 'Microphone is unavailable. Check system permissions.'`
Add to `errorKeys`: `MIC_DENIED: 'errors.micDenied',`

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- src/features/assistant && npm --prefix frontend run build`
Expected: PASS; build clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/assistant/ frontend/src/features/i18n/translations.ts
git commit -m "feat: add assistant drawer components"
```

---

### Task 14: App Wiring (Header Button + Task State Sync)

**Files:**
- Modify: `frontend/src/features/header/components/Header.tsx`
- Modify: `frontend/src/features/tasks/hooks/useTodos.ts`
- Modify: `frontend/src/app/App.tsx`
- Test: `frontend/src/features/tasks/hooks/__tests__/` (extend the existing useTodos test file)
- Test: `frontend/src/features/assistant/__tests__/header-assistant-button.test.tsx`

**Interfaces:**
- Produces on `TodoState`: `upsertExternalTask(task: Todo) => void` and `removeExternalTask(id: string) => void` — state-only, no API calls, no pending tracking.
- Consumes: Task 13 `AssistantDrawer`.

- [ ] **Step 1: Write the failing tests**

Append to the existing useTodos test file:

```ts
  it('upserts and removes externally changed tasks', () => {
    const initial = task();
    const { result } = renderHook(() => useTodos([initial], fakeApi(), vi.fn()));

    act(() => result.current.upsertExternalTask(task({ id: 'new-id', text: '助手创建' })));
    expect(result.current.allTasks.map(t => t.id)).toEqual([initial.id, 'new-id']);

    act(() => result.current.upsertExternalTask(task({ text: '改后' })));
    expect(result.current.allTasks[0].text).toBe('改后');
    expect(result.current.allTasks).toHaveLength(2);

    act(() => result.current.removeExternalTask(initial.id));
    expect(result.current.allTasks.map(t => t.id)).toEqual(['new-id']);
  });
```

（直接使用该测试文件已有的 `task()` 和 `fakeApi()` 工厂。）

Create `frontend/src/features/assistant/__tests__/header-assistant-button.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Header from '@/features/header/components/Header';
import { I18nProvider } from '@/features/i18n/I18nProvider';

describe('Header assistant button', () => {
  it('calls onOpenAssistant', () => {
    const onOpenAssistant = vi.fn();
    render(
      <I18nProvider language="zh-CN">
        <Header
          onOpenAchievements={vi.fn()}
          onOpenCreateModal={vi.fn()}
          onOpenSettings={vi.fn()}
          onOpenAssistant={onOpenAssistant}
          muted={false}
          onToggleMuted={vi.fn()}
          onToggleLanguage={vi.fn()}
          languagePending={false}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByLabelText('打开 AI 助手'));

    expect(onOpenAssistant).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- src/features/assistant/__tests__/header-assistant-button.test.tsx src/features/tasks/hooks`
Expected: FAIL — no `onOpenAssistant` prop; no `upsertExternalTask`.

- [ ] **Step 3: Wire the app**

In `useTodos.ts`, add to the `TodoState` interface:

```ts
  upsertExternalTask: (task: Todo) => void;
  removeExternalTask: (id: string) => void;
```

Add inside `useTodos` (next to the other callbacks) and include both in the returned object:

```ts
  const upsertExternalTask = useCallback((task: Todo) => {
    setTasks(prev => (
      prev.some(existing => existing.id === task.id)
        ? prev.map(existing => (existing.id === task.id ? task : existing))
        : [...prev, task]
    ));
  }, []);

  const removeExternalTask = useCallback((id: string) => {
    setTasks(prev => prev.filter(existing => existing.id !== id));
  }, []);
```

In `Header.tsx`, add `onOpenAssistant: () => void;` to `HeaderProps`, destructure it, and render inside `.app-header__actions` (before the language button):

```tsx
        <button
          className="icon-btn"
          onClick={onOpenAssistant}
          aria-label={t('assistant.openAssistant')}
          title={t('assistant.openAssistant')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" width="20" height="20">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l1.9 4.6L18.5 9l-4.6 1.4L12 15l-1.9-4.6L5.5 9l4.6-1.4L12 3zM18 15l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9.9-2.1z" />
          </svg>
        </button>
```

In `App.tsx` (`TodoApplicationContent`):

1. Add imports:

```ts
import { useAssistant } from '@/features/assistant/hooks/useAssistant';
import AssistantDrawer from '@/features/assistant/components/AssistantDrawer';
import type { ResolveProposalResult } from '@/shared/api/contracts';
```

2. Inside the component, after the existing hooks:

```ts
  const [assistantOpen, setAssistantOpen] = useState(false);
  const assistant = useAssistant(api, handleApplicationError);

  const handleApplyProposal = useCallback((result: ResolveProposalResult) => {
    if (result.proposal.action === 'delete') {
      if (result.proposal.taskId) todoState.removeExternalTask(result.proposal.taskId);
      return;
    }
    if (result.task) todoState.upsertExternalTask(result.task);
  }, [todoState]);
```

3. Pass `onOpenAssistant={() => setAssistantOpen(true)}` to `<Header>`.

4. Render the drawer next to `<AchievementDrawer>`:

```tsx
      <AssistantDrawer
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        assistant={assistant}
        api={api}
        onApplyProposal={handleApplyProposal}
        onError={handleApplicationError}
      />
```

- [ ] **Step 4: Run the full frontend suite**

Run: `npm --prefix frontend test && npm --prefix frontend run build`
Expected: entire suite PASS; build clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/header/components/Header.tsx \
  frontend/src/features/tasks/hooks/useTodos.ts frontend/src/app/App.tsx \
  frontend/src/features/tasks/hooks/__tests__ \
  frontend/src/features/assistant/__tests__/header-assistant-button.test.tsx
git commit -m "feat: wire assistant drawer into the app"
```

---

### Task 15: Desktop Mic Permission + Docs + Manual Verification

**Files:**
- Create: `desktop/src-tauri/Info.plist`
- Modify: `docs/backend/api.md`
- Modify: `docs/backend/database.md`
- Modify: `README.md`

- [ ] **Step 1: Create the plist**

Create `desktop/src-tauri/Info.plist` (Tauri's bundler merges this into the generated bundle plist):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>NSMicrophoneUsageDescription</key>
	<string>Todo List 需要麦克风权限，用于把语音输入交给 AI 助手分析。</string>
</dict>
</plist>
```

- [ ] **Step 2: Verify the merged plist lands in the bundle**

Run:

```bash
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run build
plutil -p "desktop/src-tauri/target/release/bundle/macos/Todo List.app/Contents/Info.plist" | grep Microphone
```

Expected: output contains `NSMicrophoneUsageDescription`. If the key is missing, move the key into `tauri.conf.json` under `bundle.macOS` (check the Tauri version's documented override) and rebuild — do not proceed without the key present.

- [ ] **Step 3: Update docs**

Append to `docs/backend/api.md` (new section, matching the document's existing style):

```markdown
## AI 助手

所有路由同样需要 Bearer token；统一挂载在 `/api/v1/assistant/` 下。

| 方法与路径 | 说明 |
| --- | --- |
| `POST /assistant/conversations` | 创建会话，返回 `{id, title, createdAt, updatedAt}` |
| `GET /assistant/conversations` | 返回 `{conversations: [...]}`（按 `updatedAt` 倒序） |
| `GET /assistant/conversations/{id}` | 返回 `{conversation, messages, proposals}` |
| `DELETE /assistant/conversations/{id}` | 删除会话并清理其上传附件，204 |
| `POST /assistant/conversations/{id}/messages` | 发送消息并运行 agent 循环，返回 `{message, proposals}` |
| `POST /assistant/uploads` | multipart 上传（字段名 `file`），返回 `{fileId, kind, name, mime}` |
| `POST /assistant/transcribe` | `{fileId}` → `{text}`（音频模型转写） |
| `POST /assistant/proposals/{id}/accept` | 按 action 创建/修改/删除真实任务，返回 `{proposal, task?}` |
| `POST /assistant/proposals/{id}/reject` | 标记拒绝，返回 `{proposal}` |
| `GET /assistant/settings` | 返回 `{hasApiKey, chatModel, audioModel}`（key 不回传） |
| `PUT /assistant/settings` | 保存 `{apiKey?, chatModel?, audioModel?}` |

上传限制：图片 jpg/jpeg/png/webp ≤10MB；文档 pdf/docx/txt/md ≤10MB；音频 mp3/wav/m4a ≤25MB。

稳定错误码：`ASSISTANT_NOT_CONFIGURED`（409）、`ASSISTANT_UNAVAILABLE`（503）、`UNSUPPORTED_FILE_TYPE`（415）、`UPLOAD_TOO_LARGE`（413）、`UPLOAD_NOT_FOUND`（404）、`CONVERSATION_NOT_FOUND`（404）、`PROPOSAL_NOT_FOUND`（404）、`PROPOSAL_ALREADY_RESOLVED`（409）、`DOCUMENT_NOT_READABLE`（422）。
```

Append to `docs/backend/database.md` (tables + migration sections, matching existing style):

```markdown
### assistant_conversations / assistant_messages / assistant_proposals

- `assistant_conversations`：`id` 主键，`title`，`created_at` / `updated_at`（毫秒时间戳）。
- `assistant_messages`：`id` 主键，`conversation_id` 外键（级联删除），`role`（user/assistant），`content`，`attachments`（JSON），`tool_trace`（JSON，仅审计），`status`（pending/done/failed），`created_at`。
- `assistant_proposals`：`id` 主键，`conversation_id`、`message_id` 外键，`action`（create/update/delete），`task_id`（update/delete 的目标），`payload`（JSON，任务字段），`status`（pending/accepted/rejected），`created_at`，`resolved_at`。

迁移 `003_add_assistant.sql` 新建以上三张表，并向 `app_settings` 增加 `assistant_api_key`、`assistant_chat_model`、`assistant_audio_model` 三列。API key 只存于该列，任何接口不回传。

上传的文件保存在数据库同级的 `assistant_uploads/` 目录，删除会话时同步清理。
```

Append to `README.md` 功能 list:

```markdown
- AI 助手：接入火山引擎方舟多模态模型，支持文字、语音（转写或直发）、图片和文档分析；agent 提议任务变更，确认后写入列表
```

- [ ] **Step 4: Full regression**

Run:

```bash
uv run --directory backend pytest
uv run --directory backend pyright
uv run --directory backend ruff check src tests
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: everything PASS / clean.

- [ ] **Step 5: Manual verification with a real Ark key**

Run `npm --prefix desktop run dev`, then walk through:

1. 打开助手抽屉 → 显示配置引导；填入真实 API Key 保存。
2. 发送「明天下午三点和产品开会，重要」→ 出现提议卡片；接受 → 任务列表出现该任务。
3. 追问「改成下午四点」→ 出现修改提议；接受 → 任务时间更新。
4. 录音 → 「转文字」→ 文字进入输入框可编辑 → 发送。
5. 录音 → 「直接发送」→ 转写自动入列，agent 回复。
6. 上传一张日程截图 → agent 整理出多条提议；拒绝其中一条 → 标记已拒绝。
7. 上传一份 docx/txt 计划 → agent 分析；上传扫描件 PDF → 收到 DOCUMENT_NOT_READABLE 提示。
8. 重启应用 → 会话与消息仍在，可继续对话。
9. 首次录音时系统弹出麦克风权限请求；拒绝时界面出现 `errors.micDenied` 提示。
10. 检查后端日志：不含 API key、消息正文、文件路径。

- [ ] **Step 6: Commit**

```bash
git add desktop/src-tauri/Info.plist docs/backend/api.md docs/backend/database.md README.md
git commit -m "feat: enable mic permission and document assistant"
```

---

## Definition of Done

- 全部自动化检查通过（Step 4 of Task 15）。
- 手动验收 10 条全部走通。
- 后端无真实网络调用的测试全部使用注入的 fake。
- 日志与接口均不泄露 API key。
