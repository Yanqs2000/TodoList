import sqlite3
from datetime import date, timedelta

from todo_backend.models import AchievementState
from todo_backend.repositories.achievements import AchievementRepository


class AchievementService:
    def __init__(self, repository: AchievementRepository | None = None) -> None:
        self.repository = repository or AchievementRepository()

    def apply_completion(
        self,
        connection: sqlite3.Connection,
        local_date: str,
        records_progress: bool,
    ) -> tuple[AchievementState, list[str]]:
        state = self.repository.load_state(connection)
        newly_unlocked: list[str] = []

        if records_progress:
            same_day = state.today_date == local_date
            today_completed = state.today_completed + 1 if same_day else 1
            streak_days = state.streak_days
            yesterday = (date.fromisoformat(local_date) - timedelta(days=1)).isoformat()
            if not same_day or state.last_active_date != local_date:
                streak_days = state.streak_days + 1 if state.last_active_date == yesterday else 1

            unlocked = list(state.unlocked)
            for achievement_id, condition in (
                ("first-task", today_completed >= 1),
                ("speed-demon", today_completed >= 10),
                ("streak-7", streak_days >= 7),
            ):
                if condition and achievement_id not in unlocked:
                    unlocked.append(achievement_id)
                    newly_unlocked.append(achievement_id)

            state = AchievementState(
                unlocked=unlocked,
                streakDays=streak_days,
                lastActiveDate=local_date,
                todayCompleted=today_completed,
                todayDate=local_date,
            )

        self.repository.save_state(connection, state)
        self.repository.add_unlocks(connection, newly_unlocked)
        return state, newly_unlocked
