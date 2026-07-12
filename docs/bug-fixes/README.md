# Bug 修复记录

本目录用于独立 bug 跟踪与已知问题记录。

## 现状

当前所有 bug 修复已记录在 [版本开发日志](../development-logs/) 中（按版本），例如：

| 版本 | 修复内容 |
|---|---|
| [v0.1.1](../development-logs/v0.1.1-ime-fix.md) | 中文输入法 Enter 误提交 |
| [v0.1.4](../development-logs/v0.1.4-code-review-bugfix.md) | 系统性代码审查与 13 项 bug 修复 |
| [v0.1.6](../development-logs/v0.1.6-macos-signing.md) | macOS DMG 签名修复 |
| [v0.4.1](../development-logs/v0.4.1-shortcut-fix.md) | 全局热键录制修复 |
| [v0.4.2](../development-logs/v0.4.2-confirm-dialog.md) | 清除已完成/删除按钮无效（window.confirm 替换为应用内对话框） |
| [v0.4.3](../development-logs/v0.4.3-category-default.md) | 无分类任务无法在分类筛选中找到（默认归「其他」） |

## 何时在此目录新增

- 跨版本的独立 bug 追踪（不绑定单一版本发布）
- 已知问题清单（known issues）
- 复现步骤 + 根因 + 修复方案的独立记录

## 命名约定

`<bug简述>.md`，例如 `ime-enter-submit.md`。
