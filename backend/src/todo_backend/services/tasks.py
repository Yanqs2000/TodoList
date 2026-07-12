from todo_backend.database import Database
from todo_backend.models import CreateTaskCommand, Task, UpdateTaskCommand
from todo_backend.repositories.tasks import TaskRepository


class TaskService:
    def __init__(self, database: Database, repository: TaskRepository | None = None) -> None:
        self.database = database
        self.repository = repository or TaskRepository()

    def list_all(self) -> list[Task]:
        connection = self.database.connect()
        try:
            return self.repository.list_all(connection)
        finally:
            connection.close()

    def create(self, command: CreateTaskCommand) -> Task:
        with self.database.transaction() as connection:
            return self.repository.create(connection, command)

    def update(self, task_id: str, command: UpdateTaskCommand) -> Task:
        with self.database.transaction() as connection:
            return self.repository.update(connection, task_id, command)

    def delete(self, task_id: str) -> None:
        with self.database.transaction() as connection:
            self.repository.delete(connection, task_id)

    def replace_order(self, task_ids: list[str]) -> list[Task]:
        with self.database.transaction() as connection:
            return self.repository.replace_order(connection, task_ids)
