#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "The todo backend sidecar can only be built on macOS arm64." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
uv sync --frozen
uv run pyinstaller --noconfirm --clean todo-backend.spec
mkdir -p "$ROOT/desktop/src-tauri/binaries"
cp dist/todo-backend "$ROOT/desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin"
chmod +x "$ROOT/desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin"
