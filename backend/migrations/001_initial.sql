CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
    created_at INTEGER NOT NULL,
    time_start TEXT,
    time_end TEXT,
    category TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN ('work', 'study', 'life', 'other')),
    notes TEXT,
    position INTEGER NOT NULL
);

CREATE INDEX idx_tasks_position ON tasks (position);

CREATE TABLE achievement_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT NOT NULL DEFAULT '',
    today_completed INTEGER NOT NULL DEFAULT 0,
    today_date TEXT NOT NULL DEFAULT ''
);

CREATE TABLE achievement_unlocks (
    achievement_id TEXT PRIMARY KEY
);

CREATE TABLE task_reminders (
    task_id TEXT NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    scheduled_start TEXT NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (task_id, scheduled_start)
);

CREATE TABLE app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    theme TEXT NOT NULL,
    muted INTEGER NOT NULL CHECK (muted IN (0, 1)),
    shortcut TEXT NOT NULL
);
