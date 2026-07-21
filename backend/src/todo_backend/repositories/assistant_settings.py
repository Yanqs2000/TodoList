import sqlite3

from todo_backend.models import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_AUDIO_MODEL,
    DEFAULT_CHAT_MODEL,
    AssistantSettings,
    AssistantSettingsPatchCommand,
)

__all__ = [
    "DEFAULT_ARK_BASE_URL",
    "DEFAULT_AUDIO_MODEL",
    "DEFAULT_CHAT_MODEL",
    "AssistantSettingsRepository",
]


class AssistantSettingsRepository:
    def get(self, connection: sqlite3.Connection) -> AssistantSettings:
        row = connection.execute(
            "SELECT assistant_api_key, assistant_chat_model, assistant_audio_model,"
            " assistant_base_url FROM app_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Application settings are not initialized")
        return AssistantSettings(
            api_key=row["assistant_api_key"],
            chat_model=row["assistant_chat_model"],
            audio_model=row["assistant_audio_model"],
            base_url=row["assistant_base_url"],
        )

    def patch(
        self,
        connection: sqlite3.Connection,
        command: AssistantSettingsPatchCommand,
    ) -> AssistantSettings:
        column_by_field = {
            "api_key": "assistant_api_key",
            "chat_model": "assistant_chat_model",
            "audio_model": "assistant_audio_model",
            "base_url": "assistant_base_url",
        }
        assignments: list[str] = []
        values: list[object] = []
        for field_name in command.model_fields_set:
            assignments.append(f"{column_by_field[field_name]} = ?")
            values.append(getattr(command, field_name))
        connection.execute(
            f"UPDATE app_settings SET {', '.join(assignments)} WHERE id = 1",
            values,
        )
        return self.get(connection)
