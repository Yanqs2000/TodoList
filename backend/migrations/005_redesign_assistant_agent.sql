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
