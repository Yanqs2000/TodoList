# TodoList — 游戏化待办事项应用

一个具有游戏化体验的待办事项应用，支持中文界面。采用纯前端技术栈，零第三方依赖，使用 Canvas API 实现粒子效果，Web Audio API 实现音效合成。

## 技术栈

- **框架**: React 19 + TypeScript 5.8
- **构建工具**: Vite 7 + @vitejs/plugin-react
- **样式**: Plain CSS + CSS 自定义属性（变量）主题系统
- **状态管理**: React Hooks + localStorage 持久化
- **桌面端**: Tauri 2（Rust，打包为原生 Mac .app）
- **零依赖**: 仅依赖 React，粒子用 Canvas API，音效用 Web Audio API

## 功能特性

### 🌙 深色模式

右上角太阳/月亮图标切换，CSS 变量驱动全局配色，偏好持久化到 localStorage。

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

## 架构

**数据流**: `App.tsx` 编排多个 Hooks → 通过 props 传递状态和处理函数

### Hooks

- `useTodos` — 任务增删改查、过滤、排序、localStorage 同步
- `useTheme` — 深色/浅色模式切换
- `useSound` — Web Audio 音效合成与静音控制
- `useAchievements` — 成就解锁追踪、连续天数计算
- `useDragDrop` — 拖拽状态管理
- `useConfetti` — Canvas 粒子动画系统

### 组件

- `Header` — 标题 + 操作按钮（静音、成就、主题切换）
- `TaskInput` — 文本输入，回车提交
- `PrioritySelector` — 低/中/高优先级选择
- `FilterTabs` — 全部/未完成/已完成 过滤
- `TaskList` → `TaskItem` — 任务列表，支持拖拽排序
- `Footer` — 进度环、连续天数、统计、清除已完成
- `ConfettiCanvas` — 全屏 Canvas 粒子覆盖层
- `AchievementDrawer` — 侧边抽屉展示成就
- `Toast` — 成就解锁通知
- `ProgressRing` — SVG 环形进度指示器

## 开发命令

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动开发服务器 |
| `npm run build` | TypeScript 类型检查 + Vite 构建 |
| `npm run preview` | 预览生产构建 |
| `npm run tauri dev` | 桌面应用开发模式 |
| `npm run tauri build` | 构建 Mac .app 和 .dmg |

## 桌面端构建

配置文件: `src-tauri/tauri.conf.json`，窗口 640×800，可调整大小。

产物:

- `src-tauri/target/release/bundle/macos/Todo List.app`（约 8MB）
- `src-tauri/target/release/bundle/dmg/Todo List_0.1.0_aarch64.dmg`（约 3MB）

需要 Rust 工具链（rustup）。国内需配置 crates.io 镜像。
