from todo_backend.database import Database
from todo_backend.models import BootstrapResponse, ThemeId
from todo_backend.repositories.achievements import AchievementRepository
from todo_backend.repositories.settings import SettingsRepository
from todo_backend.repositories.tasks import TaskRepository


class BootstrapService:
    def __init__(
        self,
        database: Database,
        task_repository: TaskRepository | None = None,
        settings_repository: SettingsRepository | None = None,
        achievement_repository: AchievementRepository | None = None,
    ) -> None:
        self.database = database
        self.task_repository = task_repository or TaskRepository()
        self.settings_repository = settings_repository or SettingsRepository()
        self.achievement_repository = achievement_repository or AchievementRepository()

    def bootstrap(self, preferred_theme: ThemeId) -> BootstrapResponse:
        with self.database.transaction() as connection:
            settings = self.settings_repository.initialize(connection, preferred_theme)
            self.achievement_repository.ensure_state(connection)
            return BootstrapResponse(
                tasks=self.task_repository.list_all(connection),
                settings=settings,
                achievementState=self.achievement_repository.load_state(connection),
            )
