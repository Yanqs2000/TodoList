<div align="center">

# ✓ Todo List

### 本机优先的智能待办桌面应用 · AI 助手 · 离线可用

[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)](https://github.com/Yanqs2000/TodoList/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20arm64-lightgrey.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built with Tauri](https://img.shields.io/badge/built%20with-Tauri%202-orange.svg)](https://tauri.app/)
[![Python](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-19-61DAFB.svg?logo=react)](https://react.dev/)

</div>

---

中文 | [English](#english)

Todo List 是一个支持中文和英文的桌面待办应用，使用 React + Tauri 提供任务管理、拖拽排序、提醒、主题、音效和成就反馈。内置 AI 助手接入火山引擎方舟多模态模型，通过 LangGraph 多节点工作流实现意图分析、计划生成、执行、自检的全流程智能辅助。

应用数据由随桌面程序启动的 Python 后端写入本机 SQLite；**不需要账号，也不会把数据同步到云端**。

## 功能

- **任务管理** — 创建、编辑、删除、完成、搜索、分类（工作/学习/生活/其他）和优先级（高/中/低）
- **手动拖拽排序** — 自由排列任务顺序，支持 Today Focus 时间轴视图
- **6 套主题** — 工作台 / 薄荷 / 纸笺 × 浅色 / 深色，Web Audio 音效，Canvas 撒花
- **本地提醒** — 系统通知，原子去重
- **成就系统** — 连续完成天数、今日统计、里程碑解锁
- **中英文界面** — `EN` / `中文` 按钮一键切换，语言偏好持久化到 SQLite
- **macOS 桌面集成** — 托盘、关闭到托盘、全局快捷键、开机自启动
- **数据安全** — 纯本机 SQLite，不依赖云服务，不收集数据

## AI 助手

基于 LangGraph 的多节点智能工作流：

```
analyze（意图分析）→ plan（计划生成）→ execute（执行）→ reflect（自检）
```

- **多模态输入** — 文字、语音（转写或直发）、图片、文档（PDF/Word/Markdown）
- **SSE 实时流式** — 实时展示模型思考的每一步（意图推理 → 计划详情 → 自检结果）
- **跨轮记忆** — 对话历史注入 + 结构化 turn memory，模型能记住上下文
- **确认卡片** — 创建/更新提议在可编辑批次卡中一次确认，删除显示目标快照；支持部分成功重试
- **推挤动画** — 助手面板、今日摘要均有平滑的推入动画

### 配置

AI 助手需要火山引擎方舟的 API Key。支持两种套餐：

| 套餐 | Base URL | API Key |
|---|---|---|
| **Agent Plan**（推荐） | `https://ark.cn-beijing.volces.com/api/plan/v3` | Agent Plan 专属 Key |
| Token Plan / 按量计费 | `https://ark.cn-beijing.volces.com/api/v3` | 普通方舟 Key |

配置步骤：打开应用 → 点击 ✦ 按钮 → ⚙ 设置 → 填入 API Key 和模型 → 保存。API Key 仅保存在本机 SQLite。

## 开发

要求：Node.js、npm、Python 3.12、[uv](https://docs.astral.sh/uv/)、Rust 工具链、macOS arm64。

```bash
# Python 后端
uv sync --directory backend --frozen
uv run --directory backend pytest

# 前端
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build

# 桌面端开发
npm --prefix desktop install
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
```

构建安装包：

```bash
npm --prefix desktop run build
npm --prefix desktop run sign:macos
```

产物位于 `desktop/src-tauri/target/release/bundle/macos/Todo List.app` 和 `dmg/`。

## 架构

```text
frontend/  React 19 + TypeScript + Vite
backend/   Python 3.12 + FastAPI + SQLite，uv 管理环境
desktop/   Tauri 2 + Rust，sidecar 生命周期、托盘、快捷键、打包
docs/      按前端、后端、运行架构分类的文档
```

Tauri 启动 Python sidecar，通过仅监听 `127.0.0.1` 的随机 Bearer token API 通信。所有数据保存在本机 SQLite，前端不使用 localStorage。

## 文档

- [项目总览](docs/project-overview.md)
- [运行架构](docs/architecture/runtime.md)
- [后端开发](docs/backend/development.md)
- [HTTP API](docs/backend/api.md)
- [SQLite 数据库](docs/backend/database.md)
- [前端测试](docs/frontend/testing.md)
- [macOS 安装与构建](docs/architecture/installation.md)
- [文档索引](docs/CLAUDE.md)

版本记录：[development-logs](docs/development-logs/)

## 开源

本项目采用 [MIT](LICENSE) 许可证。欢迎提交 Issue 和 Pull Request，详见 [贡献指南](CONTRIBUTING.md)。

---

<h2 id="english">English</h2>

Todo List is a desktop to-do application with full Chinese and English support, built with React + Tauri. It features task management, drag-and-drop sorting, reminders, themes, sound effects, and achievements. The built-in AI assistant uses ByteDance Volcano Engine's multimodal models with a LangGraph multi-node workflow (analyze → plan → execute → reflect) for intelligent task assistance.

All data is stored in a local SQLite database managed by a Python backend launched alongside the desktop app. **No account required, no cloud sync.**

### Features

- **Task Management** — Create, edit, delete, complete, search, categories (work/study/life/other), priorities (high/medium/low)
- **Drag & Drop** — Manual task ordering with Today Focus timeline view
- **6 Themes** — Workspace / Mint / Paper × Light / Dark, Web Audio, Canvas confetti
- **Local Reminders** — System notifications with atomic deduplication
- **Achievements** — Streak days, daily stats, milestone unlocks
- **Bilingual** — One-click `EN` / `中文` switch, persisted to SQLite
- **macOS Integration** — Tray, close-to-tray, global shortcut, auto-launch
- **Privacy** — 100% local SQLite, no cloud dependency, no data collection

### AI Assistant

Multi-modal input (text, voice, images, documents) with real-time SSE streaming of the agent's thinking process. Confirmation cards for create/update/delete with editable batch review. Cross-turn conversation memory.

Configuration: ByteDance Volcano Engine API key required. Open app → ✦ → ⚙ Settings → enter credentials.

### Quick Start

Requires: Node.js, npm, Python 3.12, uv, Rust toolchain, macOS arm64.

```bash
uv sync --directory backend --frozen
npm --prefix frontend install
npm --prefix desktop install
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
```

Build: `npm --prefix desktop run build && npm --prefix desktop run sign:macos`

### License

[MIT](LICENSE) — contributions welcome via [Issues and PRs](CONTRIBUTING.md).
