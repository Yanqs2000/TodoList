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
