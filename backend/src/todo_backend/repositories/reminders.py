import sqlite3
import time

from todo_backend.repositories.tasks import TaskNotFoundError


class ReminderRepository:
    def claim(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        scheduled_start: str,
    ) -> bool:
        task_exists = connection.execute(
            "SELECT 1 FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if task_exists is None:
            raise TaskNotFoundError
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO task_reminders (task_id, scheduled_start, claimed_at)
            VALUES (?, ?, ?)
            """,
            (task_id, scheduled_start, time.time_ns() // 1_000_000),
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
