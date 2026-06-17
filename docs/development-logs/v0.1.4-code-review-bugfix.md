# 代码审查与 Bug 修复记录 — 2026-06-17

本文档记录了一次系统性代码审查发现的问题、对应的修复方案、新增测试，以及随附的工程改进。

## 概览

| 维度 | 数据 |
| --- | --- |
| 审查范围 | 全部 `src/`（hooks、components、utils、styles） |
| 构建 | ✅ `npm run build` 通过 |
| 测试 | ✅ 48 个测试通过（新增 18 个） |
| 修复项 | 13 项（严重 3 / 中等 5 / 较小 5） |

---

## 🔴 严重问题（影响功能正确性 / 数据安全）

### 1. 时间排序覆盖手动拖拽（已修复）

**位置**：`src/hooks/useTodos.ts:151-171`（旧版）

**问题**：`filteredTasks` 末尾无条件按 `time.start` 排序，导致用户拖拽后 underlying 数组变化，UI 仍按时间显示——拖拽"看起来无效"。

**修复**：
- 新增 `sortMode: 'manual' | 'time'` 状态，默认 `manual`
- `manual` 模式不排序，保留拖拽顺序
- `reorderTasks` 调用后自动切回 `manual`，确保用户拖拽意图被尊重
- `TaskList` 顶部新增「手动排序 / 按时间排序」切换按钮

**新增测试**：`useTodos-import-sort.test.ts`

---

### 2. 导入 JSON 无 schema 校验，可写入垃圾数据（已修复）

**位置**：`src/hooks/useTodos.ts:119-143`（旧版）

**问题**：`importTasks` 仅检查 `data.tasks` 是数组，不校验元素结构。导入 `{ completed: 'sure', priority: 'evil' }` 之类的垃圾数据后，应用进入不一致状态（truthy 当成完成、`priority-evil` CSS class 不存在）。

**修复**：
- 新建 `src/utils/validateTodo.ts`，导出 `validateTodo` / `validateTodoArray`
- 逐字段校验 `id`（非空字符串）、`text`（字符串，≤500 字符）、`completed`（boolean）、`priority`（枚举）、`createdAt`（数字）、可选的 `category` / `time` / `notes`
- `time.start` / `time.end` 必须匹配 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$`
- `importTasks` 返回 `{ added, skipped }`，调用方据此显示更具体的提示
- 启动时 `loadInitialTasks` 也走校验，防止手工篡改的 localStorage 让应用崩溃

**新增测试**：`validateTodo.test.ts`（10 个用例）、`useTodos-import-sort.test.ts`（5 个用例）

---

### 3. `generateId` 在同一毫秒内可能撞 id（已修复）

**位置**：`src/hooks/useTodos.ts:15-17`（旧版）

**问题**：`Date.now().toString(36) + Math.random().toString(36).slice(2, 6)` 的随机段仅 4 字符 base36（约 60 万种），批量粘贴/导入时小概率重复。撞 id 后导入去重逻辑会误判"已存在"而漏导。

**修复**：
- 新建 `src/utils/id.ts`，优先使用 `crypto.randomUUID()`（浏览器原生，UUID v4，碰撞概率 ≈ 0）
- 兼容回退：`Date.now().toString(36) + 两次 10 字符 base36`

**新增测试**：`id.test.ts`（5000 次调用无重复）

---

## 🟡 中等问题

### 4. 用 `alert()` 阻塞 UI，桌面端体验差（已修复）

**位置**：`src/App.tsx:34, 36`

**修复**：新建 `InfoToast` 组件（绿/红两色，2.5 秒自动消失，可点击关闭），替换 `alert()`。`importTasks` 返回 `{added, skipped}`，提示更精确：「已导入 X 个任务，跳过 Y 个无效项」。

---

### 5. 删除动画的双重计时器 + 二次调用风险（已修复）

**位置**：`src/components/TaskItem.tsx:83-95`（旧版）

**问题**：`animationend` + `setTimeout(200)` 双保险，但 `setTimeout` 没清，`animationend` 触发后仍可能再调一次 `removeRef.current`。原代码靠 `filter` 幂等掩盖，但逻辑脆弱。

**修复**：
- 用 `removeDoneRef` 标记一次性执行
- `onEnd` 先清 `setTimeout`，再调 `onDelete`
- 组件卸载时 `useEffect` cleanup 清理 `removeTimerRef`

---

### 6. `useAchievements` toast 计时器无 cleanup + `clearTimeout(0)` 异味（已修复）

**位置**：`src/hooks/useAchievements.ts:27, 69-70`（旧版）

**修复**：
- `toastTimerRef` 类型改为 `number | null`，初始 `null`
- 新增 `useEffect` 卸载时清理计时器
- `dismissToast` 也清理计时器

---

### 7. `localStorage.setItem` 异常未捕获（已修复）

**位置**：`useAchievements.ts:81`、`useTheme.ts:17`、`useSound.ts:66`

**问题**：`useTodos` 用了 `safeSetItem`，其它三个 hook 没用。隐私模式 / 配额满会抛 `QuotaExceededError`，中断 React 渲染。

**修复**：抽出 `src/utils/storage.ts`（`safeSetItem` + `safeGetItem`），三个 hook 统一改用。

---

### 8. `getInitialState` 解析 localStorage 不校验字段（已修复）

**位置**：`src/hooks/useAchievements.ts:16-22`（旧版）

**修复**：逐字段校验 `unlocked`（数组且元素为字符串）、`streakDays` / `todayCompleted`（数字）、`lastActiveDate` / `todayDate`（字符串），缺失字段用 fallback。

---

## 🟢 较小问题

### 9. `escapeHtml` 死代码（已删除）

`src/utils/escapeHtml.ts` 全局 grep 显示无调用方（React JSX 自带转义）。连同测试一并删除。

---

### 10. dragover 期间频繁 setState（已优化）

**位置**：`src/hooks/useDragDrop.ts`

**修复**：用 `lastOverIdRef` 比较，id 未变时不调 `setOverId`，避免每次 mousemove 都触发 re-render。`handleDragLeave` 用 `relatedTarget` 检查避免子元素误触发。

---

### 11. TimePicker 缺少键盘可达性（已修复）

**位置**：`src/components/TimePicker.tsx`

**修复**：监听 `keydown`，按 `Esc` 关闭弹窗。

---

### 12. 单条删除无确认（已修复）

**位置**：`src/components/TaskItem.tsx`

**修复**：`handleDelete` 调 `window.confirm('确定要删除任务「X」吗？')`。

---

### 13. 可访问性增强（已修复）

- `TaskItem` checkbox 从 `<div role="checkbox">` 改为原生 `<input type="checkbox">`，恢复表单语义
- `Toast` 加 `role="alert" aria-live="assertive"`
- `App` 顶部新增 `role="status" aria-live="polite"` 的 `sr-only` 区域，屏幕阅读器能读到成就解锁和导入结果
- `.sr-only` CSS class（视觉隐藏但可读屏）

---

## 新增 / 修改文件清单

**新增**：
- `src/utils/storage.ts` — 安全 localStorage 封装
- `src/utils/id.ts` — `generateId`（优先 `crypto.randomUUID`）
- `src/utils/validateTodo.ts` — Todo schema 校验
- `src/components/InfoToast.tsx` + `src/styles/InfoToast.css`
- `src/utils/__tests__/validateTodo.test.ts`（10 个用例）
- `src/utils/__tests__/id.test.ts`（3 个用例）
- `src/hooks/__tests__/useTodos-import-sort.test.ts`（5 个用例）

**修改**：
- `src/App.tsx` — 用 InfoToast 替代 alert，加 sr-only live region
- `src/hooks/useTodos.ts` — sortMode、schema 校验、safeSetItem、新 ID 生成
- `src/hooks/useAchievements.ts` — cleanup、字段校验、safeSetItem
- `src/hooks/useTheme.ts` — safeSetItem / safeGetItem
- `src/hooks/useSound.ts` — safeSetItem / safeGetItem
- `src/hooks/useDragDrop.ts` — dragover 节流、dragLeave 修复
- `src/components/TaskItem.tsx` — 原生 checkbox、删除确认、动画 cleanup
- `src/components/TaskList.tsx` — 排序模式切换按钮
- `src/components/Toast.tsx` — role/aria-live
- `src/components/TimePicker.tsx` — Esc 关闭
- `src/styles/TaskItem.css` — input[type=checkbox] 样式
- `src/styles/TaskList.css` — sort-bar 样式

**删除**：
- `src/utils/escapeHtml.ts` + 测试（死代码）

---

## 测试统计

| 项 | 数量 |
| --- | --- |
| 测试文件 | 8 |
| 测试用例 | 48（修复前 38，删除 escapeHtml 的 8 个，新增 18 个） |
| 通过 | 48 ✅ |
| TypeScript 严格模式 | ✅ |
| Vite 构建 | ✅ 227 KB / gzip 71 KB |

---

## 后续建议（未在本轮修复）

1. **ConfettiCanvas 在窗口 resize 时不更新尺寸**——粒子坐标基于旧 width/height。
2. **AchievementDrawer 没有 focus trap**——Tab 会跑到背景元素。
3. **没有撤销机制**——删除/清除已完成不可撤销，可考虑加 undo stack。
4. **没有暗色模式下 priority-tag 颜色适配**——浅色背景在深色主题下偏亮。
