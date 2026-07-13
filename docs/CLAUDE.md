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

## 历史与归档

- [development-logs](development-logs/) — v0.1.0 至 v0.5.0 的版本日志，保持历史原文
- [bug-fixes](bug-fixes/README.md) — 独立问题记录入口
- [plans](plans/README.md) — 旧模块规划入口

## 归档约定

| 文档类型 | 目录 |
| --- | --- |
| 前端操作与测试 | `docs/frontend/` |
| 后端开发、API、数据 | `docs/backend/` |
| 运行、安装和跨层设计 | `docs/architecture/` |
| 历史版本日志 | `docs/development-logs/` |
