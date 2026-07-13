import sys
from pathlib import Path

import uvicorn

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


def _migrations_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle_root, str):
        return Path(bundle_root) / "migrations"
    return Path(__file__).parents[2] / "migrations"


def main() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_path, _migrations_dir())
    app = create_app(settings, database)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
