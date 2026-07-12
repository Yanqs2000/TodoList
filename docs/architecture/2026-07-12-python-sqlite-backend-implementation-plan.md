# Python SQLite Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all application-owned localStorage persistence with a bundled Python FastAPI sidecar backed by SQLite while preserving current Todo List behavior.

**Architecture:** React runs inside Tauri and calls a loopback-only FastAPI sidecar through a typed HTTP client and an in-memory Bearer token. Tauri owns sidecar lifecycle and native integration; Python owns validation, transactions, migrations, and SQLite. Code is separated into frontend, backend, and desktop workspaces.

**Tech Stack:** React 19, TypeScript 5.8, Vite 7, Vitest 4, Tauri 2, Rust 2021, Python 3.12, uv, FastAPI, Uvicorn, Pydantic 2, sqlite3, pytest, Ruff, Pyright, PyInstaller.

## Global Constraints

- Target macOS Apple Silicon only; sidecar target is `aarch64-apple-darwin`.
- No users, login, cloud service, remote access, sync, backup, restore, or database-management UI.
- Do not migrate old localStorage; the first database-backed launch starts empty.
- Persist tasks, order, achievements, reminder claims, theme, mute state, and shortcut in SQLite.
- Keep autostart in the macOS/Tauri plugin because it is OS-owned state.
- Database or sidecar failures block the main UI; never fall back to memory or localStorage.
- Ship Python and dependencies inside the app; users do not install Python or uv.
- Preserve existing behavior and layout except startup, unsupported-browser, and blocking-error states.
- Preserve unrelated dirty worktree changes and stage only files belonging to each task.

---

## File Map

- `frontend/src/shared/api/`: wire contracts and authenticated API client.
- `frontend/src/app/hooks/useBootstrap.ts`: connection discovery, bootstrap, retry, fatal state.
- `frontend/src/app/components/StartupGate.tsx`: loading, unsupported, and blocking-error UI.
- `frontend/src/features/*/hooks/`: server-initialized state and database-first mutations.
- `backend/src/todo_backend/api.py`: FastAPI app and routes.
- `backend/src/todo_backend/database.py`: connections, PRAGMAs, transactions, migrations.
- `backend/src/todo_backend/repositories/`: SQL-only persistence.
- `backend/src/todo_backend/services/`: tasks, completion, achievements, reminders, settings.
- `desktop/src-tauri/src/backend.rs`: sidecar supervisor, health, restart, shutdown.
- `desktop/scripts/build-sidecar.sh`: PyInstaller and Tauri target-triple output.

### Task 1: Reorganize the repository without changing behavior

**Files:**
- Move: `src/`, `index.html`, Node/Vite/Vitest/TS files → `frontend/`
- Move: `src-tauri/` → `desktop/src-tauri/`
- Move: `scripts/sign-macos-bundle.sh` → `desktop/scripts/`
- Create: `desktop/package.json`
- Modify: `frontend/package.json`, `desktop/src-tauri/tauri.conf.json`

**Interfaces:**
- Produces: `npm --prefix frontend test`, `npm --prefix frontend run build`, `npm --prefix desktop run dev`.

- [ ] **Step 1: Verify the baseline**

~~~bash
npm test
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
~~~

Expected: 13 Vitest files and 91 tests pass; both builds succeed.

- [ ] **Step 2: Move tracked files with `git mv`**

~~~bash
mkdir -p frontend desktop/scripts
git mv src index.html package.json package-lock.json vite.config.ts vitest.config.ts tsconfig.json frontend/
git mv src-tauri desktop/src-tauri
git mv scripts/sign-macos-bundle.sh desktop/scripts/sign-macos-bundle.sh
~~~

- [ ] **Step 3: Create the desktop Node package**

~~~json
{
  "name": "todo-desktop",
  "private": true,
  "version": "0.5.0",
  "scripts": {
    "dev": "tauri dev",
    "build": "bash scripts/build-sidecar.sh && tauri build",
    "sign:macos": "bash scripts/sign-macos-bundle.sh"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.11.2"
  }
}
~~~

Remove Tauri CLI and Tauri build scripts from `frontend/package.json`. Generate `desktop/package-lock.json` with `npm --prefix desktop install --package-lock-only`.

- [ ] **Step 4: Point Tauri at the frontend**

~~~json
{
  "build": {
    "frontendDist": "../../frontend/dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "npm --prefix ../../frontend run dev",
    "beforeBuildCommand": "npm --prefix ../../frontend run build"
  }
}
~~~

Keep existing identifier, window, icon, plugin, and signing settings.

- [ ] **Step 5: Verify and commit**

~~~bash
npm --prefix frontend test
npm --prefix frontend run build
cargo check --manifest-path desktop/src-tauri/Cargo.toml
git diff --check
git add frontend desktop
git commit -m "chore: separate frontend and desktop workspaces"
~~~

### Task 2: Create the authenticated backend foundation and schema

**Files:**
- Create: `backend/.python-version`, `backend/pyproject.toml`, `backend/uv.lock`
- Create: `backend/src/todo_backend/{config,auth,database,errors}.py`
- Create: `backend/migrations/001_initial.sql`
- Test: `backend/tests/test_auth.py`, `backend/tests/test_database.py`

**Interfaces:**
- Produces: `Settings.from_env()`, `require_token()`, `Database.connect()`, `Database.transaction()`, `Database.initialize()`.

- [ ] **Step 1: Define Python 3.12 and dependencies**

Use `requires-python = ">=3.12,<3.13"`; runtime dependencies are FastAPI and Uvicorn. Development dependencies are HTTPX, PyInstaller, Pyright, pytest, pytest-cov, and Ruff. Configure Ruff for Python 3.12/100 columns and Pyright strict mode.

~~~bash
cd backend
uv lock
uv sync --frozen
~~~

- [ ] **Step 2: Write failing auth and migration tests**

~~~python
def test_initialize_creates_schema(database):
    database.initialize()
    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
    assert version == 1
    assert {"tasks", "achievement_state", "achievement_unlocks",
            "task_reminders", "app_settings"} <= tables
~~~

Also assert missing/wrong Bearer tokens return `401 UNAUTHORIZED`.

- [ ] **Step 3: Run red tests**

~~~bash
uv run pytest tests/test_auth.py tests/test_database.py -q
~~~

Expected: imports fail because backend modules do not exist.

- [ ] **Step 4: Implement the foundation**

Implement immutable `Settings` fields `database_path: Path`, `host: str`, `port: int`, and `token: str`, plus `Settings.from_env() -> Settings`. Implement `Database.__init__(path: Path, migrations_dir: Path)`, `connect() -> sqlite3.Connection`, the `transaction()` context manager, and `initialize() -> None`.

Require the explicit environment keys `TODO_DATABASE_PATH`, `TODO_BACKEND_PORT`, and `TODO_BACKEND_TOKEN`; force `127.0.0.1`; compare tokens using `secrets.compare_digest`; enable row factory, foreign keys, WAL, and a 5-second busy timeout. Apply numbered SQL files transactionally and reject a database version above the latest migration.

The migration creates all five approved tables, checks priority/category/boolean values, indexes task position, and uses `(task_id, scheduled_start)` with `ON DELETE CASCADE`.

- [ ] **Step 5: Verify and commit**

~~~bash
uv run pytest tests/test_auth.py tests/test_database.py -q
uv run ruff check .
uv run pyright
git add backend
git commit -m "feat: add authenticated SQLite backend foundation"
~~~

### Task 3: Implement task CRUD and persistent ordering

**Files:**
- Create: `backend/src/todo_backend/models.py`
- Create: `backend/src/todo_backend/repositories/tasks.py`
- Create: `backend/src/todo_backend/services/tasks.py`
- Create: `backend/src/todo_backend/api.py`, `backend/src/todo_backend/main.py`
- Test: `backend/tests/test_tasks_api.py`

**Interfaces:**
- Produces authenticated create, patch, delete, list-through-bootstrap, and order endpoints.

- [ ] **Step 1: Write failing API tests**

Cover create, edit, delete, invalid text/enums, missing task, and exact ordering. Assert duplicate, missing, or unknown order IDs return `400 INVALID_TASK_ORDER` without changing stored order.

~~~python
response = client.put(
    "/api/v1/tasks/order",
    headers=auth_headers,
    json={"taskIds": [second_id, first_id]},
)
assert response.status_code == 200
assert [task["id"] for task in response.json()["tasks"]] == [second_id, first_id]
~~~

- [ ] **Step 2: Run red tests**

~~~bash
uv run pytest tests/test_tasks_api.py -q
~~~

Expected: route imports or requests fail.

- [ ] **Step 3: Implement strict models and transactional services**

Implement `TaskRepository.list_all(connection) -> list[Task]`, `create(connection, command) -> Task`, `update(connection, task_id, command) -> Task`, `delete(connection, task_id) -> None`, and `replace_order(connection, task_ids) -> list[Task]`.

Use strict Pydantic models with `extra="forbid"`. Reject text/notes above 10,000 characters. Generate UUID v4 hex IDs and Unix-millisecond timestamps server-side. Insert new tasks at position 0 and increment existing positions in the same transaction.

- [ ] **Step 4: Verify and commit**

~~~bash
uv run pytest tests/test_tasks_api.py -q
uv run pytest -q
uv run ruff check .
uv run pyright
git add backend
git commit -m "feat: add task CRUD and ordering API"
~~~

### Task 4: Make completion and achievements atomic

**Files:**
- Create: `backend/src/todo_backend/repositories/achievements.py`
- Create: `backend/src/todo_backend/services/achievements.py`
- Modify: task service and API
- Test: `backend/tests/test_completion_api.py`

**Interfaces:**
- Produces: `PUT /api/v1/tasks/{id}/completion` returning `task`, `achievementState`, and `newlyUnlocked`.

- [ ] **Step 1: Write failing tests**

Test first completion, tenth same-day completion, seven-day streak, no decrement on uncomplete, no double count for repeated `completed=true`, and rollback after an injected achievement write failure.

~~~python
assert payload["task"]["completed"] is True
assert payload["achievementState"]["todayCompleted"] == 1
assert payload["newlyUnlocked"] == ["first-task"]
~~~

- [ ] **Step 2: Run red tests**

~~~bash
uv run pytest tests/test_completion_api.py -q
~~~

- [ ] **Step 3: Implement the transaction**

Use IDs `first-task`, `speed-demon`, and `streak-7`; thresholds are 1, 10, and 7. Accept `completed` and a validated `localDate`. Only a false-to-true transition records progress. Update task, singleton state, and unlock rows in one database transaction.

- [ ] **Step 4: Verify and commit**

~~~bash
uv run pytest tests/test_completion_api.py -q
uv run pytest -q
uv run ruff check .
uv run pyright
git add backend
git commit -m "feat: persist completion and achievements atomically"
~~~

### Task 5: Add bootstrap, settings, reminders, and stable errors

**Files:**
- Create: settings/reminder repositories and services
- Create: `backend/src/todo_backend/services/bootstrap.py`
- Modify: API and errors
- Test: bootstrap, settings, reminders, and errors API tests

**Interfaces:**
- Produces bootstrap snapshot `{tasks, settings, achievementState}`.
- Produces settings patch and atomic reminder-claim endpoints.
- Produces `{"error":{"code":string,"message":string}}`.

- [ ] **Step 1: Write failing tests**

Assert first bootstrap stores preferred theme, later bootstrap ignores a different preference, settings persist, reminder claims return true then false, rescheduling can claim again, deletion cascades, and SQLite failure returns sanitized `503 DATABASE_UNAVAILABLE`.

- [ ] **Step 2: Run red tests**

~~~bash
uv run pytest tests/test_bootstrap_api.py tests/test_settings_api.py tests/test_reminders_api.py tests/test_errors_api.py -q
~~~

- [ ] **Step 3: Implement services**

Bootstrap defaults: requested workspace theme, `muted=false`, shortcut `Cmd+Alt+KeyT`. Reminder claim uses `INSERT OR IGNORE`. Task time changes delete claims for old starts. Map domain errors to 4xx and database/migration errors to 503 without logging tokens, bodies, task text, notes, or SQL parameters.

- [ ] **Step 4: Verify and commit**

~~~bash
uv run pytest --cov=todo_backend --cov-report=term-missing -q
uv run ruff check .
uv run pyright
git add backend
git commit -m "feat: add bootstrap settings and reminder APIs"
~~~

Expected: tests pass and backend core line coverage is at least 90%.

### Task 6: Build a self-contained arm64 sidecar

**Files:**
- Create: `backend/todo-backend.spec`
- Create: `backend/tests/test_packaging_smoke.py`
- Create: `desktop/scripts/build-sidecar.sh`
- Modify: Tauri config and `.gitignore`

**Interfaces:**
- Produces: `desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin`.

- [ ] **Step 1: Write the packaging smoke test**

Launch the binary path from `TODO_BACKEND_BINARY` with a temporary DB, free port, and token; poll authenticated health; terminate and assert exit within five seconds. Skip only when the binary environment variable is absent.

- [ ] **Step 2: Implement PyInstaller and build script**

~~~bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
uv sync --frozen
uv run pyinstaller --noconfirm --clean todo-backend.spec
mkdir -p "$ROOT/desktop/src-tauri/binaries"
cp dist/todo-backend "$ROOT/desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin"
chmod +x "$ROOT/desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin"
~~~

Bundle migrations in the spec. Set `bundle.externalBin` to `["binaries/todo-backend"]`. Ignore generated PyInstaller and binary outputs.

- [ ] **Step 3: Build, test, and commit**

~~~bash
bash desktop/scripts/build-sidecar.sh
file desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin
uv run --directory backend pytest tests/test_packaging_smoke.py -q
git add backend/todo-backend.spec backend/tests/test_packaging_smoke.py desktop/scripts/build-sidecar.sh desktop/src-tauri/tauri.conf.json .gitignore
git commit -m "build: package Python backend as Tauri sidecar"
~~~

Expected: a Mach-O arm64 executable and passing smoke test.

### Task 7: Supervise the sidecar from Tauri

**Files:**
- Create: `desktop/src-tauri/src/backend.rs`
- Modify: `desktop/src-tauri/src/lib.rs`, Cargo files, capabilities
- Test: Rust backend module tests

**Interfaces:**
- Produces commands `get_backend_connection`, `retry_backend`, and transactional shortcut update.
- Emits `backend-unavailable`.

- [ ] **Step 1: Write failing pure-helper tests**

~~~rust
#[test]
fn token_has_256_bits_of_hex_entropy() {
    let token = generate_token();
    assert_eq!(token.len(), 64);
    assert!(token.chars().all(|value| value.is_ascii_hexdigit()));
}
~~~

Also test stopped/running/restarting transitions and loopback connection serialization.

- [ ] **Step 2: Run red tests**

~~~bash
cargo test --manifest-path desktop/src-tauri/Cargo.toml backend
~~~

- [ ] **Step 3: Implement supervisor and dependencies**

Add Tauri shell and single-instance plugins, `rand`, `reqwest` with rustls, and Tokio sync/time. Register single-instance first and focus the existing window on a second launch. Spawn `app.shell().sidecar("todo-backend")`, pass database path/port/token through `TODO_DATABASE_PATH`, `TODO_BACKEND_PORT`, and `TODO_BACKEND_TOKEN` environment variables, poll health for ten seconds, retry port binding up to three times, store child/state in an async mutex, emit unexpected exits, and kill intentionally on application exit.

Do not grant JavaScript shell spawn permission because Rust owns the child.

- [ ] **Step 4: Verify and commit**

~~~bash
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml -- --check
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
git add desktop/src-tauri
git commit -m "feat: supervise local Python backend from Tauri"
~~~

### Task 8: Add frontend API client and startup gate

**Files:**
- Create: `frontend/src/shared/api/contracts.ts`, `client.ts`, tests
- Create: `frontend/src/app/hooks/useBootstrap.ts`, tests
- Create: `frontend/src/app/components/StartupGate.tsx`, CSS
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- Produces typed `TodoApi`.
- Produces `loading | ready | unsupported | blocked` bootstrap states.

- [ ] **Step 1: Write failing tests**

Test Bearer injection, stable error parsing, timeout/network classification, Tauri detection, unsupported-browser state, bootstrap success, sidecar-exit blocking, and retry with full snapshot replacement.

- [ ] **Step 2: Run red tests**

~~~bash
npm --prefix frontend test -- src/shared/api src/app/hooks
~~~

- [ ] **Step 3: Implement contracts and gate**

~~~typescript
type BootstrapState =
  | { status: 'loading' }
  | { status: 'unsupported' }
  | { status: 'blocked'; message: string }
  | { status: 'ready'; api: TodoApi; snapshot: BootstrapSnapshot };
~~~

The client uses a ten-second AbortController timeout, JSON and Bearer headers, and never logs tokens/bodies. Bootstrap invokes Tauri connection discovery, passes system light/dark preference, listens for `backend-unavailable`, and retries through `retry_backend`.

- [ ] **Step 4: Verify and commit**

~~~bash
npm --prefix frontend test
npm --prefix frontend run build
git add frontend/src/shared/api frontend/src/app
git commit -m "feat: add backend API client and startup gate"
~~~

### Task 9: Convert tasks to database-first mutations

**Files:**
- Modify: task hook, tests, mutation controls, and App orchestration

**Interfaces:**
- Consumes initial tasks, `TodoApi`, and infrastructure-error callback.
- Produces async actions that update state only after API success.

- [ ] **Step 1: Replace localStorage tests**

Use a fake API and deferred promises. Assert state is unchanged before resolution, updates after success, remains unchanged after failure, and infrastructure failures call the fatal callback.

- [ ] **Step 2: Run red tests**

~~~bash
npm --prefix frontend test -- src/features/tasks/hooks
~~~

- [ ] **Step 3: Implement the hook**

~~~typescript
export function useTodos(
  initialTasks: Todo[],
  api: TodoApi,
  onInfrastructureError: (error: InfrastructureError) => void,
): TodoState
~~~

Remove storage reads/writes and client-side ID generation. Keep filter, category, priority selection, search, and sort mode local. Await API results before state updates. Disable only the mutation control currently pending.

- [ ] **Step 4: Verify and commit**

~~~bash
npm --prefix frontend test
npm --prefix frontend run build
git add frontend/src/features/tasks frontend/src/app/App.tsx
git commit -m "feat: persist task mutations through backend API"
~~~

### Task 10: Move all remaining persistence off localStorage

**Files:**
- Modify: achievement, reminder, theme, sound, desktop hooks and tests
- Modify: App orchestration
- Delete: `frontend/src/shared/lib/storage.ts`

**Interfaces:**
- Achievements consume server state/new unlock IDs.
- Reminders call atomic claim.
- Theme, mute, and shortcut consume/persist backend settings.

- [ ] **Step 1: Rewrite tests around API success and failure**

Assert theme/mute/shortcut change only after settings success, reminders notify only when `claimed=true`, and achievement feedback uses the completion response instead of React counter calculations.

- [ ] **Step 2: Run red tests**

~~~bash
npm --prefix frontend test -- src/features/achievements src/features/reminders src/features/theme src/features/desktop
~~~

- [ ] **Step 3: Implement server-owned state**

Initialize hooks from bootstrap. Keep achievement definitions/toast timers and reminder due scanning in React. Remove all persistent calculations/storage calls. Keep autostart in Tauri. Make shortcut registration and database persistence rollback to the previous shortcut on either failure.

- [ ] **Step 4: Prove production localStorage is gone**

~~~bash
rg -n "localStorage|safeGetItem|safeSetItem" frontend/src --glob '!**/__tests__/**' --glob '!test/setup.ts'
~~~

Expected: no matches.

- [ ] **Step 5: Verify and commit**

~~~bash
npm --prefix frontend test
npm --prefix frontend run build
git add frontend/src
git commit -m "feat: move application settings and progress to SQLite"
~~~

### Task 11: Harden security, recovery, and signing

**Files:**
- Modify: Tauri CSP/config, supervisor, signing script
- Modify: backend CORS/logging/shutdown
- Test: `frontend/src/app/__tests__/backendFailure.integration.test.tsx`

**Interfaces:**
- Only loopback backend connectivity is allowed.
- Logs contain no token, task text, notes, bodies, or SQL parameters.

- [ ] **Step 1: Add failing integration tests**

Cover sidecar exit, bootstrap 503, mutation network failure, retry snapshot replacement, and shortcut rollback. Assert fatal errors replace the main UI with the blocking gate.

- [ ] **Step 2: Run red tests**

~~~bash
npm --prefix frontend test -- src/app/__tests__/backendFailure.integration.test.tsx
cargo test --manifest-path desktop/src-tauri/Cargo.toml backend
~~~

- [ ] **Step 3: Implement hardening**

Replace `csp: null` with explicit app-asset and loopback-connect policy. Allow production Tauri origin and Vite localhost only in development CORS. Generate a new token on retry, stop the previous child before replacement, and redact sensitive log fields. Sign the nested sidecar before the containing app.

- [ ] **Step 4: Run all automated gates and commit**

~~~bash
uv run --directory backend pytest --cov=todo_backend --cov-report=term-missing -q
uv run --directory backend ruff check .
uv run --directory backend pyright
npm --prefix frontend test
npm --prefix frontend run build
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml -- --check
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
git diff --check
git add backend frontend desktop
git commit -m "fix: harden backend lifecycle and recovery"
~~~

### Task 12: Separate current docs and verify the packaged app

**Files:**
- Move: current testing guide → `docs/frontend/`
- Move: installation guide → `docs/architecture/`
- Create: `docs/backend/{development,api,database}.md`
- Create: `docs/architecture/runtime.md`
- Modify: root README, project overview, AGENTS, docs index
- Preserve: all historical development logs

**Interfaces:**
- Produces accurate setup, testing, API, schema, runtime, and packaging docs.

- [ ] **Step 1: Document exact commands**

~~~bash
uv sync --directory backend --frozen
uv run --directory backend pytest
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix desktop install
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
npm --prefix desktop run build
~~~

Document routes, errors, schema, migrations, token, lifecycle, and no-browser/no-localStorage policy. Repair every moved relative link.

- [ ] **Step 2: Verify current docs and source**

~~~bash
rg -n "localStorage 持久化|npm run tauri" README.md docs AGENTS.md --glob '!docs/development-logs/**'
rg -n "localStorage|safeGetItem|safeSetItem" frontend/src --glob '!frontend/src/test/setup.ts' --glob '!**/__tests__/**'
git diff --check
~~~

Expected: no stale current claims and no production storage references.

- [ ] **Step 3: Build and sign**

~~~bash
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run build
codesign --verify --deep --strict --verbose=2 "desktop/src-tauri/target/release/bundle/macos/Todo List.app"
~~~

Expected: sidecar, frontend, Tauri bundle, and signature verification succeed.

- [ ] **Step 4: Manual smoke test**

Add two richly populated tasks; reorder and edit; complete one and verify achievement feedback; change theme, mute, and shortcut; fully quit and relaunch; verify every persisted value/order; confirm browser mode shows unsupported state.

- [ ] **Step 5: Final clean verification and commit**

~~~bash
uv run --directory backend pytest --cov=todo_backend --cov-report=term-missing -q
uv run --directory backend ruff check .
uv run --directory backend pyright
npm --prefix frontend test
npm --prefix frontend run build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
git diff --check
git status --short
git add README.md AGENTS.md docs
git commit -m "docs: document Python SQLite desktop architecture"
~~~

## Official References

- Tauri external binaries: <https://v2.tauri.app/develop/sidecar/>
- Tauri single instance: <https://v2.tauri.app/plugin/single-instance/>
- Tauri development configuration: <https://v2.tauri.app/develop/>
