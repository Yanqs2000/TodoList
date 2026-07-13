from todo_backend.database import Database
from todo_backend.models import AppSettings, SettingsPatchCommand
from todo_backend.repositories.settings import SettingsRepository


class SettingsService:
    def __init__(
        self,
        database: Database,
        repository: SettingsRepository | None = None,
    ) -> None:
        self.database = database
        self.repository = repository or SettingsRepository()

    def patch(self, command: SettingsPatchCommand) -> AppSettings:
        with self.database.transaction() as connection:
            return self.repository.patch(connection, command)
