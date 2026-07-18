# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from todo_backend.api import create_app
from todo_backend.config import Settings
from todo_backend.database import Database


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    with TestClient(create_app(settings=settings, database=database)) as test_client:
        yield test_client


def test_settings_patch_persists_only_supplied_fields(client: TestClient) -> None:
    headers = {"Authorization": "Bearer test-token"}
    initialized = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-light"},
    )
    assert initialized.status_code == 200

    muted = client.patch("/api/v1/settings", headers=headers, json={"muted": True})
    shortcut = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"theme": "mint-dark", "shortcut": "Cmd+Shift+KeyN"},
    )
    restarted = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-dark"},
    )

    assert muted.status_code == 200
    assert muted.json() == {
        "settings": {
            "theme": "workspace-light",
            "muted": True,
            "shortcut": "Cmd+Alt+KeyT",
            "language": "zh-CN",
        }
    }
    assert shortcut.status_code == 200
    assert shortcut.json()["settings"] == {
        "theme": "mint-dark",
        "muted": True,
        "shortcut": "Cmd+Shift+KeyN",
        "language": "zh-CN",
    }
    assert restarted.json()["settings"] == shortcut.json()["settings"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"theme": "unknown"},
        {"muted": "true"},
        {"shortcut": ""},
        {"shortcut": "KeyT"},
        {"shortcut": "not a shortcut"},
        {"shortcut": "Cmd+"},
        {"shortcut": None},
        {"language": "fr"},
        {"unknown": True},
    ],
)
def test_settings_patch_rejects_invalid_payloads(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    headers = {"Authorization": "Bearer test-token"}
    client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-light"},
    )

    response = client.patch("/api/v1/settings", headers=headers, json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "INVALID_REQUEST", "message": "Invalid request"}
    }


def test_language_setting_defaults_and_persists(client: TestClient) -> None:
    headers = {"Authorization": "Bearer test-token"}
    initialized = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-light"},
    )

    changed = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"language": "en"},
    )
    restarted = client.post(
        "/api/v1/bootstrap",
        headers=headers,
        json={"preferredTheme": "workspace-dark"},
    )

    assert initialized.json()["settings"]["language"] == "zh-CN"
    assert changed.status_code == 200
    assert changed.json()["settings"]["language"] == "en"
    assert restarted.json()["settings"]["language"] == "en"
