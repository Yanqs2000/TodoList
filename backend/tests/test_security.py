# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

from fastapi.testclient import TestClient

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


def test_cors_allows_tauri_and_only_enables_vite_for_development(tmp_path: Path) -> None:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    production = Settings(database.path, "127.0.0.1", 8000, "test-token")

    with TestClient(create_app(settings=production, database=database)) as client:
        tauri = client.options(
            "/api/v1/bootstrap",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        vite = client.options(
            "/api/v1/bootstrap",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert tauri.headers["access-control-allow-origin"] == "tauri://localhost"
    assert "access-control-allow-origin" not in vite.headers

    development = Settings(
        database.path,
        "127.0.0.1",
        8000,
        "test-token",
        allow_vite_dev_origin=True,
    )
    with TestClient(create_app(settings=development, database=database)) as client:
        vite = client.options(
            "/api/v1/bootstrap",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert vite.headers["access-control-allow-origin"] == "http://localhost:5173"
