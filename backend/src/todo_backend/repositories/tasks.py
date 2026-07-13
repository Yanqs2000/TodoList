import sqlite3
import time
import uuid

from todo_backend.models import CreateTaskCommand, Task, TimeField, UpdateTaskCommand


class TaskNotFoundError(LookupError):
    pass


class InvalidTaskOrderError(ValueError):
    pass


class TaskRepository:
    def list_all(self, connection: sqlite3.Connection) -> list[Task]:
        rows = connection.execute(
            """
            SELECT id, text, completed, priority, created_at,
                   time_start, time_end, category, notes
            FROM tasks
            ORDER BY position ASC
            """
        ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def create(
        self,
        connection: sqlite3.Connection,
        command: CreateTaskCommand,
    ) -> Task:
        task_id = uuid.uuid4().hex
        created_at = time.time_ns() // 1_000_000
        connection.execute("UPDATE tasks SET position = position + 1")
        connection.execute(
            """
            INSERT INTO tasks (
                id, text, completed, priority, created_at,
                time_start, time_end, category, notes, position
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                task_id,
                command.text,
                command.priority,
                created_at,
                command.time.start if command.time else None,
                command.time.end if command.time else None,
                command.category,
                command.notes,
            ),
        )
        return self._get(connection, task_id)

    def update(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        command: UpdateTaskCommand,
    ) -> Task:
        if not self._exists(connection, task_id):
            raise TaskNotFoundError

        assignments: list[str] = []
        values: list[object] = []
        for field_name in command.model_fields_set:
            if field_name == "time":
                assignments.extend(("time_start = ?", "time_end = ?"))
                values.extend(
                    (
                        command.time.start if command.time else None,
                        command.time.end if command.time else None,
                    )
                )
            else:
                assignments.append(f"{field_name} = ?")
                values.append(getattr(command, field_name))

        if assignments:
            values.append(task_id)
            connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        return self._get(connection, task_id)

    def delete(self, connection: sqlite3.Connection, task_id: str) -> None:
        row = connection.execute(
            "SELECT position FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise TaskNotFoundError
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        connection.execute(
            "UPDATE tasks SET position = position - 1 WHERE position > ?",
            (row["position"],),
        )

    def set_completion(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        completed: bool,
    ) -> tuple[Task, bool]:
        task = self._get(connection, task_id)
        records_progress = not task.completed and completed
        if task.completed != completed:
            connection.execute(
                "UPDATE tasks SET completed = ? WHERE id = ?",
                (completed, task_id),
            )
            task = self._get(connection, task_id)
        return task, records_progress

    def replace_order(
        self,
        connection: sqlite3.Connection,
        task_ids: list[str],
    ) -> list[Task]:
        stored_ids = [
            row["id"]
            for row in connection.execute("SELECT id FROM tasks ORDER BY position ASC")
        ]
        if len(task_ids) != len(stored_ids) or len(set(task_ids)) != len(task_ids):
            raise InvalidTaskOrderError
        if set(task_ids) != set(stored_ids):
            raise InvalidTaskOrderError

        connection.executemany(
            "UPDATE tasks SET position = ? WHERE id = ?",
            ((position, task_id) for position, task_id in enumerate(task_ids)),
        )
        return self.list_all(connection)

    def _get(self, connection: sqlite3.Connection, task_id: str) -> Task:
        row = connection.execute(
            """
            SELECT id, text, completed, priority, created_at,
                   time_start, time_end, category, notes
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise TaskNotFoundError
        return self._task_from_row(row)

    def _exists(self, connection: sqlite3.Connection, task_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone() is not None

    def _task_from_row(self, row: sqlite3.Row) -> Task:
        task_time = None
        if row["time_start"] is not None:
            task_time = TimeField(start=row["time_start"], end=row["time_end"])
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
