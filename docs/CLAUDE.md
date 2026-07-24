# TodoList 文档索引

当前项目介绍见 [README](../README.md) 和 [项目总览](project-overview.md)。历史开发日志记录各版本当时的实现，当前命令与架构以本索引链接的分类文档为准。

## 前端

- [测试指南](frontend/testing.md) — Vitest、构建和测试目录

## 后端

- [开发指南](backend/development.md) — Python 3.12、uv、本地运行与质量检查
- [HTTP API](backend/api.md) — 鉴权、路由、请求响应和稳定错误
- [SQLite 数据库](backend/database.md) — 文件位置、表、迁移、事务和备份

## 桌面与架构

- [运行架构](architecture/runtime.md) — Tauri、Python sidecar、bootstrap、失败恢复和安全边界
- [macOS 安装与构建](architecture/installation.md) — 安装、打包、签名和卸载
- [Python SQLite 后端设计](architecture/2026-07-12-python-sqlite-backend-design.md)
- [Python SQLite 后端实施计划](architecture/2026-07-12-python-sqlite-backend-implementation-plan.md)

## AI 助手

- [2026-07-25 v1.3.0 Agent 记忆系统与 SSE 实时流式传输](development-logs/v1.3.0-agent-memory-sse.md) — **v1.2→v1.3**：跨轮记忆修复、SSE 流式传输、前端交互优化、prompt 能力清单修正
- [2026-07-22 Agent 回复超时修复日志](development-logs/2026-07-22-agent-reply-timeout.md) — thinking 超时根因、修复决策、回归与包内真实请求证据
- [2026-07-23 Agent 架构演进](development-logs/2026-07-23-agent-architecture-evolution.md) — **v1.1→v1.2**：analyze 思考层 + reflect 自检层 + 拆除正则、增强 repair 上下文
- [2026-07-23 Agent 架构 v2 实施计划](development-logs/2026-07-23-agent-architecture-v2-plan.md) — 分阶段实施：analyze→repair→reflect→跨轮记忆
- [LangGraph agent redesign 设计](superpowers/specs/2026-07-22-langgraph-agent-redesign-design.md) — v1.0/v1.1 原始设计基线，不代表当前 v1.2 架构
- [LangGraph agent redesign 实施计划](superpowers/plans/2026-07-22-langgraph-agent-redesign.md) — 当前实施计划
- [LangGraph redesign 验证交接](superpowers/plans/2026-07-22-langgraph-agent-redesign-test-handoff.md) — Tasks 4–13 延期测试的环境决策、分阶段命令和风险清单
- [AI 助手原始设计基线](superpowers/specs/2026-07-20-ai-assistant-design.md) — 2026-07-20 原始实现基线，不代表当前 LangGraph 架构
- [AI 助手原始实施基线](superpowers/plans/2026-07-20-ai-assistant.md) — 2026-07-20 原始实施基线，不作为当前执行计划

## 历史与归档

- [v1.0.0 发布日志](development-logs/v1.0.0-python-sqlite-desktop.md) — Python/FastAPI + SQLite 桌面架构正式发布
- [development-logs](development-logs/) — v0.1.0 至 v1.0.0 的版本日志，保持历史原文
- [bug-fixes](bug-fixes/README.md) — 独立问题记录入口
- [plans](plans/README.md) — 旧模块规划入口

## 归档约定

| 文档类型 | 目录 |
| --- | --- |
| 前端操作与测试 | `docs/frontend/` |
| 后端开发、API、数据 | `docs/backend/` |
| 运行、安装和跨层设计 | `docs/architecture/` |
| 历史版本日志 | `docs/development-logs/` |
