# TodoList

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

TodoList 是一个支持中文和英文的桌面待办应用，使用 React + Tauri 提供任务管理、拖拽排序、提醒、主题、音效和成就反馈。应用数据由随桌面程序启动的 Python 后端写入本机 SQLite；不需要账号，也不会把数据同步到云端。当前稳定版本为 **v1.3.0**。

## 当前架构

```text
frontend/  React 19 + TypeScript + Vite
backend/   Python 3.12 + FastAPI + sqlite3，使用 uv 管理环境
desktop/   Tauri 2 + Rust，负责 sidecar、托盘、快捷键和打包
docs/      按前端、后端和运行架构分类的文档
```

Tauri 启动 Python sidecar，并通过仅监听 `127.0.0.1` 的带随机 Bearer token API 与它通信。任务、界面语言、主题、静音、快捷键、成就和提醒 claim 都保存在 `todo.sqlite3` 中；生产前端不使用 `localStorage`。普通浏览器模式不提供降级数据层，只显示“请通过桌面应用运行”。

## 功能

- 任务创建、编辑、删除、完成、搜索、分类和优先级
- 手动拖拽排序与 Today Focus 时间轴
- 6 套明暗主题、Web Audio 音效和 Canvas 撒花
- 本地系统提醒与原子去重
- 成就、连续完成天数和今日统计
- 首页 `EN` / `中文` 按钮切换完整中英文界面，并在 SQLite 中保存选择
- macOS 托盘、关闭到托盘、全局快捷键和开机自启动
- 后端异常时阻断主界面，可显式重试并加载完整数据库快照
- AI 助手：接入火山引擎方舟多模态模型，支持文字、语音（转写或直发）、图片和文档分析；后端使用独立的 LangGraph 对话规划与提议应用工作流（analyze → plan → execute → reflect），创建/更新提议在可编辑批次卡中一次确认，删除提议显示目标快照；SSE 实时流式展示模型思考过程（意图分析、计划生成、执行、自检）；跨轮会话记忆系统（上下文历史 + 结构化 turn memory）；Enter 发送 / Shift+Enter 换行；推挤动画布局，主题自适应

## AI 助手配置

AI 助手需要火山引擎方舟的 API Key。支持两种套餐：

| 套餐 | Base URL | API Key |
|---|---|---|
| **Agent Plan**（推荐） | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 专属 Key |
| Token Plan / 按量计费 | `https://ark.cn-beijing.volces.com/api/v3` | 普通方舟 Key |

配置步骤：打开应用 → 点击 header 右侧 ✦ 按钮 → 点击 ⚙ 设置 → 填入 API Key、Base URL、对话模型和音频模型 → 保存。

默认模型：对话 `doubao-seed-2-1-pro-260628`，音频 `doubao-seed-2-0-lite-260428`。API Key 仅保存在本机 SQLite，不回传、不写日志。

## v1.3.0

v1.3.0 重构了 AI 助手的核心架构：引入 LangGraph 多节点工作流（analyze → plan → execute → reflect），拆除正则匹配改由模型自主判断意图；新增 SSE 实时流式传输，前端可展示模型思考的每一步（意图分析推理、计划详情、自检结果）；实现跨轮会话记忆系统（完整对话历史注入 + 结构化 turn memory）；修复查询路径无上下文、助手回复无语义价值等记忆缺陷。前端新增今日摘要切换按钮、助手按钮切换、任务详情与摘要合并布局、Enter 发送等交互优化。Prompt 改用正面能力清单，消除模型误以为自己只能创建不能修改的问题。

完整变更见 [v1.3.0 发布日志](docs/development-logs/v1.3.0-agent-memory-sse.md)。

## v1.0.0

v1.0.0 将应用的数据层升级为随桌面程序分发的 Python/FastAPI + SQLite 后端，并由 Tauri 负责 sidecar 生命周期和安全连接。前端、后端、桌面端与文档已拆分为独立目录，任务、设置、成就和提醒状态统一由本机数据库持久化。本版本同时提供完整中英文界面：英文日期按 `en-US` 显示，用户输入的任务标题和备注保持原文。

从 v0.5.0 升级时，旧版 `localStorage` 数据不会自动导入，首次运行 v1.0.0 会创建新的 SQLite 数据库。完整变更见 [v1.0.0 发布日志](docs/development-logs/v1.0.0-python-sqlite-desktop.md)。

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

## 开发约定

- 前端跨功能模块使用 `@/*` 导入；持久化数据只能通过后端读写，不能增加 `localStorage` 降级路径。
- 后端由 repository 负责 SQL、service 负责事务；数据库结构变更使用新的编号迁移，不修改已经发布的迁移。
- 桌面端 Rust 负责 sidecar 的启动、健康检查、重试、监控和关闭；前端 JavaScript 不获得 shell 执行权限。
- 服务只监听本机回环地址并使用 Bearer token；日志不得包含 token、任务正文、备注、数据库路径或 SQL 参数。
- 修改后运行与受影响层对应的最小检查；具体命令和设计细节参见下方文档。

## 文档

- [项目总览](docs/project-overview.md)
- [运行架构](docs/architecture/runtime.md)
- [后端开发](docs/backend/development.md)
- [HTTP API](docs/backend/api.md)
- [SQLite 数据库](docs/backend/database.md)
- [前端测试](docs/frontend/testing.md)
- [macOS 安装与构建](docs/architecture/installation.md)
- [文档索引](docs/CLAUDE.md)

版本记录保留在 [docs/development-logs](docs/development-logs/) 中；旧日志描述对应版本当时的实现，不代表当前架构。

## 开源

本项目采用 [MIT](LICENSE) 许可证。欢迎提交 Issue 和 Pull Request，详见 [贡献指南](CONTRIBUTING.md)。
