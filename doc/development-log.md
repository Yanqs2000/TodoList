# TodoList 开发日志

## 项目概述

一个具有游戏化体验的待办事项应用，支持中文界面。采用纯前端技术栈，零第三方依赖。

**技术栈：**
- React 19 + TypeScript 5.8
- Vite 7 构建
- Tauri 2 桌面端
- CSS自定义属性主题系统
- Web Audio API 音效
- Canvas API 粒子效果

---

## 版本历史

### v0.1.3 (2026-06-14)

#### 新功能
- ✏️ **任务编辑** - 点击任务文本或铅笔图标编辑
- 🏷️ **任务分类** - 工作/学习/生活/其他
- 📝 **任务备注** - 展开查看详情
- 🔍 **搜索功能** - 按文本、分类、备注搜索
- 📦 **导出/导入** - JSON格式备份和恢复

#### Bug修复
1. Category类型移除`| string`联合类型
2. 移除TaskItem中多余的escapeHtml调用（双重转义）
3. AudioContext添加resume()调用
4. localStorage.setItem添加try/catch错误处理
5. 移除useAchievements中的死代码
6. 清除已完成操作添加确认对话框
7. CATEGORY_LABELS提取到共享constants.ts

#### 测试
- 配置Vitest测试框架
- 编写38个单元测试用例
- 覆盖工具函数、hooks、组件

#### 文档
- 添加测试指南 docs/testing-guide.md

---

### v0.1.2 (2026-06-12)

#### 新功能
- 📅 **日历时间选择器** - 月视图日历 + 自定义时间滚动选择器
- 🎨 **青绿色主题** - 自定义时间选择器匹配应用整体风格

#### UI改进
- 替换原生时间输入为自定义滚动选择器
- 修复日历网格对齐问题
- 修复删除按钮图标缺失
- 优化优先级标签颜色
- 增强任务卡片阴影效果

---

### v0.1.1 (2026-06-11)

#### Bug修复
- 修复中文输入法下Enter键误提交问题

---

### v0.1.0 (2026-06-11)

#### 初始版本
- 深色/浅色模式切换
- Canvas粒子撒花效果
- Web Audio API音效合成
- HTML5拖拽排序
- 成就系统
- 统计面板 + SVG进度环
- Tauri桌面应用打包

---

## 架构设计

### 组件结构
```
App.tsx (根组件)
├── AchievementDrawer (成就面板)
├── Toast (通知)
├── ConfettiCanvas (粒子效果)
├── Header (标题栏)
├── SearchBox (搜索)
├── TaskInput (任务输入)
│   └── TimePicker (时间选择)
├── PrioritySelector (优先级)
├── FilterTabs (过滤器)
├── TaskList (任务列表)
│   └── TaskItem (任务项)
└── Footer (统计)
    └── ProgressRing (进度环)
```

### 数据流
```
App.tsx 编排多个hooks
    ↓ props传递
组件接收状态和处理函数
    ↓ 用户交互
调用hook方法更新状态
    ↓ 状态更新
localStorage持久化
```

### Hooks职责
| Hook | 职责 |
|------|------|
| useTodos | 任务CRUD、过滤、搜索、导入导出 |
| useTheme | 深色/浅色模式切换 |
| useSound | Web Audio音效合成 |
| useAchievements | 成就解锁、连续天数 |
| useDragDrop | 拖拽排序状态 |
| useConfetti | Canvas粒子效果 |

---

## 测试覆盖

| 模块 | 测试文件 | 用例数 |
|------|----------|--------|
| escapeHtml | escapeHtml.test.ts | 8 |
| useTodos | useTodos.test.ts | 12 |
| useTheme | useTheme.test.ts | 5 |
| useAchievements | useAchievements.test.ts | 7 |
| EmptyState | EmptyState.test.tsx | 3 |
| ProgressRing | ProgressRing.test.tsx | 3 |
| **总计** | | **38** |

---

## 开发命令

```bash
# 开发
npm run dev

# 构建
npm run build

# 测试
npm test
npm run test:watch
npm run test:coverage

# 桌面应用
npm run tauri dev
npm run tauri build
```

---

## 文件结构

```
to do list/
├── src/
│   ├── App.tsx
│   ├── types.ts
│   ├── constants.ts
│   ├── hooks/
│   │   ├── useTodos.ts
│   │   ├── useTheme.ts
│   │   ├── useSound.ts
│   │   ├── useAchievements.ts
│   │   └── useDragDrop.ts
│   ├── components/
│   │   ├── Header.tsx
│   │   ├── TaskInput.tsx
│   │   ├── TaskItem.tsx
│   │   ├── TimePicker.tsx
│   │   └── ... (14个组件)
│   ├── styles/
│   │   └── ... (16个CSS文件)
│   └── utils/
│       └── escapeHtml.ts
├── src-tauri/          # Tauri桌面壳
├── docs/               # 文档
│   ├── testing-guide.md
│   └── compose/plans/  # 实现计划
└── package.json
```

---

## GitHub Releases

- v0.1.3: https://github.com/Yanqs2000/TodoList/releases/tag/v0.1.3
- v0.1.2: https://github.com/Yanqs2000/TodoList/releases/tag/v0.1.2
- v0.1.1: https://github.com/Yanqs2000/TodoList/releases/tag/v0.1.1
- v0.1.0: https://github.com/Yanqs2000/TodoList/releases/tag/v0.1.0
