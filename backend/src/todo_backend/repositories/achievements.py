import sqlite3

from todo_backend.models import AchievementState


class AchievementRepository:
    def ensure_state(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO achievement_state (
                id, streak_days, last_active_date, today_completed, today_date
            ) VALUES (1, 0, '', 0, '')
            """
        )

    def load_state(self, connection: sqlite3.Connection) -> AchievementState:
        row = connection.execute(
            """
            SELECT streak_days, last_active_date, today_completed, today_date
            FROM achievement_state
            WHERE id = 1
            """
        ).fetchone()
        unlocked = [
            unlock["achievement_id"]
            for unlock in connection.execute(
                "SELECT achievement_id FROM achievement_unlocks ORDER BY rowid"
            )
        ]
        if row is None:
            return AchievementState(
                unlocked=unlocked,
                streakDays=0,
                lastActiveDate="",
                todayCompleted=0,
                todayDate="",
            )
        return AchievementState(
            unlocked=unlocked,
            streakDays=row["streak_days"],
            lastActiveDate=row["last_active_date"],
            todayCompleted=row["today_completed"],
            todayDate=row["today_date"],
        )

    def save_state(
        self,
        connection: sqlite3.Connection,
        state: AchievementState,
    ) -> None:
        connection.execute(
            """
            INSERT INTO achievement_state (
                id, streak_days, last_active_date, today_completed, today_date
            ) VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                streak_days = excluded.streak_days,
                last_active_date = excluded.last_active_date,
                today_completed = excluded.today_completed,
                today_date = excluded.today_date
            """,
            (
                state.streak_days,
                state.last_active_date,
                state.today_completed,
                state.today_date,
            ),
        )

    def add_unlocks(
        self,
        connection: sqlite3.Connection,
        achievement_ids: list[str],
    ) -> None:
        connection.executemany(
            "INSERT INTO achievement_unlocks (achievement_id) VALUES (?)",
            ((achievement_id,) for achievement_id in achievement_ids),
        )
