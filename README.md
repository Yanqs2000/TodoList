# TodoList

TodoList 是一个中文桌面待办应用，使用 React + Tauri 提供任务管理、拖拽排序、提醒、主题、音效和成就反馈。应用数据由随桌面程序启动的 Python 后端写入本机 SQLite；不需要账号，也不会把数据同步到云端。

## 当前架构

```text
frontend/  React 19 + TypeScript + Vite
backend/   Python 3.12 + FastAPI + sqlite3，使用 uv 管理环境
desktop/   Tauri 2 + Rust，负责 sidecar、托盘、快捷键和打包
docs/      按前端、后端和运行架构分类的文档
```

Tauri 启动 Python sidecar，并通过仅监听 `127.0.0.1` 的带随机 Bearer token API 与它通信。任务、主题、静音、快捷键、成就和提醒 claim 都保存在 `todo.sqlite3` 中；生产前端不使用 `localStorage`。普通浏览器模式不提供降级数据层，只显示“请通过桌面应用运行”。

## 功能

- 任务创建、编辑、删除、完成、搜索、分类和优先级
- 手动拖拽排序与 Today Focus 时间轴
- 6 套明暗主题、Web Audio 音效和 Canvas 撒花
- 本地系统提醒与原子去重
- 成就、连续完成天数和今日统计
- macOS 托盘、关闭到托盘、全局快捷键和开机自启动
- 后端异常时阻断主界面，可显式重试并加载完整数据库快照

## 开发环境

要求：Node.js、npm、Python 3.12、[uv](https://docs.astral.sh/uv/)、Rust 工具链，以及 macOS arm64（构建当前 sidecar 时）。

```bash
# Python 后端
uv sync --directory backend --frozen
uv run --directory backend pytest

# 前端
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build

# 桌面端
npm --prefix desktop install
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
```

构建安装包：

```bash
npm --prefix desktop run build
npm --prefix desktop run sign:macos
```

产物位于：

- `desktop/src-tauri/target/release/bundle/macos/Todo List.app`
- `desktop/src-tauri/target/release/bundle/dmg/`

## 文档

- [项目总览](docs/project-overview.md)
- [运行架构](docs/architecture/runtime.md)
- [后端开发](docs/backend/development.md)
- [HTTP API](docs/backend/api.md)
- [SQLite 数据库](docs/backend/database.md)
- [前端测试](docs/frontend/testing.md)
- [macOS 安装与构建](docs/architecture/installation.md)
- [文档索引](docs/CLAUDE.md)

历史版本记录保留在 [docs/development-logs](docs/development-logs/) 中；这些日志描述对应版本当时的实现，不代表当前架构。
