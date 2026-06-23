# TodoList — 项目介绍

> 当前版本：**v0.4.3**（2026-06-19）  
> 仓库:https://github.com/Yanqs2000/TodoList

一个具有游戏化体验的待办事项应用，支持中文界面。采用纯前端技术栈，零第三方依赖，使用 Canvas API 实现粒子效果，Web Audio API 实现音效合成。

## 技术栈

- **框架**：React 19 + TypeScript 5.8
- **构建**：Vite 7 + `@vitejs/plugin-react`
- **样式**：Plain CSS + CSS 自定义属性（变量）主题系统
- **状态**：React Hooks + localStorage 持久化
- **桌面端**：Tauri 2（Rust，打包为原生 Mac .app）
- **测试**：Vitest 4 + @testing-library/react
- **零运行时依赖**：仅依赖 React，粒子用 Canvas API，音效用 Web Audio API

## 功能特性

### 🌙 6 主题系统
3 种风格 × 2 种明暗 = 6 套主题（工作台/薄荷/纸笺 × 浅/深）。右上角主题按钮打开 popover，色块预览即时切换，CSS 变量驱动，偏好持久化到 localStorage，含 legacy 值自动迁移。

### 🎉 撒花粒子系统
完成任务时从 checkbox 位置爆发彩色粒子，纯 Canvas 实现，带重力和旋转效果。

### 🔊 音效系统
Web Audio API 合成三种音效：完成（升调）、删除（短促）、成就（旋律）。右上角可静音。

### ↕️ 拖拽排序
HTML5 Drag & Drop API 实现任务重排，拖拽时有视觉反馈，排序结果持久化。

### 🏆 成就系统
三个成就徽章：
- **初出茅庐** — 完成第一个任务
- **效率达人** — 一天内完成 10 个任务
- **永不言弃** — 连续 7 天完成任务

解锁时弹出 Toast 通知 + 音效，点击奖杯图标打开成就面板。

### 📊 统计面板
底部显示：今日目标进度环（SVG）、连续打卡天数、总完成数。

### 📅 时间选择器
自定义日历 + 时间滚动选择器，支持时间点 / 时间段两种模式。

### 🏷️ 分类与备注
任务可分类（工作/学习/生活/其他），附备注，按分类过滤。

### 🔍 搜索
按文本、分类、备注全文搜索。

### ⏰ 时间提醒
为任务设置时间后，到时自动通过系统通知 + 5 秒柔和音效 + 屏内 toast 三重提醒。已提醒的任务持久化记录，重启不重复。

### 🍎 桌面原生体验（v0.4.0+）
- 系统托盘图标，左键切换显示，右键唤出菜单
- 关闭即隐藏到托盘，应用持续后台运行
- 全局热键 `⌘⌥T`（macOS）/ `Ctrl+Alt+T`（其他平台），可在设置中改
- 可选开机自启动
- 主题切换内嵌在设置面板（v0.4.1 起）

## 架构

### 数据流
`app/App.tsx` 编排多个 Hooks → 通过 props 传递状态和处理函数 → 组件触发 hook 方法更新状态 → localStorage 持久化。

### 目录结构（feature-based）
```
src/
├── app/                          # 应用入口
│   ├── App.tsx
│   ├── main.tsx
│   └── styles/App.css
├── features/                     # 按业务功能划分
│   ├── tasks/                    # 任务管理
│   │   ├── components/           # TaskList, TaskItem, Sidebar, DetailPanel,
│   │   │                         # CreateTaskModal, TimePicker, EmptyState
│   │   ├── hooks/                # useTodos, useDragDrop
│   │   ├── lib/                  # validateTodo, id, formatTime
│   │   └── styles/
│   ├── achievements/             # AchievementDrawer, Toast, useAchievements
│   ├── theme/                    # useTheme, ThemeSwitcher (6 主题)
│   ├── sound/                    # useSound
│   ├── confetti/                 # ConfettiCanvas
│   ├── feedback/                 # InfoToast
│   ├── header/                   # Header
│   └── stats/                    # Footer, ProgressRing
├── shared/                       # 跨功能共享
│   ├── lib/storage.ts            # safeSetItem / safeGetItem
│   ├── constants.ts              # CATEGORIES, PRIORITY_LABELS, DAILY_GOAL
│   └── types.ts
├── test/setup.ts
└── vite-env.d.ts
```

### 路径别名
`@/*` → `src/*`，所有 cross-feature import 用绝对路径。

### Hooks 职责
| Hook | 位置 | 职责 |
|------|------|------|
| `useTodos` | `features/tasks/hooks/` | 任务 CRUD、过滤、排序、搜索、localStorage 同步 |
| `useTheme` | `features/theme/hooks/` | 6 主题切换 + legacy 值自动迁移 |
| `useSound` | `features/sound/hooks/` | Web Audio 音效合成与静音控制 |
| `useAchievements` | `features/achievements/hooks/` | 成就解锁追踪、连续天数计算 |
| `useDragDrop` | `features/tasks/hooks/` | 拖拽状态管理（含 dragover 节流） |
| `useConfetti` | `features/confetti/components/ConfettiCanvas.tsx` | Canvas 粒子动画系统 |

## 开发命令

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动开发服务器 |
| `npm run build` | TypeScript 类型检查 + Vite 构建 |
| `npm run preview` | 预览生产构建 |
| `npm test` | 运行 Vitest 测试套件 |
| `npm run test:watch` | 监听模式 |
| `npm run test:coverage` | 生成覆盖率报告 |
| `npm run tauri dev` | 桌面应用开发模式 |
| `npm run tauri build` | 构建 Mac .app 和 .dmg（不签名） |
| `npm run tauri:build` | 构建 + 自动 ad-hoc 签名 .app 和 .dmg |
| `npm run sign:macos` | 对已构建产物做 ad-hoc 签名 |

## 桌面端构建

配置文件：`src-tauri/tauri.conf.json`，窗口默认 1080×720（最小 720×560），可调整大小。

产物：
- `src-tauri/target/release/bundle/macos/Todo List.app`
- `src-tauri/target/release/bundle/dmg/Todo List_0.4.3_aarch64.dmg`

需要 Rust 工具链（rustup）。国内需配置 crates.io 镜像（见 `~/.cargo/config.toml`）。

### 代码签名

本应用使用 ad-hoc 签名（无需 Apple Developer 账号）。`npm run tauri:build` 会自动调用 `scripts/sign-macos-bundle.sh` 对 `.app` 做深度签名 + hardened runtime，对 `.dmg` 做外层签名。

**用户首次打开需绕过 Gatekeeper**（右键打开或 `xattr -dr` 命令），详见 [installation-guide.md](./installation-guide.md)。

> 当前仅构建 Apple Silicon（arm64）架构。Intel Mac 暂不支持。

## 测试

65 个单元测试，覆盖 hooks、组件、工具函数。详见 [development-logs/v0.1.3-testing-guide.md](./development-logs/v0.1.3-testing-guide.md)。

```
Test Files  10 passed (10)
     Tests  65 passed (65)
```

## 版本历史

| 版本 | 日期 | 主要内容 |
| --- | --- | --- |
| [v0.1.0](./development-logs/v0.1.0-initial.md) | 2026-06-11 | 初始版本：暗色模式、撒花、音效、拖拽、成就、Tauri 打包 |
| [v0.1.1](./development-logs/v0.1.1-ime-fix.md) | 2026-06-11 | 修复中文输入法 Enter 误提交 |
| [v0.1.2](./development-logs/v0.1.2-time-picker.md) | 2026-06-12 | 自定义日历时间选择器 |
| [v0.1.3](./development-logs/v0.1.3-categories.md) | 2026-06-14 | 任务分类、备注、搜索、导入导出 |
| [v0.1.4](./development-logs/v0.1.4-code-review-bugfix.md) | 2026-06-17 | 系统性代码审查与 13 项 bug 修复 |
| [v0.1.5](./development-logs/v0.1.5-restructure.md) | 2026-06-17 | feature-based 项目结构重组 + 文档统一 |
| [v0.1.6](./development-logs/v0.1.6-macos-signing.md) | 2026-06-17 | macOS DMG 签名修复（ad-hoc + hardened runtime） |
| [v0.2.0](./development-logs/v0.2.0-redesign.md) | 2026-06-17 | 三栏布局重构 + 6 主题系统 + 创建任务模态 |
| [v0.2.1](./development-logs/v0.2.1-feedback-tweaks.md) | 2026-06-18 | 用户反馈调整：mint 主题 + 默认进行中 + 移除导入导出 |
| [v0.3.0](./development-logs/v0.3.0-reminders.md) | 2026-06-18 | 时间提醒功能 + mint 主题淡雅化 |
| [v0.3.1](./development-logs/v0.3.1-time-tweaks.md) | 2026-06-19 | 详情面板支持修改时间 + 默认时间为当前 |
| [v0.4.0](./development-logs/v0.4.0-desktop-native.md) | 2026-06-19 | 桌面原生体验：托盘 + 全局热键 + 关闭隐藏 + 自启动 |
| [v0.4.1](./development-logs/v0.4.1-shortcut-fix.md) | 2026-06-19 | 设置面板整合主题 + 热键录制修复 + 默认 ⌘⌥T |
| [v0.4.2](./development-logs/v0.4.2-confirm-dialog.md) | 2026-06-19 | 修复清除已完成/删除按钮无效（window.confirm 替换为应用内对话框） |
| [v0.4.3](./development-logs/v0.4.3-category-default.md) | 2026-06-19 | 修复无分类任务无法在分类筛选中找到（默认归「其他」） |

## 后续规划

详见 [v0.1.4 修复记录末尾](./development-logs/v0.1.4-code-review-bugfix.md#后续建议未在本轮修复)：
1. ConfettiCanvas 窗口 resize 适配
2. AchievementDrawer focus trap
3. 删除/清除已完成撤销机制
4. 暗色模式 priority-tag 配色适配
