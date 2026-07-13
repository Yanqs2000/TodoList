# 后端开发指南

后端位于 `backend/`，要求 Python 3.12，由 `uv` 管理锁定环境。它作为本地 sidecar 使用，不是面向公网部署的多用户服务。

## 环境与质量检查

```bash
uv sync --directory backend --frozen
uv run --directory backend pytest
uv run --directory backend pytest --cov=todo_backend --cov-report=term-missing -q
uv run --directory backend ruff check .
uv run --directory backend pyright
```

目录职责：

- `src/todo_backend/api.py`：FastAPI 路由和稳定错误 envelope
- `models.py`：严格 Pydantic wire models
- `services/`：事务与业务流程
- `repositories/`：SQL 和 row 映射
- `database.py`：连接、WAL、迁移和事务 context manager
- `sidecar.py`：读取环境并启动 Uvicorn
- `migrations/`：递增编号 SQL 迁移

## 单独运行

通常应由 Tauri 启动 sidecar。调试时可以手动提供同样的环境：

```bash
TODO_DATABASE_PATH=/tmp/todo.sqlite3 \
TODO_BACKEND_PORT=43123 \
TODO_BACKEND_TOKEN=dev-only-token \
TODO_BACKEND_ALLOW_VITE_ORIGIN=1 \
uv run --directory backend python -m todo_backend.sidecar
```

服务始终强制监听 `127.0.0.1`。除开发调试外不要启用 Vite CORS。请求必须包含：

```text
Authorization: Bearer <TODO_BACKEND_TOKEN>
Content-Type: application/json
```

## 打包 sidecar

在 macOS arm64 上运行：

```bash
bash desktop/scripts/build-sidecar.sh
```

脚本会执行 frozen `uv sync`、运行 PyInstaller，并复制为 Tauri 需要的 target-triple 文件：

```text
desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin
```

该生成文件被 `.gitignore` 排除，不应提交。

## 约束

- 不记录 token、请求正文、任务文本、备注、数据库路径或 SQL 参数。
- API 返回稳定的公开错误，不返回 traceback 或 SQLite 细节。
- 新 schema 变更必须新增迁移；不要修改已经发布的迁移。
- service 决定事务边界，repository 不自行开启嵌套事务。
