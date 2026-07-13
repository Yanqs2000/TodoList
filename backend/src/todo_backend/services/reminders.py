from todo_backend.database import Database
from todo_backend.models import ReminderClaimCommand, ReminderClaimResponse
from todo_backend.repositories.reminders import ReminderRepository


class ReminderService:
    def __init__(
        self,
        database: Database,
        repository: ReminderRepository | None = None,
    ) -> None:
        self.database = database
        self.repository = repository or ReminderRepository()

    def claim(self, command: ReminderClaimCommand) -> ReminderClaimResponse:
        with self.database.transaction() as connection:
            claimed = self.repository.claim(
                connection,
                command.task_id,
                command.scheduled_start,
            )
        return ReminderClaimResponse(claimed=claimed)
