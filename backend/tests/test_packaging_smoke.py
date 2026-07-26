import os
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_packaged_sidecar_starts_and_stops(tmp_path: Path) -> None:
    binary_value = os.environ.get("TODO_BACKEND_BINARY")
    if binary_value is None:
        pytest.skip("TODO_BACKEND_BINARY is not set")

    binary = Path(binary_value)
    assert binary.is_file(), f"sidecar binary does not exist: {binary}"

    database_path = tmp_path / "todo.sqlite3"
    port = _free_port()
    token = "packaging-smoke-token"
    environment = os.environ.copy()
    environment.update(
        {
            "TODO_DATABASE_PATH": str(database_path),
            "TODO_BACKEND_PORT": str(port),
            "TODO_BACKEND_TOKEN": token,
        }
    )
    process = subprocess.Popen(  # noqa: S603
        [str(binary)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + 10
        last_error = "sidecar did not accept a connection"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                pytest.fail(f"sidecar exited before readiness:\n{output}")
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{port}/api/v1/health",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=0.5,
                )
                if response.status_code == 200:
                    break
                last_error = f"readiness returned {response.status_code}: {response.text}"
            except httpx.HTTPError as error:
                last_error = str(error)
            time.sleep(0.05)
        else:
            pytest.fail(f"sidecar did not become ready: {last_error}")

        assert database_path.is_file()
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            pytest.fail("sidecar did not exit within five seconds")

    with sqlite3.connect(database_path) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert user_version == 6
    assert "tasks" in tables
