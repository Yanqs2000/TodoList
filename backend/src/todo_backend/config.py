import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    host: str
    port: int
    token: str
    allow_vite_dev_origin: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        database_path = _required_environment_value("TODO_DATABASE_PATH")
        port = _required_environment_value("TODO_BACKEND_PORT")
        token = _required_environment_value("TODO_BACKEND_TOKEN")
        try:
            parsed_port = int(port)
        except ValueError as error:
            raise ConfigurationError("TODO_BACKEND_PORT must be an integer") from error
        return cls(
            Path(database_path),
            "127.0.0.1",
            parsed_port,
            token,
            allow_vite_dev_origin=os.environ.get("TODO_BACKEND_ALLOW_VITE_ORIGIN") == "1",
        )


def _required_environment_value(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {key}")
    return value
