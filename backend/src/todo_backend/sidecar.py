import fcntl
import os
import signal
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, TextIO

import uvicorn

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


def _migrations_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle_root, str):
        return Path(bundle_root) / "migrations"
    return Path(__file__).parents[2] / "migrations"


@contextmanager
def _claim_database(database_path: Path) -> Generator[None, None, None]:
    lock_path = database_path.with_name(f".{database_path.name}.backend.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file: TextIO = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another todo backend already owns this database") from error
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{os.getpid()}\n")
        lock_file.flush()
        yield
    finally:
        lock_file.close()


def _watch_parent_stdin() -> None:
    while sys.stdin.read(1):
        pass
    os.kill(os.getpid(), signal.SIGTERM)


def main() -> None:
    settings = Settings.from_env()
    with _claim_database(settings.database_path):
        if settings.watch_parent_stdin:
            threading.Thread(
                target=_watch_parent_stdin,
                name="todo-parent-stdin-watchdog",
                daemon=True,
            ).start()
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
