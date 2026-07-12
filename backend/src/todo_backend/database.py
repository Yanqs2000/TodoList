import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .errors import DatabaseVersionError

_MIGRATION_PATTERN = re.compile(r"^(\d+)_.*\.sql$")


class Database:
    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self.path = path
        self.migrations_dir = migrations_dir

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        migrations = self._migrations()
        latest_version = migrations[-1][0] if migrations else 0

        connection = self.connect()
        try:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

        if current_version > latest_version:
            raise DatabaseVersionError(
                f"Database version {current_version} is newer than supported version {latest_version}"
            )

        for version, migration_path in migrations:
            if version > current_version:
                self._apply_migration(version, migration_path)

    def _migrations(self) -> list[tuple[int, Path]]:
        migrations: list[tuple[int, Path]] = []
        for path in self.migrations_dir.glob("*.sql"):
            match = _MIGRATION_PATTERN.match(path.name)
            if match:
                migrations.append((int(match.group(1)), path))
        return sorted(migrations)

    def _apply_migration(self, version: int, migration_path: Path) -> None:
        script = migration_path.read_text(encoding="utf-8")
        connection = self.connect()
        try:
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
            )
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
