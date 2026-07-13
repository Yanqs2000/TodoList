# CLAUDE.md

Current repository guidance for coding agents.

## Architecture

- `frontend/`: React 19, TypeScript 5.8, Vite 7, Plain CSS, Vitest.
- `backend/`: Python 3.12, uv, FastAPI, Pydantic, standard-library `sqlite3`, pytest.
- `desktop/`: Tauri 2 and Rust; owns the Python sidecar, tray, shortcut, autostart, and packaging.
- `docs/`: current documentation separated by frontend, backend, and architecture.

The desktop app has no accounts or cloud sync. SQLite is the only production persistence layer. Do not add `localStorage` fallbacks or a browser data mode. Browser startup must remain unsupported.

## Commands

```bash
uv sync --directory backend --frozen
uv run --directory backend pytest
uv run --directory backend ruff check .
uv run --directory backend pyright

npm --prefix frontend test
npm --prefix frontend run build

bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
npm --prefix desktop run build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml -- -D warnings
```

## Data and failure rules

- Bootstrap is the authoritative initial snapshot for tasks, settings, and achievements.
- Mutations publish React state only after the backend succeeds.
- Infrastructure failures replace the main UI with the blocking startup gate.
- Retry starts a new backend connection and replaces the full snapshot.
- Task completion and achievement updates remain atomic in the backend.
- Reminder notifications require an atomic successful claim.
- Shortcut OS registration and SQLite persistence are coordinated by the Rust command; do not duplicate the settings write in React.

## Code conventions

- Keep cross-feature frontend imports on the `@/*` alias; relative imports are fine inside a feature.
- Preserve TypeScript strict mode and remove unused values.
- Keep Python wire models strict and camelCase-compatible; repositories own SQL, services own transactions.
- Never log bearer tokens, request bodies, task text, notes, database paths, SQL parameters, or raw tracebacks.
- Do not grant JavaScript shell spawn/execute permissions; Rust owns the sidecar.
- Make small, task-scoped changes and run the relevant layer's tests before the full gates.

## Important paths

- Frontend bootstrap: `frontend/src/app/hooks/useBootstrap.ts`
- Typed API client: `frontend/src/shared/api/`
- Backend entry: `backend/src/todo_backend/sidecar.py`
- SQL migrations: `backend/migrations/`
- Sidecar supervisor: `desktop/src-tauri/src/backend.rs`
- Tauri config: `desktop/src-tauri/tauri.conf.json`
- Documentation index: `docs/CLAUDE.md`
