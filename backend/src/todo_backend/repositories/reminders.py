import sqlite3
import time


class ReminderRepository:
    def claim(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        scheduled_start: str,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO task_reminders (task_id, scheduled_start, claimed_at)
            SELECT id, ?, ?
            FROM tasks
            WHERE id = ?
              AND completed = 0
              AND time_start = ?
            """,
            (
                scheduled_start,
                time.time_ns() // 1_000_000,
                task_id,
                scheduled_start,
            ),
        )
        return cursor.rowcount == 1

    def prune_stale(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        current_start: str | None,
    ) -> None:
        if current_start is None:
            connection.execute("DELETE FROM task_reminders WHERE task_id = ?", (task_id,))
            return
        connection.execute(
            """
            DELETE FROM task_reminders
            WHERE task_id = ? AND scheduled_start != ?
            """,
            (task_id, current_start),
        )
