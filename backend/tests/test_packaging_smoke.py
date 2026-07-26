import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PACKAGED_SIDECAR_STARTUP_TIMEOUT = 30


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
        deadline = time.monotonic() + PACKAGED_SIDECAR_STARTUP_TIMEOUT
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


def test_packaged_sidecar_allows_only_one_process_per_database(tmp_path: Path) -> None:
    binary_value = os.environ.get("TODO_BACKEND_BINARY")
    if binary_value is None:
        pytest.skip("TODO_BACKEND_BINARY is not set")

    binary = Path(binary_value)
    database_path = tmp_path / "todo.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "TODO_DATABASE_PATH": str(database_path),
            "TODO_BACKEND_PORT": str(_free_port()),
            "TODO_BACKEND_TOKEN": "first-token",
        }
    )
    first = subprocess.Popen(  # noqa: S603
        [str(binary)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + PACKAGED_SIDECAR_STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if first.poll() is not None:
                output = first.stdout.read() if first.stdout is not None else ""
                pytest.fail(f"first sidecar exited before readiness:\n{output}")
            if database_path.exists():
                break
            time.sleep(0.05)
        else:
            pytest.fail("first sidecar did not initialize its database")

        second_environment = environment.copy()
        second_environment["TODO_BACKEND_PORT"] = str(_free_port())
        second_environment["TODO_BACKEND_TOKEN"] = "second-token"
        second = subprocess.run(  # noqa: S603
            [str(binary)],
            env=second_environment,
            capture_output=True,
            text=True,
            timeout=PACKAGED_SIDECAR_STARTUP_TIMEOUT,
            check=False,
        )

        assert second.returncode != 0
        assert "already owns this database" in (second.stdout + second.stderr)
    finally:
        if first.poll() is None:
            first.terminate()
        first.wait(timeout=5)


def test_packaged_sidecar_exits_after_its_parent_process_is_gone(tmp_path: Path) -> None:
    binary_value = os.environ.get("TODO_BACKEND_BINARY")
    if binary_value is None:
        pytest.skip("TODO_BACKEND_BINARY is not set")

    binary = Path(binary_value)
    database_path = tmp_path / "todo.sqlite3"
    pid_path = tmp_path / "sidecar.pid"
    parent_script = f"""
import os
import subprocess
import sys
import time
from pathlib import Path

binary, database_path, pid_path = sys.argv[1:]
environment = os.environ.copy()
environment["TODO_PARENT_STDIN_WATCH"] = "1"
child = subprocess.Popen(
    [binary],
    env=environment,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
Path(pid_path).write_text(str(child.pid), encoding="utf-8")
deadline = time.monotonic() + {PACKAGED_SIDECAR_STARTUP_TIMEOUT}
while time.monotonic() < deadline and not Path(database_path).exists():
    if child.poll() is not None:
        raise SystemExit("sidecar exited before initialization")
    time.sleep(0.05)
"""
    environment = os.environ.copy()
    environment.update(
        {
            "TODO_DATABASE_PATH": str(database_path),
            "TODO_BACKEND_PORT": str(_free_port()),
            "TODO_BACKEND_TOKEN": "parent-watch-token",
        }
    )
    parent = subprocess.run(  # noqa: S603
        [sys.executable, "-c", parent_script, str(binary), str(database_path), str(pid_path)],
        env=environment,
        timeout=PACKAGED_SIDECAR_STARTUP_TIMEOUT + 5,
        check=False,
    )
    assert parent.returncode == 0
    sidecar_pid = int(pid_path.read_text(encoding="utf-8"))

    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.killpg(sidecar_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("sidecar process group remained alive after its parent process exited")
    finally:
        try:
            os.killpg(sidecar_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
