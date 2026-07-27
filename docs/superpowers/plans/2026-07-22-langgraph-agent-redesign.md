# TodoList LangGraph Agent Reliability Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the open-ended function-calling loop with two persisted LangGraph workflows that reliably distinguish create/update/delete, expose editable batch confirmation cards, and apply confirmed changes directly and idempotently through the backend.

**Architecture:** `AssistantTurnGraph` performs structured planning, deterministic target resolution, proposal construction, and proposal verification without writing tasks. `ProposalApplyGraph` pauses with `interrupt()`, resumes with the edited confirmation payload, applies each item in its own transaction, verifies the stored result, and loops back to review only for remaining failed items. Existing OpenAI SDK/Ark integration remains the sole model boundary; LangChain's high-level Agent API is not introduced.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, sqlite3, OpenAI Python SDK, LangGraph `StateGraph`, `langgraph-checkpoint-sqlite`, pytest, Ruff, Pyright; React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-22-langgraph-agent-redesign-design.md`

## Global Constraints

- Use the existing isolated Python 3.12 environment at `backend/.venv`; refresh it with `uv sync --directory backend --python .venv/bin/python --group dev` after dependency changes (`--directory backend` makes `.venv/bin/python` relative to `backend`).
- Do not add `langchain`; add only `langgraph` and `langgraph-checkpoint-sqlite` for orchestration and checkpoint persistence.
- `todo.sqlite3` remains the business source of truth; checkpoints live beside it in `assistant_graph.sqlite3`.
- Configure checkpoint serialization with `JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)`; checkpoint state contains JSON-safe IDs, bounded summaries, and primitive dictionaries only.
- Every task mutation requires a visible card. The normal path has one card confirmation, no verbal pre-confirmation, and no model call after the user clicks confirm.
- Group all create/update proposals from one turn into one batch. Every delete proposal is a separate single-item batch.
- Apply batch items in independent transactions. Successful items stay accepted; failed items stay pending with `last_error` and can be confirmed again.
- New graph/business IDs are stable under retry: turn graph thread `turn:{turn_id}`, apply graph thread `proposal:{batch_id}`, and batch/proposal IDs derived deterministically from `turn_id` plus their indexes.
- Never log API keys, message/task bodies, attachment contents, complete model payloads, or filesystem paths.
- All Ark calls stay in `backend/src/todo_backend/agent/ark_client.py`; automated tests inject fakes and never use a real key.
- Add migration `005`; never edit migrations `001` through `004`.
- Preserve existing uploads, transcription, settings, Bearer authentication, and attachment behavior.
- All new UI text must have both `zh-CN` and `en` translations.
- Backend gates: `backend/.venv/bin/python -m pytest`, `backend/.venv/bin/ruff check backend/src backend/tests`, and `backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python`.
- Frontend gates: `npm --prefix frontend test` and `npm --prefix frontend run build`.
- Do not commit, push, merge, or delete a worktree without explicit user authorization. The commit steps below are conditional checkpoints and must be skipped until that authorization is given.
- Backend Tasks 1-10 are one schema/wire migration slice: after Task 1 the old repository/service is intentionally not yet compatible with migration 005, and compatibility is restored in Task 11. Treat their commit blocks only as review boundaries; do not create an intermediate commit or run the full backend gate until Task 11. If commits are authorized, commit the complete backend slice only after Task 11's full suite passes.
- Frontend Tasks 12-13 are likewise one contract/component migration slice; only Task 13 runs the full build and offers the conditional frontend commit.

---

## File Structure

New backend files:

- `backend/migrations/005_redesign_assistant_agent.sql` — proposal batches, turn idempotency, snapshots, result IDs, statuses, and graph-thread ownership.
- `backend/src/todo_backend/repositories/proposal_batches.py` — batch/proposal persistence, hydration, stable status transitions, and graph-thread lookup.
- `backend/src/todo_backend/services/proposal_batches.py` — edited-payload validation, per-item task transactions, conflict checks, idempotency, and result verification.
- `backend/src/todo_backend/agent/checkpoints.py` — hardened SQLite checkpointer lifecycle and exact thread deletion.
- `backend/src/todo_backend/agent/apply_graph.py` — persisted review/edit/apply/verify workflow.
- `backend/src/todo_backend/agent/planning.py` — `IntentPlan` schema, prompts, explicit-action policy, and Ark plan adapter.
- `backend/src/todo_backend/agent/task_resolution.py` — deterministic task candidate scoring and ambiguity threshold.
- `backend/src/todo_backend/agent/proposals.py` — full-state draft construction, time preservation, grouping, and proposal verification.
- `backend/src/todo_backend/agent/turn_graph.py` — persisted plan/read/resolve/propose/verify graph.
- `backend/tests/test_proposal_batches_repository.py`
- `backend/tests/test_proposal_batch_service.py`
- `backend/tests/test_agent_checkpoints.py`
- `backend/tests/test_assistant_apply_graph.py`
- `backend/tests/test_assistant_planning.py`
- `backend/tests/test_assistant_task_resolution.py`
- `backend/tests/test_assistant_proposals.py`
- `backend/tests/test_assistant_turn_graph.py`

New frontend files:

- `frontend/src/features/assistant/components/ProposalFieldsEditor.tsx` — controlled editable fields shared by create/update items.
- `frontend/src/features/assistant/components/ProposalBatchCard.tsx` — one confirmation control for create/update batches, diffs, partial success, and superseded history.
- `frontend/src/features/assistant/components/DeleteProposalCard.tsx` — read-only full target and an isolated destructive confirmation.
- `frontend/src/features/assistant/__tests__/proposal-cards.test.tsx`

Modified backend files:

- `backend/pyproject.toml`, `backend/uv.lock`
- `backend/src/todo_backend/models.py`
- `backend/src/todo_backend/repositories/conversations.py`
- `backend/src/todo_backend/repositories/tasks.py`
- `backend/src/todo_backend/services/tasks.py`
- `backend/src/todo_backend/agent/ark_client.py`
- `backend/src/todo_backend/services/assistant.py`
- `backend/src/todo_backend/assistant_api.py`
- `backend/src/todo_backend/api.py`
- `backend/todo-backend.spec`
- Existing `backend/tests/test_assistant_*.py`, `test_database.py`, and `test_packaging_smoke.py`

Modified frontend files:

- `frontend/src/shared/api/contracts.ts`
- `frontend/src/shared/api/client.ts`
- `frontend/src/features/assistant/hooks/useAssistant.ts`
- `frontend/src/features/assistant/components/MessageList.tsx`
- `frontend/src/features/assistant/components/AssistantDrawer.tsx`
- `frontend/src/features/assistant/styles/assistant.css`
- `frontend/src/features/i18n/translations.ts`
- `frontend/src/app/App.tsx`
- Existing assistant, API-client, i18n, and App tests

Deleted after replacement tests pass:

- `backend/src/todo_backend/agent/orchestrator.py`
- `backend/src/todo_backend/agent/tools.py`
- `backend/tests/test_assistant_orchestrator.py`
- `backend/tests/test_assistant_tools.py`
- `frontend/src/features/assistant/components/ProposalCard.tsx`

Documentation updated in the final task:

- `README.md`
- `docs/project-overview.md`
- `docs/backend/api.md`
- `docs/backend/database.md`
- `docs/CLAUDE.md`

---

### Task 1: Migration 005 and Wire Models

**Files:**
- Create: `backend/migrations/005_redesign_assistant_agent.sql`
- Modify: `backend/src/todo_backend/models.py:226-315`
- Modify: `backend/tests/test_database.py`
- Modify: `backend/tests/test_assistant_settings.py`

**Interfaces:**
- Produces: `assistant_turns`, `assistant_proposal_batches`, extended `assistant_proposals`, and nullable `assistant_messages.turn_id`.
- Produces: separate `PlannedFields` (partial/internal) and `ProposalCardFields` (six required wire keys), plus `AssistantTurnRecord`, `AssistantProposalBatch`, extended `AssistantProposal`, `ConfirmProposalBatchCommand`, `ProposalReviewDecision`, `ProposalApplyItemResult`, and `ProposalBatchResolveResponse`.
- Preserves: every historical proposal as a same-status, single-item batch; historical partial payloads are hydrated by Task 2 before being returned.

- [ ] **Step 1: Add failing migration and wire-model tests**

Add these assertions to `backend/tests/test_database.py` and `backend/tests/test_assistant_settings.py`:

```python
def test_migration_005_adds_turns_batches_and_extended_proposals(database: Database) -> None:
    connection = database.connect()
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        proposal_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(assistant_proposals)")
        }
        message_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(assistant_messages)")
        }
        batch_indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(assistant_proposal_batches)")
        }
        message_index_columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA index_info(idx_assistant_batches_message)"
            )
        ]
    finally:
        connection.close()

    assert {"assistant_turns", "assistant_proposal_batches"} <= tables
    assert {
        "batch_id", "target_task_id", "before_snapshot", "result_task_id", "last_error"
    } <= proposal_columns
    assert "turn_id" in message_columns
    assert "idx_assistant_batches_message" in batch_indexes
    assert message_index_columns == ["message_id"]


def test_migration_005_wraps_legacy_proposals_without_changing_status(
    tmp_path: Path, migrations_dir: Path
) -> None:
    staged_migrations = tmp_path / "migrations"
    staged_migrations.mkdir()
    for version in range(1, 5):
        source = next(migrations_dir.glob(f"{version:03d}_*.sql"))
        shutil.copy2(source, staged_migrations / source.name)
    database_path = tmp_path / "legacy.sqlite3"
    legacy = Database(database_path, staged_migrations)
    legacy.initialize()
    with legacy.transaction() as connection:
        connection.execute(
            "INSERT INTO assistant_conversations VALUES ('c1', 'chat', 1, 1)"
        )
        connection.execute(
            "INSERT INTO assistant_messages"
            " (id, conversation_id, role, content, status, created_at)"
            " VALUES ('m1', 'c1', 'assistant', 'draft', 'done', 1)"
        )
        connection.execute(
            "INSERT INTO assistant_proposals"
            " (id, conversation_id, message_id, action, task_id, payload, status, created_at)"
            " VALUES ('p1', 'c1', 'm1', 'create', NULL, '{\"text\":\"买菜\"}',"
            " 'pending', 1)"
        )

    migration_005 = migrations_dir / "005_redesign_assistant_agent.sql"
    shutil.copy2(migration_005, staged_migrations / migration_005.name)
    legacy.initialize()

    with legacy.transaction() as connection:
        batch = connection.execute(
            "SELECT id, status FROM assistant_proposal_batches WHERE id = 'p1'"
        ).fetchone()
        proposal = connection.execute(
            "SELECT batch_id, status, payload FROM assistant_proposals WHERE id = 'p1'"
        ).fetchone()
    assert dict(batch) == {"id": "p1", "status": "pending"}
    assert proposal["batch_id"] == "p1"
    assert proposal["status"] == "pending"
    assert json.loads(proposal["payload"])["text"] == "买菜"
```

Add `import json` and `import shutil` to the test module. This exercises only the public `Database.initialize()` path.

In `test_assistant_settings.py`, assert `set(ProposalCardFields.model_json_schema()["required"])` is exactly the six card keys, constructing a complete value succeeds, and omitting `notes` raises `ValidationError`; also assert `PlannedFields(time_end="2026-07-22T17:00")` remains valid. This locks the planner/API boundary into the generated OpenAPI schema.

- [ ] **Step 2: Run the tests and confirm the red state**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_database.py backend/tests/test_assistant_settings.py -v
```

Expected: FAIL because schema version is 4 and the new tables/columns and model names do not exist.

- [ ] **Step 3: Create migration 005**

Create `backend/migrations/005_redesign_assistant_agent.sql` with this schema and data-preserving rebuild:

```sql
ALTER TABLE assistant_messages ADD COLUMN turn_id TEXT;
CREATE INDEX idx_assistant_messages_turn ON assistant_messages (turn_id);

CREATE TABLE assistant_turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES assistant_conversations (id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES assistant_messages (id) ON DELETE CASCADE,
    assistant_message_id TEXT NOT NULL REFERENCES assistant_messages (id) ON DELETE CASCADE,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'done', 'failed')),
    last_error TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (conversation_id, id),
    UNIQUE (user_message_id),
    UNIQUE (assistant_message_id)
);
CREATE UNIQUE INDEX idx_assistant_turns_one_active
    ON assistant_turns (conversation_id) WHERE status = 'active';

CREATE TABLE assistant_proposal_batches (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES assistant_conversations (id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES assistant_messages (id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'partially_applied', 'accepted', 'rejected', 'superseded')
    ),
    supersedes_batch_id TEXT REFERENCES assistant_proposal_batches (id) ON DELETE SET NULL,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
);
CREATE INDEX idx_assistant_batches_conversation
    ON assistant_proposal_batches (conversation_id, created_at);
CREATE INDEX idx_assistant_batches_message
    ON assistant_proposal_batches (message_id);

INSERT INTO assistant_proposal_batches (
    id, conversation_id, message_id, status, supersedes_batch_id, created_at, resolved_at
)
SELECT id, conversation_id, message_id, status, NULL, created_at, resolved_at
FROM assistant_proposals;

DROP INDEX idx_assistant_proposals_conversation;
ALTER TABLE assistant_proposals RENAME TO assistant_proposals_legacy;

CREATE TABLE assistant_proposals (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES assistant_conversations (id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES assistant_messages (id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES assistant_proposal_batches (id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    target_task_id TEXT,
    before_snapshot TEXT,
    payload TEXT,
    result_task_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'accepted', 'rejected', 'superseded')
    ),
    last_error TEXT,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
);

INSERT INTO assistant_proposals (
    id, conversation_id, message_id, batch_id, action, target_task_id,
    before_snapshot, payload, result_task_id, status, last_error, created_at, resolved_at
)
SELECT
    legacy.id,
    legacy.conversation_id,
    legacy.message_id,
    legacy.id,
    legacy.action,
    legacy.task_id,
    CASE WHEN legacy.action IN ('update', 'delete') THEN (
        SELECT json_object(
            'id', tasks.id,
            'text', tasks.text,
            'completed', json(CASE WHEN tasks.completed = 1 THEN 'true' ELSE 'false' END),
            'priority', tasks.priority,
            'createdAt', tasks.created_at,
            'time', CASE WHEN tasks.time_start IS NULL THEN NULL ELSE json_object(
                'start', tasks.time_start, 'end', tasks.time_end
            ) END,
            'category', tasks.category,
            'notes', tasks.notes
        )
        FROM tasks WHERE tasks.id = legacy.task_id
    ) ELSE NULL END,
    CASE
        WHEN legacy.action = 'delete'
             AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.id = legacy.task_id)
        THEN NULL
        ELSE legacy.payload
    END,
    CASE WHEN legacy.action IN ('update', 'delete') AND legacy.status = 'accepted'
        THEN legacy.task_id ELSE NULL END,
    legacy.status,
    CASE WHEN legacy.action IN ('update', 'delete')
              AND legacy.status = 'pending'
              AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.id = legacy.task_id)
        THEN 'TASK_TARGET_NOT_FOUND' ELSE NULL END,
    legacy.created_at,
    legacy.resolved_at
FROM assistant_proposals_legacy AS legacy;

DROP TABLE assistant_proposals_legacy;
CREATE INDEX idx_assistant_proposals_conversation
    ON assistant_proposals (conversation_id, created_at);
CREATE INDEX idx_assistant_proposals_batch
    ON assistant_proposals (batch_id, created_at);
```

Extend the migration fixture with two legacy deletes whose task row is absent: one accepted and one pending. Assert both preserve their original status, `before_snapshot`/`payload` are null instead of fabricated, the pending row receives the stable migration error, and conversation-detail hydration does not raise. New repository inserts reject null payloads; null is a legacy-read compatibility state only.

- [ ] **Step 4: Add the exact backend models**

Split partial planner changes from the complete confirmation wire shape and replace the old proposal/turn response section with these definitions:

```python
ProposalAction = Literal["create", "update", "delete"]
ProposalStatus = Literal["pending", "accepted", "rejected", "superseded"]
ProposalBatchStatus = Literal[
    "pending", "partially_applied", "accepted", "rejected", "superseded"
]
AssistantTurnStatus = Literal["active", "done", "failed"]


class PlannedFields(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    category: Category | None = None
    time_start: LocalDateTime | None = None
    time_end: LocalDateTime | None = None
    notes: StrictNotes | None = None


class ProposalCardFields(WireModel):
    text: StrictText
    priority: Priority
    category: Category
    time_start: LocalDateTime | None
    time_end: LocalDateTime | None
    notes: StrictNotes | None


# Temporary source-compatibility alias for the old AgentTools removed in Task 11.
ProposalFields = PlannedFields


class AssistantTurnRecord(WireModel):
    id: str
    conversation_id: str = Field(alias="conversationId")
    user_message_id: str = Field(alias="userMessageId")
    assistant_message_id: str = Field(alias="assistantMessageId")
    request_fingerprint: str = Field(alias="requestFingerprint")
    status: AssistantTurnStatus
    last_error: str | None = Field(default=None, alias="lastError")


class AssistantProposal(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    batch_id: str = Field(alias="batchId")
    action: ProposalAction
    target_task_id: str | None = Field(default=None, alias="targetTaskId")
    before_snapshot: Task | None = Field(default=None, alias="beforeSnapshot")
    payload: ProposalCardFields | None
    result_task_id: str | None = Field(default=None, alias="resultTaskId")
    status: ProposalStatus
    last_error: str | None = Field(default=None, alias="lastError")
    created_at: int = Field(alias="createdAt")


class AssistantProposalBatch(WireModel):
    id: str
    message_id: str = Field(alias="messageId")
    status: ProposalBatchStatus
    supersedes_batch_id: str | None = Field(default=None, alias="supersedesBatchId")
    proposals: list[AssistantProposal]
    created_at: int = Field(alias="createdAt")
    resolved_at: int | None = Field(default=None, alias="resolvedAt")


class SendAssistantMessageCommand(WireModel):
    turn_id: Annotated[str, Field(strict=True, min_length=8, max_length=100)] = Field(
        alias="turnId"
    )
    content: Annotated[str, Field(strict=True, max_length=10_000)] = ""
    attachments: list[AssistantAttachment] = Field(
        default_factory=list[AssistantAttachment], max_length=5
    )

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "SendAssistantMessageCommand":
        if not self.content.strip() and not self.attachments:
            raise ValueError("message requires content or attachments")
        return self


class ConfirmProposalItem(WireModel):
    proposal_id: str = Field(alias="proposalId")
    payload: ProposalCardFields | None = None


class ConfirmProposalBatchCommand(WireModel):
    items: Annotated[list[ConfirmProposalItem], Field(min_length=1)]


class ProposalReviewDecision(WireModel):
    decision: Literal["confirm", "reject"]
    items: list[ConfirmProposalItem] = Field(default_factory=list[ConfirmProposalItem])


class ProposalApplyItemResult(WireModel):
    proposal: AssistantProposal
    task: Task | None = None
    error: str | None = None


class ProposalBatchResolveResponse(WireModel):
    batch: AssistantProposalBatch
    items: list[ProposalApplyItemResult]


class AssistantTurnResponse(WireModel):
    message: AssistantMessage
    proposal_batches: list[AssistantProposalBatch] = Field(alias="proposalBatches")


class AssistantConversationDetail(WireModel):
    conversation: AssistantConversationSummary
    messages: list[AssistantMessage]
    proposal_batches: list[AssistantProposalBatch] = Field(alias="proposalBatches")
```

`AssistantProposal.payload` is nullable only for migration-era delete rows whose target had already disappeared before migration; every new draft and every create/update response must have a complete `ProposalCardFields`. Add `turn_id: str | None = Field(default=None, alias="turnId")` to `AssistantMessage`. Keep `AssistantProposalResolveResponse` and the documented `ProposalFields = PlannedFields` alias temporarily so the old agent imports remain buildable; remove only the alias with the obsolete tool files in Task 11.

- [ ] **Step 5: Run the targeted tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_database.py backend/tests/test_assistant_settings.py -v
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/models.py
```

Expected: migration/model tests PASS and Pyright reports 0 errors for `models.py`.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/migrations/005_redesign_assistant_agent.sql backend/src/todo_backend/models.py backend/tests/test_database.py backend/tests/test_assistant_settings.py
git commit -m "feat(agent): add proposal batch schema"
```

---

### Task 2: Turn and Proposal-Batch Repositories

**Files:**
- Modify: `backend/src/todo_backend/repositories/conversations.py`
- Create: `backend/src/todo_backend/repositories/proposal_batches.py`
- Modify: `backend/tests/test_assistant_conversations.py`
- Create: `backend/tests/test_proposal_batches_repository.py`

**Interfaces:**
- Produces: `ConversationsRepository.insert_message(..., turn_id: str | None)`.
- Produces: `insert_turn`, `get_turn`, `mark_turn`, `list_turn_ids`, and active-turn conflict detection.
- Produces: `ProposalBatchesRepository.insert_batches`, `list_for_conversation`, `get_batch`, `get_proposal`, `mark_item`, `set_last_error`, `recompute_batch`, `supersede`, and `list_batch_ids`.
- Guarantees: repository responses hydrate legacy partial update payloads from `before_snapshot`; new writes always store complete payloads.

- [ ] **Step 1: Write failing repository tests**

Create tests with these exact behaviors:

```python
def test_only_one_active_turn_per_conversation(database: Database, conversation_id: str) -> None:
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
                connection, conversation_id, "assistant", "", [], "pending", turn_id="turn-2"
            )
            repository.insert_turn(
                connection, "turn-2", conversation_id, user.id, assistant.id, "fingerprint-2"
            )


def test_batch_repository_hydrates_legacy_update_payload(database: Database, seeded_turn: Seed) -> None:
    tasks = TaskRepository()
    batches = ProposalBatchesRepository()
    with database.transaction() as connection:
        task = tasks.create(
            connection,
            CreateTaskCommand(
                text="会议", priority="high", category="work",
                time=TimeField(start="2026-07-22T15:00", end="2026-07-22T16:00"),
            ),
        )
        snapshot = task
        batches.insert_batches(
            connection,
            conversation_id=seeded_turn.conversation_id,
            message_id=seeded_turn.assistant_message_id,
            drafts=[BatchDraft(
                id="b1", supersedes_batch_id=None,
                proposals=[ProposalDraft(
                    id="p1", action="update", target_task_id=task.id,
                    before_snapshot=snapshot,
                    payload=ProposalCardFields(
                        text="会议", priority="high", category="work",
                        time_start="2026-07-22T15:00",
                        time_end="2026-07-22T17:00", notes=None,
                    ),
                )],
            )],
        )
        connection.execute(
            "UPDATE assistant_proposals SET payload = ? WHERE id = 'p1'",
            ('{"time_end":"2026-07-22T17:00"}',),
        )

    with database.transaction() as connection:
        batch = batches.get_batch(connection, "b1")

    proposal = batch.proposals[0]
    assert proposal.payload.text == "会议"
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"
```

Also cover deterministic insertion (`insert_batches` called twice yields one row), `supersede` disabling both batch and pending proposals, and `list_batch_ids` returning IDs used for checkpoint cleanup.

- [ ] **Step 2: Run repository tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_conversations.py backend/tests/test_proposal_batches_repository.py -v
```

Expected: FAIL because the new repository, turn methods, and extended row mapping do not exist.

- [ ] **Step 3: Extend `ConversationsRepository`**

Change message insertion/mapping and add these methods:

```python
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
    # Include turn_id in INSERT and AssistantMessage(turnId=turn_id).


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
        (turn_id, conversation_id, user_message_id, assistant_message_id,
         request_fingerprint, now, now),
    )
    return self.get_turn(connection, turn_id)


def get_turn(self, connection: sqlite3.Connection, turn_id: str) -> AssistantTurnRecord:
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
        "UPDATE assistant_turns SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
        (status, last_error, _now_ms(), turn_id),
    )
    return self.get_turn(connection, turn_id)


def list_turn_ids(self, connection: sqlite3.Connection, conversation_id: str) -> list[str]:
    return [
        row["id"]
        for row in connection.execute(
            "SELECT id FROM assistant_turns WHERE conversation_id = ?", (conversation_id,)
        ).fetchall()
    ]
```

Select `turn_id` in `list_messages` and `_message_from_row`. Add `AssistantTurnNotFoundError` next to `ConversationNotFoundError`.

- [ ] **Step 4: Implement `ProposalBatchesRepository`**

Define the internal draft dataclasses and exact public signatures:

```python
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


class ProposalBatchesRepository:
    def insert_batches(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        message_id: str,
        drafts: list[BatchDraft],
    ) -> list[AssistantProposalBatch]: ...

    def list_for_conversation(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[AssistantProposalBatch]: ...

    def get_batch(
        self, connection: sqlite3.Connection, batch_id: str
    ) -> AssistantProposalBatch: ...

    def get_proposal(
        self, connection: sqlite3.Connection, proposal_id: str
    ) -> AssistantProposal: ...

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
    ) -> AssistantProposal: ...

    def recompute_batch(
        self, connection: sqlite3.Connection, batch_id: str
    ) -> AssistantProposalBatch: ...

    def set_last_error(
        self, connection: sqlite3.Connection, proposal_id: str, last_error: str | None
    ) -> AssistantProposal: ...

    def supersede(
        self, connection: sqlite3.Connection, batch_id: str, resolved_at: int
    ) -> None: ...

    def list_batch_ids(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[str]: ...
```

Define `class ProposalBatchNotFoundError(LookupError): pass` and `class ProposalNotFoundError(LookupError): pass` in `repositories/proposal_batches.py`. Remove the duplicate `ProposalNotFoundError` definition from `repositories/conversations.py` and import the canonical class there only while its legacy methods remain. `get_batch`/`get_proposal` raise the matching typed error instead of leaking `KeyError` or returning `None`; `api.py` and compatibility routes must import this canonical class so a missing old single proposal cannot fall through as 500.

`source_batch_id`/`source_proposal_id` are transient construction metadata used only by Task 9 grouping; `insert_batches` never serializes them as proposal columns. `insert_batches` uses `INSERT OR IGNORE` for stable IDs, verifies that an existing row belongs to the same conversation/message, rejects null draft payloads, writes snapshots with `Task.model_dump_json(by_alias=True)`, and writes payloads with all six keys. `_proposal_from_row` normalizes every migration-era partial payload into the six-field card shape: create overlays explicit fields on `{text: None, priority: "medium", category: "other", time_start: None, time_end: None, notes: None}` and then requires a title; update overlays explicit fields on `_fields_from_task(before_snapshot)`; delete uses `_fields_from_task(before_snapshot)` for display. If an update/delete snapshot is absent, it returns `payload=None` and preserves the row for read-only history instead of inventing task data. Add repository tests for legacy create hydration plus accepted-delete/pending-missing-target rows returning nullable payload/snapshot without detail failure. `mark_item` serializes and replaces `payload` when the argument is non-null, so an accepted card edit becomes the durable audit payload; `payload=None` leaves it unchanged for validation errors and rejection. `set_last_error` updates only that column and never changes payload, status, result ID, or resolution time. `recompute_batch` implements exactly:

```python
statuses = {proposal.status for proposal in proposals}
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
```

Read `current_batch_status` in the same query/transaction. `supersede` sets the batch to `superseded` and changes only still-pending proposals to `superseded`; accepted audit items remain accepted. `recompute_batch` must preserve the terminal batch-level `superseded` status even for an accepted+superseded mixture, so a later idempotent read cannot revive an old card as `partially_applied`. Set `resolved_at` when no proposal remains pending; an accepted+rejected terminal batch stays `partially_applied` with a non-null `resolved_at`. Add this accepted-plus-superseded regression to the repository test.

- [ ] **Step 5: Run repository tests and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_conversations.py backend/tests/test_proposal_batches_repository.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/repositories backend/tests/test_assistant_conversations.py backend/tests/test_proposal_batches_repository.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/repositories backend/tests/test_proposal_batches_repository.py
```

Expected: all targeted tests PASS, Ruff exits 0, and Pyright reports 0 errors.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/repositories/conversations.py backend/src/todo_backend/repositories/proposal_batches.py backend/tests/test_assistant_conversations.py backend/tests/test_proposal_batches_repository.py
git commit -m "feat(agent): persist turns and proposal batches"
```

---

### Task 3: Transactional and Idempotent Proposal Application

**Files:**
- Modify: `backend/src/todo_backend/repositories/tasks.py:16-100`
- Modify: `backend/src/todo_backend/services/tasks.py:14-52`
- Create: `backend/src/todo_backend/services/proposal_batches.py`
- Modify: `backend/tests/test_tasks_api.py`
- Create: `backend/tests/test_proposal_batch_service.py`

**Interfaces:**
- Produces: `TaskRepository.get(connection, task_id) -> Task`.
- Produces: `TaskService.create_in_transaction`, `update_in_transaction`, and `delete_in_transaction` so proposal state and task state commit atomically.
- Produces: `ProposalBatchExecutor.confirm(batch_id, command)`, `.reject(batch_id)`, and `.verify(batch_id)`.
- Guarantees: exact snapshot comparison, complete edited payloads, partial success, repeat-confirm idempotency, `result_task_id` backfill, and preserved `time_start` when only `time_end` changes.

- [ ] **Step 1: Write failing executor tests**

Create `backend/tests/test_proposal_batch_service.py` covering these concrete cases:

```python
def test_confirm_update_preserves_start_when_card_changes_only_end(seeded_batch: SeededBatch) -> None:
    result = seeded_batch.executor.confirm(
        seeded_batch.batch.id,
        ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
            proposalId=seeded_batch.proposal.id,
            payload=ProposalCardFields(
                text="会议", priority="high", category="work",
                time_start="2026-07-22T15:00", time_end="2026-07-22T17:00",
                notes=None,
            ),
        )]),
    )
    assert result.items[0].error is None
    assert result.items[0].task is not None
    assert result.items[0].task.time == TimeField(
        start="2026-07-22T15:00", end="2026-07-22T17:00"
    )


def test_confirm_is_idempotent_and_returns_same_created_task(create_batch: SeededBatch) -> None:
    command = ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
        proposalId=create_batch.proposal.id,
        payload=create_batch.proposal.payload,
    )])
    first = create_batch.executor.confirm(create_batch.batch.id, command)
    second = create_batch.executor.confirm(create_batch.batch.id, command)
    assert first.items[0].task == second.items[0].task
    assert first.items[0].proposal.result_task_id == second.items[0].proposal.result_task_id
    assert len(create_batch.task_service.list_all()) == 1


def test_stale_update_stays_pending_without_overwrite(update_batch: SeededBatch) -> None:
    update_batch.task_service.update(
        update_batch.task.id, UpdateTaskCommand(text="用户在别处改过")
    )
    result = update_batch.executor.confirm(
        update_batch.batch.id, update_batch.confirm_command
    )
    assert result.items[0].proposal.status == "pending"
    assert result.items[0].error == "TASK_CHANGED_SINCE_PROPOSAL"
    assert update_batch.task_service.list_all()[0].text == "用户在别处改过"


def test_batch_commits_successes_and_keeps_failures_pending(mixed_batch: SeededBatch) -> None:
    result = mixed_batch.executor.confirm(mixed_batch.batch.id, mixed_batch.confirm_command)
    assert [item.proposal.status for item in result.items] == ["accepted", "pending"]
    assert result.batch.status == "partially_applied"
    assert len(mixed_batch.task_service.list_all()) == 1


def test_confirm_persists_edited_payload_for_reload(create_batch: SeededBatch) -> None:
    assert create_batch.proposal.payload is not None
    payload = create_batch.proposal.payload.model_copy(update={"text": "卡片编辑后"})
    command = ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
        proposalId=create_batch.proposal.id,
        payload=payload,
    )])

    create_batch.executor.confirm(create_batch.batch.id, command)
    reloaded = create_batch.executor.current(create_batch.batch.id)

    assert reloaded.items[0].proposal.payload.text == "卡片编辑后"
    assert reloaded.items[0].task is not None
    assert reloaded.items[0].task.text == "卡片编辑后"


def test_failed_item_keeps_parsed_card_edits_for_retry(update_batch: SeededBatch) -> None:
    update_batch.task_service.update(
        update_batch.task.id, UpdateTaskCommand(text="外部修改")
    )
    assert update_batch.proposal.payload is not None
    edited = update_batch.proposal.payload.model_copy(update={"notes": "保留我"})
    result = update_batch.executor.confirm(
        update_batch.batch.id,
        ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
            proposalId=update_batch.proposal.id, payload=edited,
        )]),
    )

    assert result.items[0].proposal.status == "pending"
    assert result.items[0].proposal.payload.notes == "保留我"
    assert update_batch.executor.current(update_batch.batch.id) \
        .items[0].proposal.payload.notes == "保留我"
```

Also test: blank edited title, end-before-start, duplicate/unknown/out-of-batch proposal IDs, omission of unrelated pending IDs during partial retry, no-op update, delete idempotency, rejection of only remaining pending items, and create success storing `result_task_id` in the same transaction.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_proposal_batch_service.py backend/tests/test_tasks_api.py -v
```

Expected: FAIL because the executor and transaction-aware task methods do not exist.

- [ ] **Step 3: Expose connection-scoped task operations**

Rename private repository `_get` to public `get`, update internal callers, and wrap existing service methods around these exact connection-scoped methods:

```python
def create_in_transaction(
    self, connection: sqlite3.Connection, command: CreateTaskCommand
) -> Task:
    return self.repository.create(connection, command)


def update_in_transaction(
    self,
    connection: sqlite3.Connection,
    task_id: str,
    command: UpdateTaskCommand,
) -> Task:
    task = self.repository.update(connection, task_id, command)
    if "time" in command.model_fields_set:
        self.reminder_repository.prune_stale(
            connection, task_id, task.time.start if task.time else None
        )
    return task


def delete_in_transaction(self, connection: sqlite3.Connection, task_id: str) -> None:
    self.repository.delete(connection, task_id)
```

`create`, `update`, and `delete` remain public compatibility wrappers that open one transaction and call the matching `*_in_transaction` method.

- [ ] **Step 4: Implement `ProposalBatchExecutor`**

Use these exact boundaries and error codes:

```python
EDITABLE_FIELDS = {"text", "priority", "category", "time_start", "time_end", "notes"}


class InvalidProposalBatchCommandError(ValueError):
    pass


class ProposalResultVerificationError(RuntimeError):
    pass


class ProposalBatchNotConfirmableError(RuntimeError):
    pass


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
        results = [self._apply_one(batch_id, proposal_id, edits[proposal_id])
                   for proposal_id in edits]
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
```

Inside `_apply_one`, open one `Database.transaction()`, reload the batch and proposal, and follow this order:

```python
if proposal.status == "accepted":
    return self._accepted_result(connection, proposal)
if proposal.status != "pending" or batch.status == "superseded":
    return ProposalApplyItemResult(
        proposal=proposal, task=self._result_task(connection, proposal),
        error="PROPOSAL_NOT_CONFIRMABLE",
    )

payload = self._validated_full_payload(proposal, item)
if proposal.action in {"update", "delete"}:
    current = self._tasks.repository.get(connection, proposal.target_task_id or "")
    if current != proposal.before_snapshot:
        return self._pending_error(
            connection, proposal, "TASK_CHANGED_SINCE_PROPOSAL", payload=payload
        )

if proposal.action == "create":
    task = self._tasks.create_in_transaction(connection, self._create_command(payload))
elif proposal.action == "update":
    task = self._tasks.update_in_transaction(
        connection, proposal.target_task_id or "", self._update_command(payload)
    )
else:
    self._tasks.delete_in_transaction(connection, proposal.target_task_id or "")
    task = None

if proposal.action in {"create", "update"}:
    stored = self._tasks.repository.get(connection, task.id if task else "")
    if not self._matches_payload(stored, payload):
        raise ProposalResultVerificationError("RESULT_VERIFICATION_FAILED")
else:
    try:
        self._tasks.repository.get(connection, proposal.target_task_id or "")
    except TaskNotFoundError:
        pass
    else:
        raise ProposalResultVerificationError("RESULT_VERIFICATION_FAILED")

resolved = self._batches.mark_item(
    connection,
    proposal.id,
    payload=payload,
    status="accepted",
    result_task_id=task.id if task else proposal.target_task_id,
    last_error=None,
    resolved_at=_now_ms(),
)
return ProposalApplyItemResult(proposal=resolved, task=task, error=None)
```

Omitting other pending IDs is valid because a partial retry submits only remaining/editable items; duplicate IDs, unknown IDs, or IDs from another batch reject the entire command before any mutation. `ProposalCardFields` makes all six keys structurally required; `_validated_full_payload` additionally enforces the time relationship and action rules. Delete ignores edited payload and applies its immutable stored snapshot; if a migration-era delete has no snapshot/target, it remains pending with `TASK_TARGET_NOT_FOUND` and cannot execute. Build update commands by comparing the edited full payload to `before_snapshot`; pass a complete `TimeField` when either time component differs. The accepted `mark_item` call stores that exact validated card payload in the same transaction as the task mutation and `result_task_id`, so response, restart, audit, and verification all see the edit.

If a complete `ProposalCardFields` value parsed successfully but the item fails a business check (stale snapshot, no-op, invalid time relationship, or task-service validation), persist that attempted payload with the pending `last_error` in the separate error transaction; this preserves the user's edits through partial-success rerender and restart. Use `payload=None` only when the command/payload could not be structurally parsed, no matching item exists, or the action is delete. Catch `ValidationError`, `TaskNotFoundError`, `ProposalResultVerificationError`, and expected business errors per item, roll back that item's task transaction, then record the stable error without changing a rejected/superseded status. Never catch `BaseException`.

`verify(batch_id)` reloads every accepted item's stored task. For create/update it compares the task with the accepted payload; for delete it requires `TaskNotFoundError`. A mismatch persists `RESULT_VERIFICATION_FAILED` through `set_last_error`, and the canonical `current()` response exposes it after graph completion or restart; it is never lost in transient graph state or silently reported as success. The same-transaction verification before `mark_item(status="accepted")` remains the primary correctness barrier; this post-commit graph check is an auditable recovery check and never replays a task write.

- [ ] **Step 5: Run executor and existing task tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_proposal_batch_service.py backend/tests/test_tasks_api.py backend/tests/test_reminders_api.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/services backend/src/todo_backend/repositories/tasks.py backend/tests/test_proposal_batch_service.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/services backend/tests/test_proposal_batch_service.py
```

Expected: targeted tests PASS, Ruff exits 0, and Pyright reports 0 errors.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/repositories/tasks.py backend/src/todo_backend/services/tasks.py backend/src/todo_backend/services/proposal_batches.py backend/tests/test_tasks_api.py backend/tests/test_proposal_batch_service.py
git commit -m "feat(agent): apply proposal batches transactionally"
```

---

### Task 4: LangGraph Dependency and Hardened Checkpoint Store

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/src/todo_backend/agent/checkpoints.py`
- Create: `backend/tests/test_agent_checkpoints.py`

**Interfaces:**
- Produces: `CheckpointStore(path: Path)` with `.saver`, `.has_thread(thread_id)`, `.delete_thread(thread_id)`, and `.close()`.
- Guarantees: `check_same_thread=False`, LangGraph's internal SQLite lock, no pickle fallback, strict msgpack allowlist, and exact thread deletion.

- [ ] **Step 1: Add LangGraph packages to the Python 3.12 environment**

Run:

```bash
uv add --directory backend langgraph langgraph-checkpoint-sqlite
uv sync --directory backend --python .venv/bin/python --group dev
```

Expected: `backend/pyproject.toml` contains both direct dependencies, `backend/uv.lock` changes, and dependency resolution completes without changing `requires-python = ">=3.12,<3.13"`.

- [ ] **Step 2: Write the failing persistence test**

Create `backend/tests/test_agent_checkpoints.py`:

```python
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from todo_backend.agent.checkpoints import CheckpointStore


class CounterState(TypedDict):
    value: int


def _graph(store: CheckpointStore):
    builder = StateGraph(CounterState)
    builder.add_node("increment", lambda state: {"value": state["value"] + 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=store.saver)


def test_checkpoint_survives_reopen_and_can_be_deleted(tmp_path: Path) -> None:
    path = tmp_path / "assistant_graph.sqlite3"
    config = {"configurable": {"thread_id": "turn:t1"}}

    first = CheckpointStore(path)
    assert _graph(first).invoke({"value": 1}, config=config)["value"] == 2
    assert first.has_thread("turn:t1") is True
    first.close()

    second = CheckpointStore(path)
    assert _graph(second).get_state(config).values["value"] == 2
    second.delete_thread("turn:t1")
    assert second.has_thread("turn:t1") is False
    second.close()
```

- [ ] **Step 3: Run the test and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_agent_checkpoints.py -v
```

Expected: FAIL because `todo_backend.agent.checkpoints` does not exist.

- [ ] **Step 4: Implement `CheckpointStore`**

Create `backend/src/todo_backend/agent/checkpoints.py`:

```python
import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        serializer = JsonPlusSerializer(
            pickle_fallback=False,
            allowed_msgpack_modules=None,
        )
        self.saver = SqliteSaver(self._connection, serde=serializer)
        self._closed = False

    @staticmethod
    def config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    def has_thread(self, thread_id: str) -> bool:
        return self.saver.get_tuple(self.config(thread_id)) is not None

    def delete_thread(self, thread_id: str) -> None:
        self.saver.delete_thread(thread_id)

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True
```

Do not put conversation text or Pydantic/domain objects into graph state; later graphs must call `model_dump(mode="json", by_alias=True)` before writing state.

- [ ] **Step 5: Run persistence and dependency checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_agent_checkpoints.py -v
backend/.venv/bin/python -c "import langgraph; from langgraph.checkpoint.sqlite import SqliteSaver"
backend/.venv/bin/ruff check backend/src/todo_backend/agent/checkpoints.py backend/tests/test_agent_checkpoints.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/checkpoints.py backend/tests/test_agent_checkpoints.py
```

Expected: test PASS; import and both static checks exit 0.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/todo_backend/agent/checkpoints.py backend/tests/test_agent_checkpoints.py
git commit -m "feat(agent): add durable graph checkpoints"
```

---

### Task 5: ProposalApplyGraph Review, Resume, and Partial Retry

**Files:**
- Create: `backend/src/todo_backend/agent/apply_graph.py`
- Modify: `backend/src/todo_backend/services/proposal_batches.py`
- Create: `backend/tests/test_assistant_apply_graph.py`

**Interfaces:**
- Consumes: Task 3 `ProposalBatchExecutor` and Task 4 checkpointer.
- Produces: `ProposalApplyWorkflow.start(batch_id)`, `.confirm(batch_id, command)`, and `.reject(batch_id)`.
- Guarantees: no side effect before `interrupt()`, same thread on resume, no model dependency, and a second interrupt when items remain pending.

- [ ] **Step 1: Complete the executor's graph-facing query/error methods**

Add and test these methods in `ProposalBatchExecutor`:

```python
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


def fail_pending(self, batch_id: str, error_code: str) -> ProposalBatchResolveResponse:
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
```

`_result_task` returns the stored task only for accepted create/update proposals. It catches `TaskNotFoundError` and returns `None` for migration-era/mutated history; delete and pending items also return `None`. `verify` is responsible for surfacing a missing accepted result as `RESULT_VERIFICATION_FAILED`, while ordinary detail reads never fail on historical rows.

- [ ] **Step 2: Write failing graph tests**

Create `backend/tests/test_assistant_apply_graph.py` with an in-memory checkpointer and a fake executor:

```python
def test_apply_graph_waits_before_any_write() -> None:
    executor = FakeExecutor(status="pending")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())

    workflow.start("b1")

    assert executor.confirm_calls == []
    assert executor.reject_calls == []


def test_confirm_resumes_with_edited_payload_without_model_call() -> None:
    executor = FakeExecutor(status="pending", status_after_confirm="accepted")
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")
    command = ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
        proposalId="p1", payload=ProposalCardFields(
            text="编辑后", priority="high", category="work",
            time_start=None, time_end=None, notes="确认卡修改",
        ),
    )])

    result = workflow.confirm("b1", command)

    assert executor.confirm_calls == [("b1", command)]
    assert result.batch.status == "accepted"


def test_partial_result_interrupts_again_for_remaining_items() -> None:
    executor = FakeExecutor(
        status="pending", status_after_confirm="partially_applied",
        pending_proposal_ids={"p2"},
    )
    workflow = ProposalApplyWorkflow(executor, InMemorySaver())
    workflow.start("b1")

    workflow.confirm("b1", command_for("p1"))

    snapshot = workflow.graph.get_state(workflow.config("b1"))
    assert snapshot.next == ("interrupt_review",)


def test_sqlite_checkpoint_resumes_confirmation_after_reopen(
    seeded_batch: SeededBatch, tmp_path: Path,
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
```

Also test reject routing, malformed resume data calling `fail_pending(..., "INVALID_CONFIRMATION_PAYLOAD")`, repeat confirmation returning the executor's idempotent result, and a `verify` mismatch remaining visible as persisted `RESULT_VERIFICATION_FAILED` in both the immediate workflow response and `current()` after rebuilding the workflow.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_apply_graph.py backend/tests/test_proposal_batch_service.py -v
```

Expected: FAIL because the workflow and graph-facing executor methods do not exist.

- [ ] **Step 4: Implement the apply graph**

Create `backend/src/todo_backend/agent/apply_graph.py` with JSON-safe state and these nodes:

```python
class ProposalApplyState(TypedDict, total=False):
    batch_id: str
    review: dict[str, Any]
    result: dict[str, Any]


class ProposalApplyWorkflow:
    def __init__(
        self,
        executor: ProposalBatchExecutor,
        checkpointer: BaseCheckpointSaver[str],
    ) -> None:
        self._executor = executor
        builder = StateGraph(ProposalApplyState)
        builder.add_node("load_batch", self._load_batch)
        builder.add_node("interrupt_review", self._interrupt_review)
        builder.add_node("validate_review", self._validate_review)
        builder.add_node("apply_items", self._apply_items)
        builder.add_node("verify_results", self._verify_results)
        builder.add_node("persist_results", self._persist_results)
        builder.add_node("reject_batch", self._reject_batch)
        builder.add_edge(START, "load_batch")
        builder.add_edge("load_batch", "interrupt_review")
        builder.add_edge("interrupt_review", "validate_review")
        builder.add_conditional_edges(
            "validate_review", self._review_route,
            {"confirm": "apply_items", "reject": "reject_batch", "invalid": "interrupt_review"},
        )
        builder.add_edge("apply_items", "verify_results")
        builder.add_edge("verify_results", "persist_results")
        builder.add_conditional_edges(
            "persist_results", self._result_route,
            {"done": END, "review": "interrupt_review"},
        )
        builder.add_edge("reject_batch", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    @staticmethod
    def config(batch_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": f"proposal:{batch_id}"}}

    def start(self, batch_id: str) -> ProposalBatchResolveResponse:
        config = self.config(batch_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            self.graph.invoke({"batch_id": batch_id}, config=config)
        return self._executor.current(batch_id)

    def confirm(
        self, batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        current = self._executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current
        self.start(batch_id)
        decision = ProposalReviewDecision(decision="confirm", items=command.items)
        self.graph.invoke(
            Command(resume=decision.model_dump(mode="json", by_alias=True)),
            config=self.config(batch_id),
        )
        return self._executor.current(batch_id)

    def reject(self, batch_id: str) -> ProposalBatchResolveResponse:
        current = self._executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current
        self.start(batch_id)
        decision = ProposalReviewDecision(decision="reject")
        self.graph.invoke(
            Command(resume=decision.model_dump(mode="json", by_alias=True)),
            config=self.config(batch_id),
        )
        return self._executor.current(batch_id)

    def _interrupt_review(self, state: ProposalApplyState) -> ProposalApplyState:
        review = interrupt({"batchId": state["batch_id"]})
        return {"review": review}
```

`confirm`/`reject` first return the canonical result for a terminal non-superseded batch, reject a superseded batch, and call idempotent `start` before `Command(resume=...)`; this makes both repeated confirmation and migration-era threads safe. `start` checks the stable thread state: a new thread runs to `interrupt_review`, while an already interrupted or completed thread returns current business state without appending another checkpoint or repeating a node. `_load_batch` calls only `executor.current`. `_validate_review` catches only `ValidationError`, persists `INVALID_CONFIRMATION_PAYLOAD`, and stores a JSON result. `_apply_items` reconstructs `ConfirmProposalBatchCommand` and calls `executor.confirm`; that executor has already applied, reread, and marked each successful item inside one transaction, which is required so a crash cannot leave a created task without its `result_task_id`. `_verify_results` independently reloads the committed results through `executor.verify`. `_persist_results` calls `executor.recompute`, stores the JSON-safe canonical response in graph state, and does not replay task mutations. `_result_route` returns `"review"` for `pending`/`partially_applied` and `"done"` otherwise. No node imports or accepts `ArkClient`.

- [ ] **Step 5: Run apply graph and persistence tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_apply_graph.py backend/tests/test_proposal_batch_service.py backend/tests/test_agent_checkpoints.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent/apply_graph.py backend/src/todo_backend/services/proposal_batches.py backend/tests/test_assistant_apply_graph.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/apply_graph.py backend/src/todo_backend/services/proposal_batches.py backend/tests/test_assistant_apply_graph.py
```

Expected: all tests PASS and both static checks exit 0.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/agent/apply_graph.py backend/src/todo_backend/services/proposal_batches.py backend/tests/test_assistant_apply_graph.py backend/tests/test_proposal_batch_service.py
git commit -m "feat(agent): add persisted proposal review graph"
```

---

### Task 6: Structured Ark Planning and Thinking Fallback

**Files:**
- Modify: `backend/src/todo_backend/agent/ark_client.py`
- Modify: `backend/tests/test_assistant_ark_client.py`

**Interfaces:**
- Produces: `ArkClient.chat(..., thinking: Literal["enabled", "disabled"] = "disabled", tool_choice: dict | None = None)`.
- Produces: `ArkClient.plan(messages, submit_plan_tool) -> dict[str, Any]` requiring exactly one object-valued `submit_plan` call.
- Guarantees: planning tries extended thinking; only an OpenAI `BadRequestError` causes one disabled-thinking fallback; final replies and transcription keep thinking disabled.

- [ ] **Step 1: Add failing Ark client tests**

Add tests using the existing fake OpenAI completion object:

```python
def test_plan_forces_submit_plan_and_enables_thinking() -> None:
    completion = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([completion])

    plan = client.plan([{"role": "user", "content": "有哪些任务"}], SUBMIT_PLAN_TOOL)

    assert plan == {"kind": "query"}
    request = transport.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert request["tool_choice"] == {
        "type": "function", "function": {"name": "submit_plan"}
    }


def test_plan_retries_without_thinking_only_for_bad_request() -> None:
    bad_request = BadRequestError(
        "thinking unsupported",
        response=httpx.Response(400, request=httpx.Request("POST", "https://ark.test")),
        body={"error": "unsupported"},
    )
    completion = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([bad_request, completion])

    assert client.plan([], SUBMIT_PLAN_TOOL) == {"kind": "query"}
    calls = transport.chat.completions.create.call_args_list
    assert calls[0].kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert calls[1].kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert client.planning_thinking_supported is False


def test_known_unsupported_thinking_skips_enabled_probe_and_duplicate_event() -> None:
    first = thinking_bad_request()
    fallback = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    next_plan = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport, capability_events = ark_client_with_events(
        [first, fallback, next_plan]
    )

    client.plan([], SUBMIT_PLAN_TOOL)
    client.plan([], SUBMIT_PLAN_TOOL)

    calls = transport.chat.completions.create.call_args_list
    assert [call.kwargs["extra_body"] for call in calls] == [
        {"thinking": {"type": "enabled"}},
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "disabled"}},
    ]
    assert capability_events == ["assistant_planner_thinking_fallback"]


@pytest.mark.parametrize("arguments", ["[]", '"text"', "null", "{"])
def test_plan_rejects_non_object_or_malformed_arguments(arguments: str) -> None:
    client, _transport = ark_client_with([
        fake_completion(tool_name="submit_plan", arguments=arguments)
    ])
    with pytest.raises(ArkUnavailableError):
        client.plan([], SUBMIT_PLAN_TOOL)
```

Also assert a timeout/500-style generic exception does not trigger a second call and that normal `chat()` still sends disabled thinking.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_ark_client.py -v
```

Expected: FAIL because `plan`, `tool_choice`, thinking selection, and object validation are absent.

- [ ] **Step 3: Refactor the Ark boundary**

Implement the request boundary as follows:

```python
ThinkingMode = Literal["enabled", "disabled"]


def chat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    tool_choice: dict[str, Any] | None = None,
    thinking: ThinkingMode = "disabled",
) -> ArkChatResult:
    return self._chat_once(
        messages,
        tools,
        tool_choice=tool_choice,
        thinking=thinking,
        propagate_bad_request=False,
    )


def plan(
    self, messages: list[dict[str, Any]], submit_plan_tool: dict[str, Any]
) -> dict[str, Any]:
    choice = {"type": "function", "function": {"name": "submit_plan"}}
    if self.planning_thinking_supported is False:
        result = self._chat_once(
            messages,
            [submit_plan_tool],
            tool_choice=choice,
            thinking="disabled",
            propagate_bad_request=False,
        )
    else:
        try:
            result = self._chat_once(
                messages,
                [submit_plan_tool],
                tool_choice=choice,
                thinking="enabled",
                propagate_bad_request=True,
            )
            self.planning_thinking_supported = True
        except BadRequestError:
            self.planning_thinking_supported = False
            self._capability_event("assistant_planner_thinking_fallback")
            result = self._chat_once(
                messages,
                [submit_plan_tool],
                tool_choice=choice,
                thinking="disabled",
                propagate_bad_request=False,
            )
    if len(result.tool_calls) != 1 or result.tool_calls[0].name != "submit_plan":
        raise ArkUnavailableError("planner did not submit exactly one plan")
    arguments = result.tool_calls[0].arguments
    if not isinstance(arguments, dict):
        raise ArkUnavailableError("plan arguments must be an object")
    return arguments
```

Initialize `planning_thinking_supported: bool | None = None`. `_capability_event` logs only the stable event name at info level—no endpoint, model payload, exception body, user content, or key—and is emitted only on the `None/True → False` transition. Once false, later planning calls go directly to disabled thinking instead of paying for a known-failing 400 probe.

`_chat_once` builds the existing OpenAI request, adds `tool_choice`, and catches errors as follows:

```python
except BadRequestError as error:
    if propagate_bad_request:
        raise
    raise ArkUnavailableError("chat completion failed") from error
except Exception as error:
    raise ArkUnavailableError("chat completion failed") from error
```

Thus only the first enabled-thinking planner request can escape as `BadRequestError`; a disabled fallback failure becomes `ArkUnavailableError` and cannot loop. Validate decoded tool arguments are dictionaries before constructing `ArkToolCall`, eliminating the current list/`.get()` crash path.

- [ ] **Step 4: Run Ark tests and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_ark_client.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent/ark_client.py backend/tests/test_assistant_ark_client.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/ark_client.py backend/tests/test_assistant_ark_client.py
```

Expected: all Ark tests PASS and both static checks exit 0.

- [ ] **Step 5: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/agent/ark_client.py backend/tests/test_assistant_ark_client.py
git commit -m "feat(agent): add structured planning calls"
```

---

### Task 7: Intent Schema and Explicit Action Policy

**Files:**
- Create: `backend/src/todo_backend/agent/planning.py`
- Create: `backend/tests/test_assistant_planning.py`

**Interfaces:**
- Produces: `IntentPlan`, `PlannedMutation`, `TargetQuery`, `SUBMIT_PLAN_TOOL`, `ArkPlanner.plan_once`, and `validate_explicit_actions`.
- Guarantees: query has no mutations; every mutation item has its own action; create has no target and requires a title; update/delete require a real target query or a pending-proposal reference; explicit create/update/delete wording cannot silently become a different action.

- [ ] **Step 1: Write failing planning tests**

Create `backend/tests/test_assistant_planning.py`:

```python
@pytest.mark.parametrize("text", ["新建一个会议", "添加买菜任务", "add a task"])
def test_explicit_create_cannot_be_planned_as_update(text: str) -> None:
    plan = IntentPlan.model_validate({
        "kind": "mutations",
        "evidence": text,
        "items": [{
            "action": "update",
            "target_query": {"title": "会议"},
            "fields": {"text": "会议"},
        }],
    })
    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions(text, plan)


def test_update_requires_target_and_non_empty_changes() -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate({
            "kind": "mutations", "evidence": "改一下",
            "items": [{"action": "update", "fields": {}}],
        })


def test_query_rejects_mutation_items() -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate({
            "kind": "query", "evidence": "查看",
            "items": [{"action": "create", "fields": {"text": "x"}}],
        })


def test_plan_once_returns_one_stable_validation_error() -> None:
    ark = ScriptedPlanner([
        {"kind": "mutations", "evidence": "新建任务", "items": []}
    ])
    planner = ArkPlanner(ark)
    with pytest.raises(PlanValidationError):
        planner.plan_once("新建任务", [], validation_code=None)
    assert ark.call_count == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("把会议改为四点", {"update"}),
        ("更改会议时间", {"update"}),
        ("加一个买菜任务", {"create"}),
        ("reschedule the meeting", {"update"}),
        ("不要删除会议，只修改时间", {"update"}),
        ("不要新建，改现有的", {"update"}),
        ("don't delete it; update the time", {"update"}),
    ],
)
def test_explicit_action_corpus_and_negation(
    text: str, expected: set[ProposalAction]
) -> None:
    assert explicit_actions(text) == expected


@pytest.mark.parametrize("text", ["如何删除任务", "请问如何删除任务"])
def test_how_to_delete_is_query_not_delete_command(text: str) -> None:
    plan = IntentPlan(kind="mutations", evidence=text, items=[
        PlannedMutation(action="delete", target_query=TargetQuery(title="任务"))
    ])
    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions(text, plan)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py -v
```

Expected: FAIL because the planning module does not exist.

- [ ] **Step 3: Implement the schema and tool definition**

Create these models in `planning.py`:

```python
PlanKind = Literal["query", "mutations"]


class PlanPolicyError(ValueError):
    pass


class PlanValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TargetQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str | None = None
    time_start: LocalDateTime | None = None
    category: Category | None = None
    referenced_task_id: str | None = None

    @model_validator(mode="after")
    def require_one_selector(self) -> "TargetQuery":
        if not any((self.title, self.time_start, self.category, self.referenced_task_id)):
            raise ValueError("target query requires a selector")
        return self


class PlannedMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: ProposalAction
    target_query: TargetQuery | None = None
    fields: PlannedFields = Field(default_factory=PlannedFields)
    reference: str | None = None


class IntentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: PlanKind
    evidence: str
    query: str | None = None
    items: list[PlannedMutation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "IntentPlan":
        if self.kind == "query" and (self.items or not self.query):
            raise ValueError("query requires query text and no mutations")
        if self.kind == "mutations" and not self.items:
            raise ValueError("mutation plan requires items")
        if self.kind == "mutations" and self.query is not None:
            raise ValueError("mutation plan cannot contain query text")
        for item in self.items:
            if item.action == "create":
                if item.target_query is not None or item.reference is not None \
                        or not item.fields.text:
                    raise ValueError("create requires text and no target")
            elif item.target_query is None and item.reference is None:
                raise ValueError("update/delete require a target or pending reference")
            if item.target_query is not None and item.reference is not None:
                raise ValueError("mutation target must be unambiguous")
            if item.action == "update" and not item.fields.model_fields_set:
                raise ValueError("update requires changes")
            if item.action == "delete" and item.fields.model_fields_set:
                raise ValueError("delete cannot change fields")
        return self
```

Build `SUBMIT_PLAN_TOOL` from `IntentPlan.model_json_schema()`:

```python
SUBMIT_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "提交唯一的结构化待办意图计划，不执行写操作",
        "parameters": IntentPlan.model_json_schema(),
    },
}
```

- [ ] **Step 4: Implement policy, prompt, and bounded repair**

Use explicit markers and require a unique detected action:

```python
_ACTION_MARKERS = {
    "create": (r"\b(?:add|create|new)\b", r"(?:新建|创建|添加|新增|记一个|加一个|加个)"),
    "update": (
        r"\b(?:update|change|move|rename|edit|reschedule|postpone)\b",
        r"(?:修改|改成|改到|改为|更改|调整|推迟|提前|重新安排)",
    ),
    "delete": (r"\b(?:delete|remove)\b", r"(?:删除|删掉|移除|取消任务)"),
}

_NEGATED_ACTION = re.compile(
    r"(?:不要|别|无需)\s*(?:新建|创建|添加|新增|加一个|加个|修改|改成|改到|改为|"
    r"更改|调整|删除|删掉|移除)|(?:do\s+not|don't)\s+"
    r"(?:add|create|update|change|move|rename|edit|reschedule|delete|remove)",
    flags=re.IGNORECASE,
)
_QUERY_LIKE = re.compile(
    r"(?:如何|怎么|哪些|是否|有没有|\b(?:how|what|which|whether)\b)",
    flags=re.IGNORECASE,
)
_IMPERATIVE = re.compile(r"(?:请(?!问)|帮我|麻烦|\bplease\b)", flags=re.IGNORECASE)


def explicit_actions(text: str) -> set[ProposalAction]:
    sanitized = _NEGATED_ACTION.sub("", text)
    return {
        action
        for action, patterns in _ACTION_MARKERS.items()
        if any(re.search(pattern, sanitized, flags=re.IGNORECASE) for pattern in patterns)
    }


def validate_explicit_actions(text: str, plan: IntentPlan) -> None:
    if _QUERY_LIKE.search(text) and not _IMPERATIVE.search(text):
        if plan.kind != "query":
            raise PlanPolicyError("EXPLICIT_ACTION_MISMATCH")
        return
    expected = explicit_actions(text)
    planned = {item.action for item in plan.items}
    if expected and (plan.kind != "mutations" or planned != expected):
        raise PlanPolicyError("EXPLICIT_ACTION_MISMATCH")
```

`ArkPlanner.plan_once(user_text, messages, validation_code)` makes exactly one `ark.plan(messages, SUBMIT_PLAN_TOOL)` call, validates with `IntentPlan.model_validate`, applies the explicit-action policy, and raises `PlanValidationError` carrying one stable error code on failure. When the text explicitly contains multiple actions (for example create plus update), the planned item-action set must match all of them; a model cannot add an unrequested delete. The prompt defines `reference` as an exact pending proposal ID copied from the supplied pending context, never the phrase “刚才那个” itself. When `validation_code` is non-null, the prompt asks for one corrected plan and includes only that code plus the original user request. The retry count belongs to `AssistantTurnGraph` in Task 10, so it is visible in graph state and tests. The system prompt states that cards are the only confirmation and that the planner must not ask for confirmation in `evidence` or `query`.

- [ ] **Step 5: Run planning tests and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent/planning.py backend/tests/test_assistant_planning.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/planning.py backend/tests/test_assistant_planning.py
```

Expected: all planning tests PASS and both static checks exit 0.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/agent/planning.py backend/tests/test_assistant_planning.py
git commit -m "feat(agent): enforce structured intent plans"
```

---

### Task 8: Deterministic Task Target Resolution

**Files:**
- Create: `backend/src/todo_backend/agent/task_resolution.py`
- Create: `backend/tests/test_assistant_task_resolution.py`

**Interfaces:**
- Consumes: `TargetQuery`, existing `Task`, and ordered real task IDs from recent proposal events.
- Produces: `TargetResolution(task: Task | None, score: float, error: str | None)` and `resolve_target(...)`.
- Uses: title similarity 0.65, exact start time 0.25, category 0.05, and recency 0.05; threshold is exactly `0.68`.
- Guarantees: referenced IDs must exist in the real task list; unresolved pending creates are never treated as real tasks.

- [ ] **Step 1: Tighten the target schema and write failing resolver tests**

Change `TargetQuery.require_one_selector` from Task 7 so category alone is not sufficient:

```python
if not any((self.title, self.time_start, self.referenced_task_id)):
    raise ValueError("target query requires title, time, or a real referenced task")
```

Create `backend/tests/test_assistant_task_resolution.py`:

```python
def test_exact_reference_wins_when_real_task_exists() -> None:
    older, newer = task("old", "会议", 1), task("new", "会议", 2)
    result = resolve_target(
        TargetQuery(referenced_task_id="old"), [newer, older], recent_task_ids=["new"]
    )
    assert result.task == older
    assert result.score == 1.0


def test_duplicate_titles_choose_most_recent_task() -> None:
    older, newer = task("old", "团队会议", 1), task("new", "团队会议", 2)
    result = resolve_target(
        TargetQuery(title="团队会议"), [older, newer], recent_task_ids=[]
    )
    assert result.task == newer
    assert result.score >= TARGET_THRESHOLD


def test_title_time_and_category_choose_best_candidate() -> None:
    wrong_time = task("a", "项目会议", 2, start="2026-07-22T10:00", category="work")
    expected = task("b", "项目会议", 1, start="2026-07-22T16:00", category="work")
    result = resolve_target(
        TargetQuery(
            title="项目会议", time_start="2026-07-22T16:00", category="work"
        ),
        [wrong_time, expected],
        recent_task_ids=[],
    )
    assert result.task == expected


def test_low_similarity_requires_clarification() -> None:
    result = resolve_target(
        TargetQuery(title="季度财务复盘"),
        [task("a", "买菜", 1), task("b", "晨跑", 2)],
        recent_task_ids=[],
    )
    assert result.task is None
    assert result.error == "TASK_TARGET_AMBIGUOUS"
```

Also cover missing referenced IDs, exact time tie broken by recent context, and an empty task list returning `TASK_TARGET_NOT_FOUND`.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py -v
```

Expected: FAIL because `task_resolution.py` does not exist and the category-only schema is still accepted.

- [ ] **Step 3: Implement the scoring function**

Create `backend/src/todo_backend/agent/task_resolution.py`:

```python
from dataclasses import dataclass
from difflib import SequenceMatcher

from todo_backend.agent.planning import TargetQuery
from todo_backend.models import Task

TARGET_THRESHOLD = 0.68


@dataclass(frozen=True, slots=True)
class TargetResolution:
    task: Task | None
    score: float
    error: str | None = None


def _normalized(value: str) -> str:
    return "".join(value.casefold().split())


def _recency(task: Task, tasks: list[Task], recent_task_ids: list[str]) -> float:
    if task.id in recent_task_ids:
        return 1.0 / (recent_task_ids.index(task.id) + 1)
    ordered = sorted(tasks, key=lambda item: item.created_at, reverse=True)
    return 1.0 / (ordered.index(task) + 2)


def _score(
    query: TargetQuery, task: Task, tasks: list[Task], recent_task_ids: list[str]
) -> float:
    weighted = 0.05 * _recency(task, tasks, recent_task_ids)
    total_weight = 0.05
    if query.title:
        weighted += 0.65 * SequenceMatcher(
            None, _normalized(query.title), _normalized(task.text)
        ).ratio()
        total_weight += 0.65
    if query.time_start:
        weighted += 0.25 * float(task.time is not None and task.time.start == query.time_start)
        total_weight += 0.25
    if query.category:
        weighted += 0.05 * float(task.category == query.category)
        total_weight += 0.05
    return weighted / total_weight


def resolve_target(
    query: TargetQuery,
    tasks: list[Task],
    *,
    recent_task_ids: list[str],
    threshold: float = TARGET_THRESHOLD,
) -> TargetResolution:
    if query.referenced_task_id:
        referenced = next(
            (task for task in tasks if task.id == query.referenced_task_id), None
        )
        return (
            TargetResolution(referenced, 1.0)
            if referenced is not None
            else TargetResolution(None, 0.0, "TASK_TARGET_NOT_FOUND")
        )
    if not tasks:
        return TargetResolution(None, 0.0, "TASK_TARGET_NOT_FOUND")
    ranked = sorted(
        ((_score(query, task, tasks, recent_task_ids), task) for task in tasks),
        key=lambda pair: (pair[0], pair[1].created_at),
        reverse=True,
    )
    score, task = ranked[0]
    if score < threshold:
        return TargetResolution(None, score, "TASK_TARGET_AMBIGUOUS")
    return TargetResolution(task, score)
```

The returned score is rounded only when serialized for audit/display; comparisons use the full float.

- [ ] **Step 4: Run resolver tests and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent/task_resolution.py backend/tests/test_assistant_task_resolution.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/task_resolution.py backend/tests/test_assistant_task_resolution.py
```

Expected: all tests PASS and both static checks exit 0.

- [ ] **Step 5: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/agent/planning.py backend/src/todo_backend/agent/task_resolution.py backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py
git commit -m "feat(agent): resolve mutation targets deterministically"
```

---

### Task 9: Full-State Proposal Construction and Verification

**Files:**
- Create: `backend/src/todo_backend/agent/proposals.py`
- Create: `backend/tests/test_assistant_proposals.py`

**Interfaces:**
- Consumes: an `IntentPlan`, one resolved real `Task` or pending-proposal reference per update/delete item, and the optional complete superseded batch for sibling copy-forward.
- Produces: verified `BatchDraft` objects from Task 2.
- Guarantees: complete create/update payloads, preserved partial time values, before snapshots, no-op rejection, create/update grouping, and isolated delete batches.

- [ ] **Step 1: Lock in partial planner-field behavior**

`PlannedFields` contains partial planner changes and intentionally has no cross-field time validator. `ProposalCardFields` is the complete persisted/API shape; cross-field validity is enforced by `verify_drafts` and `ProposalBatchExecutor._validated_full_payload`. Add this regression test:

```python
def test_planner_fields_allow_end_only_before_overlay() -> None:
    fields = PlannedFields(time_end="2026-07-22T17:00")
    assert fields.model_fields_set == {"time_end"}
```

- [ ] **Step 2: Write failing construction tests**

Create `backend/tests/test_assistant_proposals.py`:

```python
def test_update_end_only_preserves_snapshot_start() -> None:
    current = task(
        "t1", "会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    plan = update_plan(TargetQuery(title="会议"), PlannedFields(
        time_end="2026-07-22T17:00"
    ))

    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=current)], superseded_batch=None
    )

    proposal = drafts[0].proposals[0]
    assert proposal.before_snapshot == current
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"


def test_create_and_update_share_one_batch_but_deletes_are_isolated() -> None:
    current = task("t1", "旧任务")
    second = task("t2", "第二个旧任务")
    plan = mutation_plan([
        planned_create("新任务"),
        planned_update(TargetQuery(referenced_task_id="t1"), text="已修改"),
        planned_delete(TargetQuery(referenced_task_id="t1")),
        planned_delete(TargetQuery(referenced_task_id="t2")),
    ])
    drafts = build_batch_drafts(
        "turn-1", plan,
        [ResolvedMutation(), ResolvedMutation(task=current),
         ResolvedMutation(task=current), ResolvedMutation(task=second)],
        superseded_batch=None,
    )
    assert [len(batch.proposals) for batch in drafts] == [2, 1, 1]
    assert [proposal.action for proposal in drafts[0].proposals] == ["create", "update"]
    assert all(batch.proposals[0].action == "delete" for batch in drafts[1:])


def test_update_reference_to_pending_create_builds_superseding_create() -> None:
    old_batch = pending_create_batch(
        [("p-old", "开会")], batch_id="b-old", hour=15
    )
    pending = old_batch.proposals[0]
    plan = mutation_plan([
        planned_update(reference="p-old", time_start="2026-07-22T16:00")
    ])

    drafts = build_batch_drafts(
        "turn-2", plan, [ResolvedMutation(pending=pending)],
        superseded_batch=old_batch,
    )

    proposal = drafts[0].proposals[0]
    assert proposal.action == "create"
    assert proposal.target_task_id is None
    assert proposal.payload.text == "开会"
    assert proposal.payload.time_start == "2026-07-22T16:00"
    assert drafts[0].supersedes_batch_id == "b-old"


def test_referenced_edit_copies_unmentioned_pending_sibling() -> None:
    old_batch = pending_create_batch(
        [("p-a", "A"), ("p-b", "B")], batch_id="b-old"
    )
    plan = mutation_plan([
        planned_update(reference="p-a", notes="只修改 A"),
    ])
    drafts = build_batch_drafts(
        "turn-2", plan,
        [ResolvedMutation(pending=old_batch.proposals[0])],
        superseded_batch=old_batch,
    )
    assert [proposal.payload.text for proposal in drafts[0].proposals] == ["A", "B"]
    assert drafts[0].proposals[0].payload.notes == "只修改 A"
    assert drafts[0].proposals[1].payload == old_batch.proposals[1].payload
    assert drafts[0].supersedes_batch_id == old_batch.id


def test_unrelated_group_does_not_steal_supersedes_link() -> None:
    old_delete = pending_delete_batch("b-old", "p-old", "t1")
    plan = mutation_plan([
        planned_create("无关新任务"),
        planned_delete(reference="p-old"),
    ])
    drafts = build_batch_drafts(
        "turn-2", plan,
        [ResolvedMutation(), ResolvedMutation(pending=old_delete.proposals[0])],
        superseded_batch=old_delete,
    )
    assert drafts[0].proposals[0].action == "create"
    assert drafts[0].supersedes_batch_id is None
    assert drafts[1].proposals[0].action == "delete"
    assert drafts[1].supersedes_batch_id == "b-old"


def test_pending_correction_and_new_create_share_replacement_batch() -> None:
    old_batch = pending_create_batch(
        [("p-a", "A"), ("p-b", "B")], batch_id="b-old"
    )
    plan = mutation_plan([
        planned_update(reference="p-a", notes="修正 A"),
        planned_create("C"),
    ])
    drafts = build_batch_drafts(
        "turn-2", plan,
        [ResolvedMutation(pending=old_batch.proposals[0]), ResolvedMutation()],
        superseded_batch=old_batch,
    )
    assert len(drafts) == 1
    assert [item.payload.text for item in drafts[0].proposals] == ["A", "B", "C"]
    assert drafts[0].supersedes_batch_id == "b-old"


def test_update_noop_is_rejected() -> None:
    current = task("t1", "会议")
    with pytest.raises(ProposalVerificationError, match="UPDATE_HAS_NO_CHANGES"):
        build_batch_drafts(
            "turn-1",
            update_plan(TargetQuery(title="会议"), PlannedFields(text="会议")),
            [ResolvedMutation(task=current)],
            superseded_batch=None,
        )


def test_stable_ids_repeat_for_same_turn() -> None:
    first = build_batch_drafts(
        "turn-1", create_plan("买菜"), [ResolvedMutation()], superseded_batch=None
    )
    second = build_batch_drafts(
        "turn-1", create_plan("买菜"), [ResolvedMutation()], superseded_batch=None
    )
    assert first[0].id == second[0].id
    assert first[0].proposals[0].id == second[0].proposals[0].id
```

Also test default priority/category, blank titles, end without start, end before start, update/delete missing resolved targets, complete delete snapshots, and superseded-batch linkage.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_proposals.py backend/tests/test_assistant_planning.py -v
```

Expected: FAIL because proposal construction functions do not exist.

- [ ] **Step 4: Implement full-state overlay and stable grouping**

Create `backend/src/todo_backend/agent/proposals.py` with these core helpers:

```python
_ID_NAMESPACE = UUID("8cd168ad-1114-4cb4-921a-18cd0ff0f395")


class ProposalVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedMutation:
    task: Task | None = None
    pending: AssistantProposal | None = None

    def __post_init__(self) -> None:
        if self.task is not None and self.pending is not None:
            raise ValueError("resolved mutation has two targets")


def fields_from_task(task: Task) -> ProposalCardFields:
    return ProposalCardFields(
        text=task.text,
        priority=task.priority,
        category=task.category,
        time_start=task.time.start if task.time else None,
        time_end=task.time.end if task.time else None,
        notes=task.notes,
    )


def _overlay(
    before: ProposalCardFields, changes: PlannedFields
) -> ProposalCardFields:
    values = before.model_dump()
    for field_name in changes.model_fields_set:
        values[field_name] = getattr(changes, field_name)
    if "time_start" in changes.model_fields_set and changes.time_start is None:
        values["time_end"] = None
    return ProposalCardFields.model_validate(values)


def _stable_id(turn_id: str, kind: str, index: int) -> str:
    return uuid5(_ID_NAMESPACE, f"{turn_id}:{kind}:{index}").hex


def _single_source_batch(proposals: list[ProposalDraft]) -> str | None:
    source_ids = {
        proposal.source_batch_id
        for proposal in proposals
        if proposal.source_batch_id is not None
    }
    if len(source_ids) > 1:
        raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")
    return next(iter(source_ids), None)


def group_verified_drafts(
    turn_id: str,
    proposals: list[ProposalDraft],
) -> list[BatchDraft]:
    grouped: list[BatchDraft] = []
    editable = [proposal for proposal in proposals if proposal.action != "delete"]
    if editable:
        grouped.append(BatchDraft(
            id=_stable_id(turn_id, "batch", 0),
            supersedes_batch_id=_single_source_batch(editable),
            proposals=editable,
        ))
    for offset, proposal in enumerate(
        (item for item in proposals if item.action == "delete"), start=len(grouped)
    ):
        grouped.append(BatchDraft(
            id=_stable_id(turn_id, "batch", offset),
            supersedes_batch_id=proposal.source_batch_id,
            proposals=[proposal],
        ))
    return grouped
```

`build_batch_drafts` iterates each `PlannedMutation.action` and creates proposal IDs with `_stable_id(turn_id, "proposal", item_index)`. A create receives complete defaults (`priority="medium"`, `category="other"`, explicit `None` for time/notes). An update of a real task starts from `fields_from_task(current)` and overlays only `changes.model_fields_set`. A delete stores both `before_snapshot=current` and `payload=fields_from_task(current)`.

For an item with `reference`, Task 10 must have resolved one still-pending proposal from the business database and supplied its complete old batch. Apply these exact compatibility rules: update→pending-create produces a new create draft by overlaying the new planned fields on the pending proposal's complete payload; update→pending-update produces a new update draft by the same overlay, retaining the old `before_snapshot`/`target_task_id`; delete→pending-delete reproduces the isolated delete draft. All other action/reference pairs raise `PENDING_REFERENCE_ACTION_MISMATCH`, and references spanning multiple old batches raise `MULTIPLE_SUPERSEDED_BATCHES`.

Before adding unrelated new mutations, deterministically copy forward every still-pending sibling in the old batch that was not explicitly referenced, preserving original order, action, target, snapshot, and complete payload. Replacement and copied drafts carry transient `source_batch_id/source_proposal_id`; unrelated new drafts carry neither. `_single_source_batch` requires at most one source among a group. `group_verified_drafts` attaches `supersedes_batch_id` only to the output batch containing source drafts—editable or delete—so an unrelated group cannot steal the audit link. This preserves sibling proposals when only one item is corrected and still allows the same turn to add unrelated create/update work. Pending creates remain proposal context and are never inserted into or scored as real tasks.

`verify_drafts` raises `ProposalVerificationError` with one of these stable codes: `CREATE_TITLE_REQUIRED`, `TARGET_REQUIRED`, `TIME_END_REQUIRES_START`, `TIME_END_BEFORE_START`, `UPDATE_HAS_NO_CHANGES`, `DELETE_BATCH_NOT_ISOLATED`, `DUPLICATE_PROPOSAL`, `PENDING_REFERENCE_ACTION_MISMATCH`, or `MULTIPLE_SUPERSEDED_BATCHES`. It runs before any repository write.

- [ ] **Step 5: Run proposal tests and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_proposals.py backend/tests/test_assistant_planning.py backend/tests/test_proposal_batch_service.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent/proposals.py backend/tests/test_assistant_proposals.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent/proposals.py backend/tests/test_assistant_proposals.py
```

Expected: all tests PASS and both static checks exit 0.

- [ ] **Step 6: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/models.py backend/src/todo_backend/agent/proposals.py backend/tests/test_assistant_proposals.py backend/tests/test_assistant_planning.py backend/tests/test_proposal_batch_service.py
git commit -m "feat(agent): build verified full-state proposals"
```

---

### Task 10: AssistantTurnGraph

**Files:**
- Create: `backend/src/todo_backend/agent/turn_graph.py`
- Create: `backend/tests/test_assistant_turn_graph.py`

**Interfaces:**
- Consumes: Task 2 repositories, Task 5 apply workflow, Task 7 planner, Task 8 resolver, Task 9 proposal builder, and a LangGraph checkpointer.
- Produces: `AssistantTurnWorkflow.run(turn_id) -> AssistantTurnResponse`.
- Guarantees: explicit query/mutation routes, maximum two plan repairs, no real task write, atomic supersede/new-batch persistence, apply-graph initialization before returning cards, and resumable failures.

- [ ] **Step 1: Write failing graph behavior tests**

Create `backend/tests/test_assistant_turn_graph.py` with real temporary business SQLite and `InMemorySaver`:

```python
def test_explicit_create_never_updates_duplicate_title(graph_fixture: TurnFixture) -> None:
    existing = graph_fixture.create_task("团队会议")
    graph_fixture.planner.results = [create_plan("团队会议")]

    result = graph_fixture.run_user_turn("turn-1", "新建一个团队会议")

    proposal = result.proposal_batches[0].proposals[0]
    assert proposal.action == "create"
    assert proposal.target_task_id is None
    assert graph_fixture.task_service.list_all() == [existing]


def test_update_resolves_target_and_exposes_before_after(graph_fixture: TurnFixture) -> None:
    target = graph_fixture.create_task(
        "团队会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    graph_fixture.planner.results = [update_plan(
        TargetQuery(title="团队会议"), PlannedFields(time_end="2026-07-22T17:00")
    )]

    result = graph_fixture.run_user_turn("turn-2", "把团队会议结束时间改成五点")

    proposal = result.proposal_batches[0].proposals[0]
    assert proposal.target_task_id == target.id
    assert proposal.before_snapshot == target
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"


def test_correction_supersedes_old_batch_atomically(graph_fixture: TurnFixture) -> None:
    first = graph_fixture.run_with_plan(
        "turn-1", "新建下午三点的会议", mutation_plan([planned_create("开会", hour=15)])
    )
    old_batch = first.proposal_batches[0]
    old_proposal = old_batch.proposals[0]
    second = graph_fixture.run_with_plan(
        "turn-2",
        "把刚才那个改成四点",
        mutation_plan([planned_update(reference=old_proposal.id, hour=16)]),
    )
    detail = graph_fixture.detail()
    assert next(batch for batch in detail.proposal_batches if batch.id == old_batch.id).status \
        == "superseded"
    assert second.proposal_batches[0].supersedes_batch_id == old_batch.id
    replacement = second.proposal_batches[0].proposals[0]
    assert replacement.action == "create"
    assert replacement.target_task_id is None
    assert replacement.payload.time_start == "2026-07-22T16:00"
    assert [batch.status for batch in detail.proposal_batches].count("pending") == 1


def test_low_target_score_returns_clarification_without_proposal(graph_fixture: TurnFixture) -> None:
    graph_fixture.create_task("买菜")
    graph_fixture.planner.results = [update_plan(
        TargetQuery(title="季度财务复盘"), PlannedFields(time_end="2026-07-22T17:00")
    )]
    result = graph_fixture.run_user_turn("turn-3", "把季度财务复盘改到五点")
    assert result.proposal_batches == []
    assert "具体任务" in result.message.content
```

Also test query route, invalid plan ending in failed status after two repair attempts, stable retry not duplicating batches, apply workflow `start` called exactly once per stable batch, and no `TaskRepository.create/update/delete` call during the turn graph.

The invalid-plan case must prove that “two repairs” means one initial attempt plus two repair attempts:

```python
def test_invalid_plan_stops_after_two_graph_repairs(graph_fixture: TurnFixture) -> None:
    graph_fixture.planner.errors = ["INVALID_PLAN", "INVALID_PLAN", "INVALID_PLAN"]
    result = graph_fixture.run_user_turn("turn-invalid", "改一下")
    assert result.message.status == "failed"
    assert graph_fixture.planner.call_count == 3
    state = graph_fixture.workflow.graph.get_state(
        graph_fixture.workflow.config("turn-invalid")
    ).values
    assert state["repair_count"] == 2
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_turn_graph.py -v
```

Expected: FAIL because `turn_graph.py` does not exist.

- [ ] **Step 3: Define JSON-safe state and graph topology**

Create `backend/src/todo_backend/agent/turn_graph.py`:

```python
class AssistantTurnState(TypedDict, total=False):
    turn_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    language: str
    context_summary: dict[str, Any]
    plan: dict[str, Any]
    resolved_task_ids: list[str | None]
    resolved_pending_proposal_ids: list[str | None]
    candidate_scores: list[float]
    pending_batch_id: str | None
    draft_batches: list[dict[str, Any]]
    response_text: str
    repair_count: int
    validation_error: str | None
    error_code: str | None


def _build_graph(self, checkpointer: BaseCheckpointSaver[str]):
    builder = StateGraph(AssistantTurnState)
    builder.add_node("load_context", self._load_context)
    builder.add_node("plan_intent", self._plan_intent)
    builder.add_node("repair_plan", self._repair_plan)
    builder.add_node("execute_read", self._execute_read)
    builder.add_node("verify_answer", self._verify_answer)
    builder.add_node("resolve_targets", self._resolve_targets)
    builder.add_node("select_superseded", self._select_superseded)
    builder.add_node("build_proposals", self._build_proposals)
    builder.add_node("verify_proposals", self._verify_proposals)
    builder.add_node("persist_batches", self._persist_batches)
    builder.add_node("initialize_reviews", self._initialize_reviews)
    builder.add_node("finalize", self._finalize)
    builder.add_node("finalize_error", self._finalize_error)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "plan_intent")
    builder.add_conditional_edges(
        "plan_intent", self._intent_route,
        {
            "query": "execute_read",
            "mutation": "resolve_targets",
            "repair": "repair_plan",
            "error": "finalize_error",
        },
    )
    builder.add_edge("repair_plan", "plan_intent")
    builder.add_edge("execute_read", "verify_answer")
    builder.add_conditional_edges(
        "verify_answer", self._answer_route,
        {"valid": "finalize", "invalid": "finalize_error"},
    )
    builder.add_edge("resolve_targets", "select_superseded")
    builder.add_conditional_edges(
        "select_superseded", self._resolution_route,
        {"resolved": "build_proposals", "clarify": "finalize"},
    )
    builder.add_edge("build_proposals", "verify_proposals")
    builder.add_conditional_edges(
        "verify_proposals", self._verification_route,
        {
            "valid": "persist_batches",
            "repair": "repair_plan",
            "error": "finalize_error",
        },
    )
    builder.add_edge("persist_batches", "initialize_reviews")
    builder.add_edge("initialize_reviews", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("finalize_error", END)
    return builder.compile(checkpointer=checkpointer)
```

The state stores only primitive dicts/IDs. Every node that needs messages, pending batches, or tasks reloads them from the business database.

- [ ] **Step 4: Implement node responsibilities and persistence order**

Use a dependency bundle so tests can inject fakes:

```python
@dataclass(frozen=True, slots=True)
class TurnGraphDependencies:
    database: Database
    conversations: ConversationsRepository
    batches: ProposalBatchesRepository
    tasks: TaskService
    planner: PlannerProtocol
    ark: ArkClientProtocol
    apply_workflow: ProposalApplyWorkflow
    build_ark_messages: ArkMessageBuilderProtocol
```

`_load_context` stores `context_summary`, a bounded JSON-safe index containing turn/conversation/message IDs plus proposal/batch IDs, actions, target/result IDs, and statuses; it initializes `repair_count=0`. It does not store message bodies, task titles, full pending fields, or attachment data in checkpoint state. `_plan_intent` reloads messages and pending batches by `conversation_id`, constructs the full pending-card context only in local memory for that call, invokes injected `build_ark_messages(messages, language)`, and passes the reconstructed Ark history plus the transient pending context to `planner.plan_once(..., validation_code=state.get("validation_error"))`. The builder is the existing attachment-safe behavior moved behind a protocol: image files become bounded `data:` image parts after path validation, document/audio `extractedText` is appended to text, only the last `HISTORY_LIMIT` messages are included, and missing files raise the existing typed upload error. Add graph/service tests proving image and extracted document/audio content reach the planner while serialized graph state contains only IDs/status summaries.

On planning success, `_plan_intent` stores `IntentPlan.model_dump(mode="json")` and clears the error; on `PlanValidationError` it stores only the stable validation code. `_intent_route` selects `repair` while `repair_count < 2`; `_verification_route` does the same for repairable proposal errors and routes invariant/database errors directly to `error`. `_repair_plan` increments the shared `repair_count` by one and returns to `plan_intent`; after the third failed plan/proposal cycle it routes to `finalize_error`. Add a test in which a schema-valid plan produces `TIME_END_REQUIRES_START`, the second plan repairs it, and `planner.call_count == 2`.

`_resolve_targets` handles each item independently. A `target_query` is scored only against real tasks. A `reference` is queried by exact proposal ID from the business repository, then checked for the same conversation and a still-confirmable pending batch; it writes only the selected ID to `resolved_pending_proposal_ids` and never puts a pending create in `resolved_task_ids`. Unknown/stale references produce a repairable `PENDING_REFERENCE_NOT_FOUND`. A low real-task score sets `response_text` to a deterministic localized clarification and writes no draft. `_select_superseded` reloads the selected proposal rows, requires all referenced rows (if any) to belong to one old batch, and records that batch ID without mutating it; unrelated non-reference mutations remain allowed. `_build_proposals` reloads the complete old batch plus exact selected rows and applies Task 9's overlay/copy-forward rules, including update→pending-create becoming a replacement create proposal and every unmentioned pending sibling surviving in the new batch. A pending-update correction starts from the old pending proposal's complete payload and overlays only the newly planned fields, while retaining its original `before_snapshot` and `target_task_id`. Explicit-action verification applies to planned item actions, not the underlying proposal action preserved from a pending reference.

`_persist_batches` reconstructs and re-verifies drafts, then uses one business transaction:

```python
with self._deps.database.transaction() as connection:
    existing = self._deps.batches.list_for_message(
        connection, state["assistant_message_id"]
    )
    if existing:
        batches = existing
    else:
        batches = self._deps.batches.insert_batches(
            connection,
            conversation_id=state["conversation_id"],
            message_id=state["assistant_message_id"],
            drafts=drafts,
        )
        if state.get("pending_batch_id"):
            self._deps.batches.supersede(
                connection, state["pending_batch_id"], _now_ms()
            )
    self._deps.conversations.update_message(
        connection,
        state["assistant_message_id"],
        content=self._proposal_message(state["language"], batches),
        status="done",
        tool_trace=None,
    )
return {"draft_batches": [batch.model_dump(mode="json", by_alias=True) for batch in batches]}
```

Do not mark the turn `done` in `_persist_batches`. `_initialize_reviews` calls `apply_workflow.start(batch.id)` for every batch; stable threads and `start` make replay safe. `_finalize` then marks the turn `done`. If review initialization fails, the outer service marks the turn `failed`; retry resumes this node and reuses the existing rows.

For a query, `_execute_read` reads real tasks and calls `ark.chat(..., thinking="disabled")` with the bounded task JSON and no tools. `_verify_answer` requires non-empty text and rejects create/update/delete completion claims; the model receives only the bounded read result and no mutation tools. Failure sets `ANSWER_VERIFICATION_FAILED`. `_finalize` persists the verified assistant text and marks the turn done. Mutation reply text is deterministic: Chinese `已生成 {count} 项提议，请检查确认卡。`; English `Created {count} proposals. Review the confirmation card.` It never asks “是否确认”.

- [ ] **Step 5: Implement run/resume semantics**

```python
def run(self, turn_id: str) -> AssistantTurnResponse:
    config = {"configurable": {"thread_id": f"turn:{turn_id}"}}
    with self._deps.database.transaction() as connection:
        turn = self._deps.conversations.get_turn(connection, turn_id)
    checkpoint = self._checkpointer.get_tuple(config)
    snapshot = self.graph.get_state(config)
    if checkpoint is None:
        self.graph.invoke({"turn_id": turn_id}, config=config)
    elif turn.status != "done":
        if snapshot.next:
            self.graph.invoke(None, config=config)
        else:
            self.graph.invoke({"turn_id": turn_id}, config=config)
    with self._deps.database.transaction() as connection:
        message = self._deps.conversations.get_message(
            connection, turn.assistant_message_id
        )
        batches = self._deps.batches.list_for_message(
            connection, turn.assistant_message_id
        )
    return AssistantTurnResponse(message=message, proposalBatches=batches)
```

`snapshot.next` distinguishes a node-level interruption/error from a terminal failed run. The former resumes with `None`; the latter starts a fresh run on the same stable thread with plain input, while `_load_context` resets every per-run field (`plan`, resolved IDs, draft batches, response/error text, validation error, and repair count). This prevents a Retry after `finalize_error -> END` from becoming a no-op that leaves the turn `active`. Add a regression in which three invalid plans produce a terminal failed turn, the same `turnId` is retried with a valid plan, and the existing two messages produce exactly one batch with no duplicate rows.

Add `get_message` and `list_for_message` with direct indexed queries in their respective repositories; do not scan the full conversation. Migration 005's `idx_assistant_batches_message` is the required index for the latter.

- [ ] **Step 6: Run turn graph and upstream tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_turn_graph.py backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py backend/tests/test_assistant_proposals.py backend/tests/test_assistant_apply_graph.py -v
backend/.venv/bin/ruff check backend/src/todo_backend/agent backend/tests/test_assistant_turn_graph.py
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python backend/src/todo_backend/agent backend/tests/test_assistant_turn_graph.py
```

Expected: all selected tests PASS and both static checks exit 0.

- [ ] **Step 7: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/agent/turn_graph.py backend/src/todo_backend/repositories/conversations.py backend/src/todo_backend/repositories/proposal_batches.py backend/tests/test_assistant_turn_graph.py
git commit -m "feat(agent): add verified assistant turn graph"
```

---

### Task 11: Assistant Service, Batch API, Idempotent Retry, and Legacy Removal

**Files:**
- Modify: `backend/src/todo_backend/services/assistant.py`
- Modify: `backend/src/todo_backend/assistant_api.py`
- Modify: `backend/src/todo_backend/api.py`
- Modify: `backend/tests/test_assistant_service.py`
- Modify: `backend/tests/test_assistant_api.py`
- Delete: `backend/src/todo_backend/agent/orchestrator.py`
- Delete: `backend/src/todo_backend/agent/tools.py`
- Delete: `backend/tests/test_assistant_orchestrator.py`
- Delete: `backend/tests/test_assistant_tools.py`

**Interfaces:**
- Produces: `POST /assistant/proposal-batches/{id}/confirm` and `/reject`.
- Preserves: old single-proposal accept/reject routes for single-item batches only.
- Guarantees: stable `turnId`, request fingerprint validation, one active turn per conversation, same-turn process exclusion, checkpoint cleanup, failed-message recovery, and zero Ark calls during confirmation.

- [ ] **Step 1: Add failing service-level retry and confirmation tests**

Replace scripted tool-call tests in `backend/tests/test_assistant_service.py` with structured-plan tests, retaining upload/settings/transcription coverage. Add:

```python
@dataclass(frozen=True, slots=True)
class AssistantFixture:
    service: AssistantService
    fake_ark: FakeArk


def test_retry_same_turn_does_not_duplicate_messages_or_batches(
    assistant: AssistantFixture,
) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    _configure(service)
    fake_ark.plan_results = [ArkUnavailableError("down"), create_plan_payload("买菜")]
    conversation = service.create_conversation()
    command = SendAssistantMessageCommand(
        turnId="turn-retry-1", content="新建买菜任务", attachments=[]
    )

    first = service.send_message(conversation.id, command)
    second = service.send_message(conversation.id, command)
    detail = service.get_conversation_detail(conversation.id)

    assert first.message.status == "failed"
    assert second.message.status == "done"
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1
    assert len(detail.proposal_batches[0].proposals) == 1


def test_same_turn_id_with_changed_payload_is_rejected(
    assistant: AssistantFixture,
) -> None:
    service = assistant.service
    _configure(service)
    conversation = service.create_conversation()
    service.send_message(conversation.id, SendAssistantMessageCommand(
        turnId="turn-fixed", content="新建 A", attachments=[]
    ))
    with pytest.raises(AssistantTurnPayloadMismatchError):
        service.send_message(conversation.id, SendAssistantMessageCommand(
            turnId="turn-fixed", content="新建 B", attachments=[]
        ))


def test_confirm_edited_batch_never_calls_ark(assistant: AssistantFixture) -> None:
    service, fake_ark = assistant.service, assistant.fake_ark
    batch = seed_create_batch(service.database, text="原标题")
    fake_ark.reset_mock()

    result = service.confirm_proposal_batch(
        batch.id,
        ConfirmProposalBatchCommand(items=[ConfirmProposalItem(
            proposalId=batch.proposals[0].id,
            payload=ProposalCardFields(
                text="卡片编辑后", priority="high", category="work",
                time_start=None, time_end=None, notes="直接写入",
            ),
        )]),
    )

    assert result.items[0].task is not None
    assert result.items[0].task.text == "卡片编辑后"
    assert fake_ark.mock_calls == []


def test_turn_graph_resumes_from_sqlite_after_service_reopen(
    persistent_service_factory: PersistentServiceFactory,
) -> None:
    first_ark = FakeArk(plan_results=[ArkUnavailableError("temporary")])
    first = persistent_service_factory.open(first_ark)
    _configure(first)
    conversation = first.create_conversation()
    command = SendAssistantMessageCommand(
        turnId="turn-restart-1", content="新建买菜任务", attachments=[]
    )
    assert first.send_message(conversation.id, command).message.status == "failed"
    first.close()

    second_ark = FakeArk(plan_results=[create_plan_payload("买菜")])
    second = persistent_service_factory.open(second_ark)
    result = second.send_message(conversation.id, command)
    detail = second.get_conversation_detail(conversation.id)
    second.close()

    assert result.message.status == "done"
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1
    assert len(detail.proposal_batches[0].proposals) == 1
```

Replace the existing `service` fixture with an `assistant` fixture that creates one `FakeArk`, injects it through `ark_factory=lambda _settings: fake_ark`, and returns `AssistantFixture(service, fake_ark)`; existing tests use `assistant.service`.

`PersistentServiceFactory` uses the same temporary business database, upload directory, and real `CheckpointStore` path across `open()` calls; only the service/SQLite connections and fake Ark instance change. Assert the first service truly wrote a `turn:turn-restart-1` checkpoint before close and the second resumed it without duplicate rows. Also test: concurrent different turn IDs receive `AssistantTurnActiveError`; accepted turn replay returns the stored response; partial application returns HTTP-success item errors; delete conversation removes exact `turn:*` and `proposal:*` threads; an unexpected graph error changes `active` to `failed`.

- [ ] **Step 2: Add failing API tests**

Add these cases to `backend/tests/test_assistant_api.py`:

```python
def test_message_request_requires_and_echoes_stable_turn_id(client: TestClient) -> None:
    conversation_id = configured_conversation(client)
    response = client.post(
        f"/api/v1/assistant/conversations/{conversation_id}/messages",
        headers=_HEADERS,
        json={"turnId": "turn-http-1", "content": "新建买菜任务", "attachments": []},
    )
    assert response.status_code == 200
    assert response.json()["message"]["turnId"] == "turn-http-1"
    assert "proposalBatches" in response.json()
    assert "proposals" not in response.json()


def test_confirm_batch_accepts_edited_fields_and_returns_item_results(client: TestClient) -> None:
    batch = create_batch_over_http(client)
    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json={"items": [{
            "proposalId": batch["proposals"][0]["id"],
            "payload": {
                "text": "卡片编辑后", "priority": "high", "category": "work",
                "time_start": None, "time_end": None, "notes": None,
            },
        }]},
    )
    assert response.status_code == 200
    assert response.json()["batch"]["status"] == "accepted"
    assert response.json()["items"][0]["task"]["text"] == "卡片编辑后"


def test_superseded_batch_confirm_returns_conflict(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assistant/proposal-batches/superseded/confirm",
        headers=_HEADERS,
        json={"items": [{"proposalId": "p-old", "payload": None}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_BATCH_NOT_CONFIRMABLE"
```

Also cover batch reject, batch not found, payload mismatch, active-turn conflict, idempotent repeated confirmation, and legacy single-proposal endpoints rejecting multi-item batches with `PROPOSAL_BATCH_REQUIRED`.

- [ ] **Step 3: Run service/API tests and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_service.py backend/tests/test_assistant_api.py -v
```

Expected: FAIL because the service still constructs `AgentOrchestrator`/`AgentTools` and the batch endpoints do not exist.

- [ ] **Step 4: Implement turn creation, fingerprinting, and in-process exclusion**

Define these service-boundary errors next to the existing assistant errors, then add stable fingerprinting and a process-local same-turn guard to `AssistantService`:

```python
class AssistantTurnActiveError(RuntimeError):
    pass


class AssistantTurnPayloadMismatchError(RuntimeError):
    pass


class ProposalBatchRequiredError(RuntimeError):
    pass


def _request_fingerprint(command: SendAssistantMessageCommand) -> str:
    stable_request = {
        "content": command.content,
        "attachmentFileIds": [attachment.file_id for attachment in command.attachments],
    }
    serialized = json.dumps(
        stable_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@contextmanager
def _claim_running_turn(self, turn_id: str) -> Iterator[None]:
    with self._running_turns_lock:
        if turn_id in self._running_turns:
            raise AssistantTurnActiveError
        self._running_turns.add(turn_id)
    try:
        yield
    finally:
        with self._running_turns_lock:
            self._running_turns.discard(turn_id)
```

Fingerprint only immutable client intent: exact content plus attachment `fileId` values in request order. Do not hash `extractedText`, name, or MIME because the backend may enrich/normalize those fields after the first request; a refresh-and-Retry must still match the original turn. Add a service test with a document/audio attachment whose first command has `extractedText=null`, whose stored user message is enriched, and whose Retry reuses the same `turnId` without `ASSISTANT_TURN_PAYLOAD_MISMATCH` or duplicate rows.

In `send_message`, use short business transactions around row changes only:

1. Load an existing turn by `command.turn_id` if present.
2. Require the same conversation and fingerprint.
3. Return stored response immediately when status is `done`.
4. Change `failed` back to `active` for Retry.
5. For a new turn, validate attachment file identity/path outside a database transaction, then in one short transaction insert exactly one user message with verified but not-yet-enriched attachments, one pending assistant message with the same `turn_id`, and the active turn. Translate the partial-index `sqlite3.IntegrityError` to `AssistantTurnActiveError`.
6. After the active row exists, parse documents and perform audio transcription outside every SQLite transaction. In a second short transaction, idempotently replace the stored user-message attachments with enriched values. Retry reuses already enriched stored attachments and enriches only a still-null document/audio item.

Claim `_claim_running_turn` around enrichment plus graph execution, build an `AssistantTurnWorkflow` with the current Ark client and shared checkpointer, and call `run(turn_id)`. No PDF parsing, filesystem read, audio/model network request, or graph call may run while `BEGIN IMMEDIATE` is held. An `AssistantTurnActiveError` from the process-local claim is re-raised without changing the shared turn/message status—the winning request still owns it. On `ArkUnavailableError`, mark the existing assistant message and turn failed and return `AssistantTurnResponse(message=failed, proposalBatches=[])`. On any other exception, mark both failed and re-raise so the existing error middleware responds; no row remains active.

- [ ] **Step 5: Wire the checkpoint/apply lifecycle**

Construct these members in `AssistantService.__init__`:

```python
self._checkpoint_store = checkpoint_store or CheckpointStore(
    settings.database_path.parent / "assistant_graph.sqlite3"
)
self._batch_repository = ProposalBatchesRepository()
self._batch_executor = ProposalBatchExecutor(database, self._batch_repository)
self._apply_workflow = ProposalApplyWorkflow(
    self._batch_executor, self._checkpoint_store.saver
)
self._running_turns: set[str] = set()
self._running_turns_lock = threading.Lock()
self._ark_cache: tuple[AssistantSettings, ArkClientProtocol] | None = None
```

Change `_require_ark` to reuse the cached client when the complete in-memory `AssistantSettings` value is unchanged; invalidate the cache after a successful assistant-settings update. Never serialize or log the cached settings/key. This lets `ArkClient.planning_thinking_supported=False` survive across turns in the service, so an unsupported model is probed only once per settings configuration. Add a service test with two turns: the first performs enabled→disabled fallback, the second sends only disabled thinking.

Add:

```python
def close(self) -> None:
    self._checkpoint_store.close()


def confirm_proposal_batch(
    self, batch_id: str, command: ConfirmProposalBatchCommand
) -> ProposalBatchResolveResponse:
    current = self._batch_executor.current(batch_id)
    if current.batch.status == "superseded":
        raise ProposalBatchNotConfirmableError
    if not any(item.proposal.status == "pending" for item in current.items):
        return current
    self._apply_workflow.start(batch_id)
    return self._apply_workflow.confirm(batch_id, command)


def reject_proposal_batch(self, batch_id: str) -> ProposalBatchResolveResponse:
    current = self._batch_executor.current(batch_id)
    if current.batch.status == "superseded":
        raise ProposalBatchNotConfirmableError
    if not any(item.proposal.status == "pending" for item in current.items):
        return current
    self._apply_workflow.start(batch_id)
    return self._apply_workflow.reject(batch_id)
```

Calling idempotent `start` immediately before resume is mandatory for migration-005 legacy pending batches: they have business rows but no historical LangGraph checkpoint. Add a service test that migrates/seeds such a batch, confirms it successfully on the first request, and asserts one `proposal:{batch_id}` thread now exists. The superseded check stays before the no-pending idempotency return, so an old replaced card always receives the documented 409 instead of appearing successfully resolved.

For conversation deletion, read turn and batch IDs before deleting the business rows, then call `delete_thread(f"turn:{id}")` and `delete_thread(f"proposal:{id}")` for those exact IDs. `create_app` must close the service in a FastAPI lifespan handler:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        resolved_assistant_service.close()

app = FastAPI(lifespan=lifespan)
```

- [ ] **Step 6: Add batch routes and stable error handlers**

Add to `assistant_api.py`:

```python
@router.post(
    "/assistant/proposal-batches/{batch_id}/confirm",
    response_model=ProposalBatchResolveResponse,
)
def _confirm_batch(
    batch_id: str, command: ConfirmProposalBatchCommand
) -> ProposalBatchResolveResponse:
    return service.confirm_proposal_batch(batch_id, command)


@router.post(
    "/assistant/proposal-batches/{batch_id}/reject",
    response_model=ProposalBatchResolveResponse,
)
def _reject_batch(batch_id: str) -> ProposalBatchResolveResponse:
    return service.reject_proposal_batch(batch_id)
```

Map errors in `api.py`: `ProposalBatchNotFoundError` → 404 `PROPOSAL_BATCH_NOT_FOUND`; `InvalidProposalBatchCommandError` → 422 `INVALID_CONFIRMATION_PAYLOAD`; `ProposalBatchNotConfirmableError` → 409 `PROPOSAL_BATCH_NOT_CONFIRMABLE`; `AssistantTurnActiveError` → 409 `ASSISTANT_TURN_ACTIVE`; `AssistantTurnPayloadMismatchError` → 409 `ASSISTANT_TURN_PAYLOAD_MISMATCH`; `ProposalBatchRequiredError` → 409 `PROPOSAL_BATCH_REQUIRED`.

Replace the existing `ProposalNotFoundError` import/handler with the canonical class from `repositories.proposal_batches`; keep its existing single-proposal 404 error code for compatibility.

Do not enable `response_model_exclude_none` on conversation detail, message-turn, or batch-resolution responses: snapshots, result tasks, optional timestamps, errors, and nullable task fields are explicit `null` values in the TypeScript contract. Keep `exclude_none` only on unrelated legacy endpoints whose current response shape already depends on omission.

Retain the old proposal endpoints by looking up the proposal's batch, requiring `len(batch.proposals) == 1`, and forwarding its stored payload to `confirm_proposal_batch` or forwarding to `reject_proposal_batch`. Repeated legacy acceptance returns the prior result instead of raising the old `ProposalAlreadyResolvedError`.

- [ ] **Step 7: Delete the obsolete loop only after replacements pass**

Run the new agent/service/API tests first. When they pass and `rg` shows no production import, delete the four exact obsolete files with `apply_patch` (`*** Delete File`), not a broad filesystem command:

```bash
rg -n "AgentOrchestrator|AgentTools|TOOL_SCHEMAS|MAX_TOOL_ITERATIONS" backend/src backend/tests
```

Expected before deletion: matches exist only in those four obsolete files. Expected after deletion: `rg` exits 1 with no matches.

- [ ] **Step 8: Run the complete backend suite and static checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests -v
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python
```

Expected: all backend tests PASS (the previous 127-test baseline plus new tests; packaging smoke may remain one documented skip when `TODO_BACKEND_BINARY` is unset), Ruff exits 0, and Pyright reports 0 errors.

- [ ] **Step 9: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add backend/src/todo_backend/services/assistant.py backend/src/todo_backend/assistant_api.py backend/src/todo_backend/api.py backend/tests/test_assistant_service.py backend/tests/test_assistant_api.py backend/src/todo_backend/agent backend/tests
git commit -m "feat(agent): expose idempotent batch confirmation API"
```

---

### Task 12: Frontend Batch Client and State

**Files:**
- Modify: `frontend/src/shared/api/contracts.ts:77-177`
- Modify: `frontend/src/shared/api/client.ts:1-226`
- Modify: `frontend/src/shared/api/__tests__/assistant-client.test.ts`
- Modify: `frontend/src/features/assistant/hooks/useAssistant.ts`
- Modify: `frontend/src/features/assistant/__tests__/useAssistant.test.ts`

**Interfaces:**
- Produces: TypeScript mirrors of proposal batches, snapshots, per-item results, and edited confirmation commands.
- Produces: `sendAssistantMessage(..., {turnId, content, attachments})`, `confirmAssistantProposalBatch`, and `rejectAssistantProposalBatch`.
- Removes from `TodoApi`: frontend use of single-proposal accept/reject methods; backend compatibility routes remain.
- Produces: stable-turn retry and server-owned batch state in `useAssistant`.

- [ ] **Step 1: Write failing client tests**

Replace the old proposal-resolution test and extend the message test:

```typescript
it('sends the stable turn id with the message', async () => {
  const turn = {
    message: {
      id: 'm2', turnId: 'turn-1', role: 'assistant', content: '好',
      attachments: [], status: 'done', createdAt: 2,
    },
    proposalBatches: [],
  };
  const fetcher = vi.fn().mockResolvedValue(jsonResponse(turn));
  const api = createTodoApi(connection, fetcher);

  await api.sendAssistantMessage('c1', {
    turnId: 'turn-1', content: '你好', attachments: [],
  });

  const [, init] = fetcher.mock.calls[0] as [string, RequestInit];
  expect(JSON.parse(String(init.body))).toEqual({
    turnId: 'turn-1', content: '你好', attachments: [],
  });
});


it('confirms an edited proposal batch in one request', async () => {
  const result = batchResolveResult('accepted');
  const fetcher = vi.fn().mockResolvedValue(jsonResponse(result));
  const api = createTodoApi(connection, fetcher);
  const input = { items: [{
    proposalId: 'p1',
    payload: {
      text: '卡片编辑后', priority: 'high' as const, category: 'work' as const,
      time_start: null, time_end: null, notes: null,
    },
  }] };

  await expect(api.confirmAssistantProposalBatch('b1', input)).resolves.toEqual(result);
  expect(fetcher).toHaveBeenCalledWith(
    'http://localhost:8000/api/v1/assistant/proposal-batches/b1/confirm',
    expect.objectContaining({ method: 'POST', body: JSON.stringify(input) }),
  );
});


it('rejects a whole batch through the batch route', async () => {
  const result = batchResolveResult('rejected');
  const fetcher = vi.fn().mockResolvedValue(jsonResponse(result));
  const api = createTodoApi(connection, fetcher);
  await api.rejectAssistantProposalBatch('b1');
  expect(fetcher).toHaveBeenCalledWith(
    'http://localhost:8000/api/v1/assistant/proposal-batches/b1/reject',
    expect.objectContaining({ method: 'POST' }),
  );
});
```

- [ ] **Step 2: Run client tests and confirm failure**

Run:

```bash
npm --prefix frontend test -- src/shared/api/__tests__/assistant-client.test.ts
```

Expected: FAIL because the batch types/methods and `turnId` are absent.

- [ ] **Step 3: Replace the assistant proposal contracts**

Use these exact wire types in `contracts.ts`:

```typescript
export interface ProposalCardFields {
  text: string;
  priority: Priority;
  category: Category;
  time_start: string | null;
  time_end: string | null;
  notes: string | null;
}

export type ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'superseded';
export type ProposalBatchStatus =
  | 'pending' | 'partially_applied' | 'accepted' | 'rejected' | 'superseded';

export interface AssistantProposal {
  id: string;
  messageId: string;
  batchId: string;
  action: 'create' | 'update' | 'delete';
  targetTaskId: string | null;
  beforeSnapshot: Todo | null;
  payload: ProposalCardFields | null;
  resultTaskId: string | null;
  status: ProposalStatus;
  lastError: string | null;
  createdAt: number;
}

export interface AssistantProposalBatch {
  id: string;
  messageId: string;
  status: ProposalBatchStatus;
  supersedesBatchId: string | null;
  proposals: AssistantProposal[];
  createdAt: number;
  resolvedAt: number | null;
}

export interface ConfirmProposalItemInput {
  proposalId: string;
  payload: ProposalCardFields | null;
}

export interface ConfirmProposalBatchInput {
  items: ConfirmProposalItemInput[];
}

export interface ProposalApplyItemResult {
  proposal: AssistantProposal;
  task: Todo | null;
  error: string | null;
}

export interface ProposalBatchResolveResult {
  batch: AssistantProposalBatch;
  items: ProposalApplyItemResult[];
}
```

Add `turnId: string | null` to `AssistantMessage`. Change `AssistantTurn` and `AssistantConversationDetail` to `proposalBatches: AssistantProposalBatch[]`. Change `SendAssistantMessageInput` to include required `turnId: string`.

Replace `TodoApi.acceptAssistantProposal/rejectAssistantProposal` with:

```typescript
confirmAssistantProposalBatch(
  id: string,
  input: ConfirmProposalBatchInput,
): Promise<ProposalBatchResolveResult>;
rejectAssistantProposalBatch(id: string): Promise<ProposalBatchResolveResult>;
```

- [ ] **Step 4: Implement the client methods**

Replace the old methods in `createTodoApi`:

```typescript
confirmAssistantProposalBatch: (id, input) => request<ProposalBatchResolveResult>(
  `/api/v1/assistant/proposal-batches/${encodeURIComponent(id)}/confirm`,
  'POST',
  input,
),
rejectAssistantProposalBatch: id => request<ProposalBatchResolveResult>(
  `/api/v1/assistant/proposal-batches/${encodeURIComponent(id)}/reject`,
  'POST',
  {},
),
```

Keep the existing 120-second message timeout and multipart behavior.

- [ ] **Step 5: Run the client tests before changing the hook**

Run:

```bash
npm --prefix frontend test -- src/shared/api/__tests__/assistant-client.test.ts
```

Expected: client tests PASS. Do not run or commit a full build between Steps 5 and 12B: the existing hook still consumes the old contract, so contracts/client and hook are one atomic review unit.

- [ ] **Step 6: Continue directly to Task 12B**

Do not commit at this intermediate point. Continue with the hook steps below and use the single conditional commit after its full build passes.

---

#### Task 12B: Stable Turn Retry and Batch State Hook

**Files:**
- Modify: `frontend/src/features/assistant/hooks/useAssistant.ts`
- Modify: `frontend/src/features/assistant/__tests__/useAssistant.test.ts`

**Interfaces:**
- Produces: `AssistantState.proposalBatches`, `submittingBatchIds`, `retry(turnId)`, `confirmBatch`, and `rejectBatch`.
- Guarantees: normal sends create one UUID; retry after refresh reuses the failed message's `turnId` and original user message; resolved batch state comes from the server response.

- [ ] **Step 1: Write failing hook tests**

Update fixture messages/batches to the new wire types, then add:

```typescript
it('reuses the original turn id when retrying a failed message', async () => {
  const api = fakeApi();
  const failedDetail = detailWithFailedTurn('turn-retry-1');
  api.getAssistantConversation = vi.fn().mockResolvedValue(failedDetail);
  const { result } = renderHook(() => useAssistant(api, vi.fn()));
  await waitFor(() => expect(result.current.activeId).toBe('c1'));

  await act(() => result.current.retry('turn-retry-1'));

  expect(api.sendAssistantMessage).toHaveBeenCalledWith('c1', {
    turnId: 'turn-retry-1', content: '新建买菜任务', attachments: [],
  });
});


it('creates one stable turn id for a normal send', async () => {
  const uuid = vi.spyOn(globalThis.crypto, 'randomUUID')
    .mockReturnValue('00000000-0000-4000-8000-000000000001');
  const api = fakeApi();
  const { result } = renderHook(() => useAssistant(api, vi.fn()));
  await waitFor(() => expect(result.current.activeId).toBe('c1'));

  await act(() => result.current.send('新建买菜任务', []));

  expect(api.sendAssistantMessage).toHaveBeenCalledWith('c1', {
    turnId: '00000000-0000-4000-8000-000000000001',
    content: '新建买菜任务', attachments: [],
  });
  uuid.mockRestore();
});


it('confirms one batch and replaces it with the server state', async () => {
  const api = fakeApi();
  const resolved = batchResolveResult('partially_applied');
  api.confirmAssistantProposalBatch = vi.fn().mockResolvedValue(resolved);
  const { result } = renderHook(() => useAssistant(api, vi.fn()));
  await waitFor(() => expect(result.current.activeId).toBe('c1'));

  const response = await act(() => result.current.confirmBatch('b1', editedItems));

  expect(response).toEqual(resolved);
  expect(result.current.proposalBatches[0]).toEqual(resolved.batch);
  expect(result.current.submittingBatchIds.has('b1')).toBe(false);
});
```

Also test duplicate confirm clicks are ignored while the batch ID is submitting, reject replaces server state, and retry with an unknown turn ID reports `ASSISTANT_TURN_NOT_FOUND` without sending.

Add a failed-send refresh regression: `sendAssistantMessage` rejects with a 500, the subsequent detail request returns the persisted user/failed-assistant pair with the generated `turnId`, and the hook must still replace local `messages`/`proposalBatches`, report the original error, and allow `retry(turnId)` without a page reload.

- [ ] **Step 2: Run hook tests and confirm failure**

Run:

```bash
npm --prefix frontend test -- src/features/assistant/__tests__/useAssistant.test.ts
```

Expected: FAIL because the hook still stores flat proposals and retries by creating a new message.

- [ ] **Step 3: Replace flat proposal and retry state**

Change `AssistantState` to:

```typescript
export interface AssistantState {
  conversations: AssistantConversationSummary[];
  activeId: string | null;
  messages: AssistantMessage[];
  proposalBatches: AssistantProposalBatch[];
  settingsView: AssistantSettingsView | null;
  sending: boolean;
  submittingBatchIds: ReadonlySet<string>;
  selectConversation: (id: string) => Promise<void>;
  startNewConversation: () => void;
  deleteConversation: (id: string) => Promise<void>;
  send: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  retry: (turnId: string) => Promise<void>;
  confirmBatch: (
    id: string, items: ConfirmProposalItemInput[],
  ) => Promise<ProposalBatchResolveResult | undefined>;
  rejectBatch: (id: string) => Promise<ProposalBatchResolveResult | undefined>;
  saveSettings: (patch: AssistantSettingsPatch) => Promise<boolean>;
}
```

Keep `messagesRef.current = messages` and implement retry lookup:

```typescript
const retry = useCallback(async (turnId: string) => {
  const userMessage = messagesRef.current.find(message => (
    message.role === 'user' && message.turnId === turnId
  ));
  if (!userMessage || !activeId) {
    onErrorRef.current(new ApiError(
      'business', 'ASSISTANT_TURN_NOT_FOUND', 'Assistant turn not found', 404,
    ));
    return;
  }
  await dispatchMessage(
    activeId, turnId, userMessage.content, userMessage.attachments,
  );
}, [activeId, dispatchMessage]);
```

`send` calls `dispatchMessage(conversationId, crypto.randomUUID(), content, attachments)`. `dispatchMessage` never appends a speculative duplicate user message. Whether the message API resolves or rejects, it performs a best-effort conversation-detail/list refresh with `Promise.allSettled`; when detail succeeds it replaces `messages` plus `proposalBatches`, so a backend-persisted failed turn and its Retry button appear immediately after a 500/network response. After refresh it reports the original send error (not a refresh error). On success, refresh failures retain the existing safe error handling rather than fabricating local rows.

- [ ] **Step 4: Implement serialized batch submission**

Use a ref-backed set so two clicks in the same render cannot race:

```typescript
const submittingRef = useRef(new Set<string>());

const runBatchMutation = useCallback(async (
  id: string,
  operation: () => Promise<ProposalBatchResolveResult>,
): Promise<ProposalBatchResolveResult | undefined> => {
  if (submittingRef.current.has(id)) return undefined;
  submittingRef.current.add(id);
  setSubmittingBatchIds(new Set(submittingRef.current));
  try {
    const result = await operation();
    setProposalBatches(current => current.map(batch => (
      batch.id === id ? result.batch : batch
    )));
    return result;
  } catch (error) {
    onErrorRef.current(error);
    return undefined;
  } finally {
    submittingRef.current.delete(id);
    setSubmittingBatchIds(new Set(submittingRef.current));
  }
}, []);
```

`confirmBatch` calls `runBatchMutation(id, () => api.confirmAssistantProposalBatch(id, {items}))`; `rejectBatch` uses the reject API. Remove `lastSendRef`, flat `proposals`, and `resolveProposal`.

- [ ] **Step 5: Run the client/hook tests before component migration**

Run:

```bash
npm --prefix frontend test -- src/features/assistant/__tests__/useAssistant.test.ts
npm --prefix frontend test -- src/shared/api/__tests__/assistant-client.test.ts
```

Expected: the focused client/hook tests PASS. Do not run the full TypeScript build yet: `AssistantDrawer`, `MessageList`, and `ProposalCard` still consume the old hook shape until Task 13, so Tasks 12 and 13 are one atomic frontend migration slice.

- [ ] **Step 6: Continue directly to Task 13**

Do not commit the temporarily incompatible contract/hook state. Continue immediately to Task 13; its full test/build gate and one conditional commit include all Task 12 files.

---

### Task 13: Editable Batch Cards and Delete Target Cards

**Files:**
- Create: `frontend/src/features/assistant/components/ProposalFieldsEditor.tsx`
- Create: `frontend/src/features/assistant/components/ProposalBatchCard.tsx`
- Create: `frontend/src/features/assistant/components/DeleteProposalCard.tsx`
- Delete: `frontend/src/features/assistant/components/ProposalCard.tsx`
- Modify: `frontend/src/features/assistant/components/MessageList.tsx`
- Modify: `frontend/src/features/assistant/components/AssistantDrawer.tsx`
- Modify: `frontend/src/features/assistant/styles/assistant.css`
- Modify: `frontend/src/features/i18n/translations.ts`
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/features/assistant/__tests__/proposal-cards.test.tsx`
- Modify: `frontend/src/features/assistant/__tests__/assistant-components.test.tsx`
- Modify: `frontend/src/app/__tests__/App.test.tsx`
- Modify: `frontend/src/features/i18n/__tests__/translations.test.ts`

**Interfaces:**
- Consumes: Task 12B hook methods and batch state.
- Produces: one editable confirmation button for create/update batches; one read-only full-target card per delete; parent task-list updates for every successful item.
- Guarantees: accepted items lock, pending failures stay editable, superseded cards cannot submit, and confirmation does not send a chat message.

- [ ] **Step 1: Write failing card tests**

Create `proposal-cards.test.tsx`:

```typescript
it('edits two proposals and confirms the batch once', async () => {
  const onConfirm = vi.fn().mockResolvedValue(undefined);
  renderCard(editableBatchWithTwoItems(), { onConfirm });

  fireEvent.change(screen.getAllByLabelText('任务标题')[0], {
    target: { value: '修改后的第一项' },
  });
  fireEvent.click(screen.getByRole('button', { name: '确认全部 2 项' }));

  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onConfirm).toHaveBeenCalledWith('b1', expect.arrayContaining([
    expect.objectContaining({
      proposalId: 'p1', payload: expect.objectContaining({ text: '修改后的第一项' }),
    }),
    expect.objectContaining({ proposalId: 'p2' }),
  ]));
});


it('shows update target and before-after values', () => {
  renderCard(updateBatch(), defaults);
  expect(screen.getByText('目标：团队会议')).toBeTruthy();
  expect(screen.getByText('2026-07-22 15:00')).toBeTruthy();
  expect(screen.getByText('2026-07-22 17:00')).toBeTruthy();
});


it('locks accepted items and resubmits only pending failures', () => {
  const onConfirm = vi.fn();
  renderCard(partiallyAppliedBatch(), { onConfirm });
  expect(screen.getByDisplayValue('已创建')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '重新确认剩余 1 项' }));
  expect(onConfirm).toHaveBeenCalledWith('b1', [
    expect.objectContaining({ proposalId: 'p-failed' }),
  ]);
});


it('renders a delete target read-only with its full details', () => {
  renderDeleteCard(deleteBatch(), defaults);
  expect(screen.getByText('删除任务：季度复盘')).toBeTruthy();
  expect(screen.getByText('工作')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
});


it('disables confirmation for superseded batches', () => {
  renderCard(supersededBatch(), defaults);
  expect(screen.queryByRole('button', { name: /确认/ })).toBeNull();
  expect(screen.getByText('已被新提议取代')).toBeTruthy();
});


it('renders a legacy delete without a snapshot as read-only history', () => {
  renderDeleteCard(legacyDeleteBatch({ beforeSnapshot: null, payload: null }), defaults);
  expect(screen.getByText('任务详情不可用')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /确认删除/ })).toBeNull();
});


it('does not offer retry when a terminal partial batch has no pending items', () => {
  renderCard(acceptedAndRejectedBatch(), defaults);
  expect(screen.queryByRole('button', { name: /剩余 0/ })).toBeNull();
});
```

Also test blank title disables confirmation, invalid time range shows a local error, submitting disables buttons, notes are editable, delete has its own confirm/reject buttons, and no callback named `send` is invoked by confirmation.

- [ ] **Step 2: Run component tests and confirm failure**

Run:

```bash
npm --prefix frontend test -- src/features/assistant/__tests__/proposal-cards.test.tsx src/features/assistant/__tests__/assistant-components.test.tsx
```

Expected: FAIL because the three new components do not exist and the UI still renders one flat card per proposal.

- [ ] **Step 3: Implement the controlled fields editor**

Create `ProposalFieldsEditor.tsx` with this interface and value normalization:

```typescript
interface ProposalFieldsEditorProps {
  value: ProposalCardFields;
  disabled: boolean;
  onChange: (value: ProposalCardFields) => void;
}

function valueOrNull(value: string): string | null {
  return value === '' ? null : value;
}

function ProposalFieldsEditor({ value, disabled, onChange }: ProposalFieldsEditorProps) {
  const { t } = useI18n();
  return (
    <fieldset className="assistant-proposal-fields" disabled={disabled}>
      <label>
        {t('assistant.taskTitle')}
        <input aria-label={t('assistant.taskTitle')} value={value.text ?? ''}
          onChange={event => onChange({ ...value, text: event.target.value })} />
      </label>
      <label>
        {t('create.priority')}
        <select value={value.priority ?? 'medium'}
          onChange={event => onChange({ ...value, priority: event.target.value as Priority })}>
          <option value="low">{t('priority.low')}</option>
          <option value="medium">{t('priority.medium')}</option>
          <option value="high">{t('priority.high')}</option>
        </select>
      </label>
      <label>
        {t('create.category')}
        <select value={value.category ?? 'other'}
          onChange={event => onChange({ ...value, category: event.target.value as Category })}>
          <option value="work">{t('category.work')}</option>
          <option value="study">{t('category.study')}</option>
          <option value="life">{t('category.life')}</option>
          <option value="other">{t('category.other')}</option>
        </select>
      </label>
      <label>{t('time.start')}<input type="datetime-local" value={value.time_start ?? ''}
        onChange={event => onChange({ ...value, time_start: valueOrNull(event.target.value) })} /></label>
      <label>{t('time.end')}<input type="datetime-local" value={value.time_end ?? ''}
        onChange={event => onChange({ ...value, time_end: valueOrNull(event.target.value) })} /></label>
      <label>{t('detail.notes')}<textarea value={value.notes ?? ''}
        onChange={event => onChange({ ...value, notes: valueOrNull(event.target.value) })} /></label>
    </fieldset>
  );
}
```

Import `Priority` and `Category` from shared types. Native inputs are sufficient; do not introduce a second date-picker implementation.

- [ ] **Step 4: Implement batch and delete cards**

`ProposalBatchCard` owns `Record<proposalId, ProposalCardFields>` initialized only from non-null batch payloads and re-synchronized when server status changes. A create/update row with a null legacy payload is rendered as unavailable read-only history and cannot submit. It renders editors only for pending create/update proposals with payloads, shows update target/diff from `beforeSnapshot`, and submits only pending items:

```typescript
const pending = batch.proposals.filter(proposal => (
  proposal.status === 'pending' && proposal.payload !== null
));
const invalid = pending.some(proposal => {
  const fields = drafts[proposal.id];
  return !fields?.text?.trim()
    || Boolean(fields.time_end && !fields.time_start)
    || Boolean(fields.time_start && fields.time_end && fields.time_end < fields.time_start);
});

const confirm = () => onConfirm(batch.id, pending.map(proposal => ({
  proposalId: proposal.id,
  payload: drafts[proposal.id],
})));
```

Render a confirm/retry button only when the actionable `pending.length > 0`. A pending legacy row with null payload may still be rejected but cannot be confirmed. Use `assistant.confirmBatch` with count for a new/pending batch and `assistant.retryRemaining` for a genuinely partial batch with pending items; an accepted+rejected terminal batch may retain status `partially_applied` but has no action. Render `lastError` under only the affected item. Render superseded content inside `<details>` without actions.

`DeleteProposalCard` requires a one-item delete batch. When `beforeSnapshot` exists it renders `text/time/category/priority/notes/completed`; when it is null it renders `assistant.targetUnavailable`, never dereferences fields, disables confirm, and leaves reject available only while the row is pending. It calls confirm with `[{proposalId, payload: null}]` only for a current pending batch with a snapshot. Accepted/rejected/superseded delete cards have no actions (superseded is folded history). It never accepts a replacement target ID or editable payload.

- [ ] **Step 5: Wire cards into messages and application state**

Change `MessageList` props to accept `proposalBatches`, `submittingBatchIds`, `onRetry(turnId)`, `onConfirmBatch`, and `onRejectBatch`. Group with `batch.messageId === message.id`; render `DeleteProposalCard` when its only proposal is delete, otherwise `ProposalBatchCard`. The failed message Retry button calls `onRetry(message.turnId)` only when `turnId` is non-null.

Remove `proposalOverrides` from `AssistantDrawer`. Pass hook state directly and notify the parent for every accepted item returned by confirmation:

```typescript
const result = await assistant.confirmBatch(id, items);
for (const item of result?.items ?? []) {
  if (item.proposal.status === 'accepted') onApplyProposal(item);
}
```

Update `App.tsx` to accept `ProposalApplyItemResult`:

```typescript
const handleApplyProposal = useCallback((result: ProposalApplyItemResult) => {
  if (result.proposal.action === 'delete') {
    if (result.proposal.targetTaskId) {
      todoState.removeExternalTask(result.proposal.targetTaskId);
    }
  } else if (result.task) {
    todoState.upsertExternalTask(result.task);
  }
}, [todoState]);
```

This callback updates the existing task list only; it does not create an assistant chat message.

- [ ] **Step 6: Add translations and styles**

Add matching Chinese/English keys and include them in the assistant-copy translation test:

```text
assistant.taskTitle              任务标题 / Task title
assistant.target                目标：{task} / Target: {task}
assistant.before                修改前 / Before
assistant.after                 修改后 / After
assistant.confirmBatch          确认全部 {count} 项 / Confirm all {count}
assistant.retryRemaining        重新确认剩余 {count} 项 / Retry remaining {count}
assistant.partiallyApplied      部分成功 / Partially applied
assistant.superseded            已被新提议取代 / Replaced by a newer proposal
assistant.deleteTarget          删除任务：{task} / Delete task: {task}
assistant.targetUnavailable     任务详情不可用 / Task details unavailable
assistant.validationTitle       任务标题不能为空 / Task title is required
assistant.validationTime        结束时间必须晚于开始时间 / End time must be after start time
assistant.proposalError         此项未执行：{error} / Not applied: {error}
errors.taskChangedSinceProposal 任务已在其他位置发生变化，请重新生成提议。 / The task changed elsewhere. Generate a new proposal.
errors.invalidConfirmation      确认内容无效，请检查后重试。 / The confirmation content is invalid.
errors.resultVerification       写入结果未通过验证，请重试。 / The saved result could not be verified.
errors.proposalBatchState       该确认批次当前不可执行。 / This confirmation batch cannot be applied.
errors.assistantTurnActive      此会话仍有一条消息正在处理。 / Another message is still running in this chat.
```

Map `TASK_CHANGED_SINCE_PROPOSAL`, `INVALID_CONFIRMATION_PAYLOAD`, `RESULT_VERIFICATION_FAILED`, `PROPOSAL_BATCH_NOT_CONFIRMABLE`, and `ASSISTANT_TURN_ACTIVE` through the existing `translationForError` mechanism. Cards call `errorText(proposal.lastError)` before interpolating `assistant.proposalError`; never display a raw backend code as the only explanation.

Extend `assistant.css` with existing theme tokens only. Add `.assistant-proposal-batch`, `.assistant-proposal-item`, `.assistant-proposal-diff`, `.assistant-proposal-fields`, pending/error/accepted/superseded modifiers, responsive two-column fields above 340px and one column below. Preserve visible keyboard focus and disabled states.

- [ ] **Step 7: Delete old card and run UI tests/build**

After `rg -n "ProposalCard" frontend/src` shows only the obsolete file/import, delete `frontend/src/features/assistant/components/ProposalCard.tsx` with `apply_patch` (`*** Delete File`) and update imports. Then run:

```bash
npm --prefix frontend test -- src/features/assistant/__tests__/proposal-cards.test.tsx src/features/assistant/__tests__/assistant-components.test.tsx src/features/assistant/__tests__/useAssistant.test.ts src/features/i18n/__tests__/translations.test.ts src/app/__tests__/App.test.tsx
npm --prefix frontend run build
```

Expected: all selected tests PASS and the production build exits 0.

- [ ] **Step 8: Conditional commit checkpoint**

Only after explicit user authorization:

```bash
git add frontend/src/features/assistant frontend/src/features/i18n/translations.ts frontend/src/features/i18n/__tests__/translations.test.ts frontend/src/app/App.tsx frontend/src/app/__tests__/App.test.tsx
git add frontend/src/shared/api/contracts.ts frontend/src/shared/api/client.ts frontend/src/shared/api/__tests__/assistant-client.test.ts
git commit -m "feat(agent): add editable batch confirmation cards"
```

---

### Task 14: Packaging, Documentation, and Full Verification

**Files:**
- Modify: `backend/todo-backend.spec`
- Modify: `backend/tests/test_packaging_smoke.py`
- Modify: `README.md`
- Modify: `docs/project-overview.md`
- Modify: `docs/backend/api.md`
- Modify: `docs/backend/database.md`
- Modify: `docs/CLAUDE.md`

**Interfaces:**
- Produces: a packaged sidecar containing LangGraph/checkpoint modules and migration 005.
- Produces: current architecture/API/database documentation and links to this spec/plan.
- Verifies: backend, frontend, migration, graph restart, duplicate retry, direct confirmation, and packaging behavior.

- [ ] **Step 1: Update packaging coverage before the spec file**

Change `test_packaging_smoke.py` assertions:

```python
graph_database_path = tmp_path / "assistant_graph.sqlite3"
assert database_path.is_file()
assert graph_database_path.is_file()

# after reading todo.sqlite3
assert user_version == 5
assert {"tasks", "assistant_turns", "assistant_proposal_batches"} <= tables
```

Run the normal test without a binary:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_packaging_smoke.py -v
```

Expected: one SKIP with the existing reason `TODO_BACKEND_BINARY is not set`; test collection itself succeeds.

- [ ] **Step 2: Include LangGraph's dynamically loaded modules**

Update `backend/todo-backend.spec`:

```python
from PyInstaller.utils.hooks import collect_submodules

langgraph_hiddenimports = (
    collect_submodules("langgraph")
    + collect_submodules("langgraph.checkpoint.sqlite")
)

analysis = Analysis(
    ["src/todo_backend/sidecar.py"],
    pathex=["src"],
    binaries=[],
    datas=[("migrations", "migrations")],
    hiddenimports=langgraph_hiddenimports,
    # keep the remaining existing Analysis options unchanged
)
```

Do not change the executable name, target architecture, migrations bundle path, signing flow, or application version.

- [ ] **Step 3: Update exact API/database/architecture documentation**

Make these factual replacements:

- `README.md`: describe an editable batch confirmation card with direct backend application; do not describe the old tool loop.
- `docs/project-overview.md`: replace “后端 agent 循环执行工具调用” with the two LangGraph workflows and separate checkpoint SQLite file.
- `docs/backend/api.md`: document message `turnId`, `proposalBatches`, batch confirm/reject request/response, partial success, stable error codes, and legacy single-item routes.
- `docs/backend/database.md`: document migration 005, `assistant_turns`, `assistant_proposal_batches`, extended proposals, `assistant_graph.sqlite3`, status transitions, and exact cleanup ownership.
- `docs/CLAUDE.md`: link `2026-07-22-langgraph-agent-redesign-design.md` and `2026-07-22-langgraph-agent-redesign.md` as the current design/plan; label the 2026-07-20 documents as the original implementation baseline.

Use this API example in `docs/backend/api.md`:

```json
POST /api/v1/assistant/proposal-batches/b1/confirm
{
  "items": [
    {
      "proposalId": "p1",
      "payload": {
        "text": "团队会议",
        "priority": "high",
        "category": "work",
        "time_start": "2026-07-22T16:00",
        "time_end": "2026-07-22T17:00",
        "notes": null
      }
    }
  ]
}
```

- [ ] **Step 4: Run the full automated verification in Python 3.12**

Run from the repository root:

```bash
uv sync --directory backend --python .venv/bin/python --group dev
backend/.venv/bin/python --version
backend/.venv/bin/python -m pytest backend/tests -v
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
while IFS= read -r file; do
  output=$(git diff --no-index --check -- /dev/null "$file" 2>&1 || true)
  if [ -n "$output" ]; then
    print -r -- "$output"
    exit 1
  fi
done < <(git ls-files --others --exclude-standard)
```

Expected:

- Python reports `3.12.x`.
- Backend has zero failed tests; only the packaging smoke test may skip when no packaged binary is supplied.
- Ruff exits 0.
- Pyright reports 0 errors.
- All Vitest suites pass.
- TypeScript/Vite build exits 0.
- Tracked and untracked whitespace checks print nothing and exit 0.

- [ ] **Step 5: Build and smoke-test the sidecar on the supported macOS arm64 build host**

Run only on the repository's supported macOS arm64 packaging host:

```bash
cd backend
.venv/bin/pyinstaller --noconfirm --clean todo-backend.spec
TODO_BACKEND_BINARY="$PWD/dist/todo-backend" .venv/bin/python -m pytest tests/test_packaging_smoke.py -v
```

Expected: PyInstaller exits 0; packaging smoke PASS; the sidecar creates schema version 5 and `assistant_graph.sqlite3` and responds to health checks. Do not replace the checked-in Tauri sidecar binary or sign an application bundle without separate explicit user authorization.

- [ ] **Step 6: Run manual Ark acceptance only with explicit credentials**

Do not put the key in a command, plan, or log. Configure it through the existing settings UI, then manually verify:

1. “新建一个明天下午四点的会议” produces a create card even when a same-title task exists.
2. “把会议改到四点” shows the chosen target and before/after values.
3. “把刚才那个改成五点” supersedes the old pending card.
4. Editing two create/update items and confirming once writes both without a chat reply.
5. One invalid item yields partial success and only that item is offered again.
6. Repeated confirm does not duplicate tasks.
7. Restarting the backend preserves and resumes an unconfirmed card.
8. A model that rejects extended thinking falls back once and still produces a verified plan.
9. Confirmation creates no Ark network call.

Record pass/fail evidence without message/task bodies or credentials.

- [ ] **Step 7: Review final scope and diff**

Run:

```bash
git status --short
git diff --stat
git diff -- backend/pyproject.toml backend/src backend/tests frontend/src docs README.md
```

Expected: only files listed in this plan plus the approved design/plan documents changed; no key, uploaded attachment, generated database, `.venv`, `dist`, or unrelated formatting is tracked.

- [ ] **Step 8: Conditional final commit**

Only after explicit user authorization and after all applicable checks above pass:

```bash
git add backend/todo-backend.spec backend/tests/test_packaging_smoke.py README.md docs/project-overview.md docs/backend/api.md docs/backend/database.md docs/CLAUDE.md docs/superpowers/specs/2026-07-22-langgraph-agent-redesign-design.md docs/superpowers/plans/2026-07-22-langgraph-agent-redesign.md
git commit -m "docs(agent): document LangGraph confirmation workflow"
```

If earlier conditional commits were not authorized, do not use this documentation-only command to commit implementation files; ask the user whether they want one final implementation commit, multiple task commits, or no commit.
