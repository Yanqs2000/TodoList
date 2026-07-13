import sqlite3

from todo_backend.models import AppSettings, SettingsPatchCommand, ThemeId


class SettingsRepository:
    def initialize(self, connection: sqlite3.Connection, preferred_theme: ThemeId) -> AppSettings:
        connection.execute(
            """
            INSERT OR IGNORE INTO app_settings (id, theme, muted, shortcut)
            VALUES (1, ?, 0, 'Cmd+Alt+KeyT')
            """,
            (preferred_theme,),
        )
        return self.get(connection)

    def get(self, connection: sqlite3.Connection) -> AppSettings:
        row = connection.execute(
            "SELECT theme, muted, shortcut FROM app_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Application settings are not initialized")
        return AppSettings(
            theme=row["theme"],
            muted=bool(row["muted"]),
            shortcut=row["shortcut"],
        )

    def patch(
        self,
        connection: sqlite3.Connection,
        command: SettingsPatchCommand,
    ) -> AppSettings:
        assignments: list[str] = []
        values: list[object] = []
        for field_name in command.model_fields_set:
            assignments.append(f"{field_name} = ?")
            values.append(getattr(command, field_name))
        connection.execute(
            f"UPDATE app_settings SET {', '.join(assignments)} WHERE id = 1",
            values,
        )
        return self.get(connection)
