# TodoList 文档索引

> 本文件是 `docs/` 的导航入口。
> - 项目**代码规则**见根目录 [`../CLAUDE.md`](../CLAUDE.md)
> - 项目**介绍**见根目录 [`../README.md`](../README.md)
> - 本目录**总览**见 [`project-overview.md`](./project-overview.md)

## 顶层文档

- [project-overview.md](./project-overview.md) - 项目总览（技术栈、功能清单、版本历史表）

## 分类目录

### 📒 development-logs/ — 版本开发日志
按版本号记录每个版本的开发内容：功能、设计决策、文件变更、测试。共 17 篇，v0.1.0 → v0.5.0。
- 入口：[project-overview.md 版本历史表](./project-overview.md#版本历史) 按版本跳转。

### 🐛 bug-fixes/ — Bug 修复记录
独立 bug 跟踪与已知问题。目前 bug 修复记录在各版本开发日志中（见 development-logs/），此目录用于后续跨版本的独立 bug 记录。
- 详见 [bug-fixes/README.md](./bug-fixes/README.md)

### 📐 plans/ — 模块设计 / 规划
模块设计方案、功能规划 spec、技术选型记录。
- 详见 [plans/README.md](./plans/README.md)

### 📖 guides/ — 操作指南
- [installation-guide.md](./guides/installation-guide.md) - macOS 安装与签名
- [testing-guide.md](./guides/testing-guide.md) - 测试指南

## 命名与归档约定

| 类型 | 目录 | 命名 |
|---|---|---|
| 版本日志 | `development-logs/` | `vX.Y.Z-简述.md` |
| 独立 bug 记录 | `bug-fixes/` | `<bug简述>.md` |
| 模块设计 spec | `plans/` | `<模块>-<简述>.md` |
| 操作指南 | `guides/` | `<主题>-guide.md` |

> 顶层只放 `project-overview.md` 与本索引；其余文档按类型归入子目录。
