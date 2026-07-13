from todo_backend.database import Database
from todo_backend.models import (
    CompletionCommand,
    CompletionResponse,
    CreateTaskCommand,
    Task,
    UpdateTaskCommand,
)
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.achievements import AchievementService


class TaskService:
    def __init__(
        self,
        database: Database,
        repository: TaskRepository | None = None,
        achievement_service: AchievementService | None = None,
    ) -> None:
        self.database = database
        self.repository = repository or TaskRepository()
        self.achievement_service = achievement_service or AchievementService()

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

    def set_completion(
        self,
        task_id: str,
        command: CompletionCommand,
    ) -> CompletionResponse:
        with self.database.transaction() as connection:
            task, records_progress = self.repository.set_completion(
                connection,
                task_id,
                command.completed,
            )
            achievement_state, newly_unlocked = self.achievement_service.apply_completion(
                connection,
                command.local_date,
                records_progress,
            )
            return CompletionResponse(
                task=task,
                achievementState=achievement_state,
                newlyUnlocked=newly_unlocked,
            )

    def replace_order(self, task_ids: list[str]) -> list[Task]:
        with self.database.transaction() as connection:
            return self.repository.replace_order(connection, task_ids)
