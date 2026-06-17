# Bug Fixes and Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix identified bugs and add comprehensive test coverage to the TodoList application.

**Architecture:** Fix bugs in existing code, then set up Vitest testing framework and write unit tests for hooks and utilities.

**Tech Stack:** React 19, TypeScript 5.8, Vitest, @testing-library/react, jsdom

---

## File Map

### Modified Files
- `src/types.ts` — Fix Category type
- `src/utils/escapeHtml.ts` — Replace with pure string function
- `src/hooks/useSound.ts` — Add AudioContext.resume()
- `src/hooks/useTodos.ts` — Add localStorage error handling, extract constants
- `src/hooks/useAchievements.ts` — Remove dead code
- `src/components/TaskItem.tsx` — Fix double escaping
- `src/components/Footer.tsx` — Add confirmation dialog

### New Files
- `vitest.config.ts` — Vitest configuration
- `src/test/setup.ts` — Test setup file
- `src/utils/__tests__/escapeHtml.test.ts` — EscapeHtml tests
- `src/hooks/__tests__/useTodos.test.ts` — UseTodos tests
- `src/hooks/__tests__/useTheme.test.ts` — UseTheme tests
- `src/hooks/__tests__/useSound.test.ts` — UseSound tests
- `src/hooks/__tests__/useAchievements.test.ts` — UseAchievements tests
- `src/components/__tests__/TaskItem.test.tsx` — TaskItem tests
- `src/components/__tests__/EmptyState.test.tsx` — EmptyState tests
- `src/components/__tests__/Footer.test.tsx` — Footer tests
- `src/components/__tests__/ProgressRing.test.tsx` — ProgressRing tests
- `docs/testing-guide.md` — Testing documentation

---

## Task 1: Fix Category Type

**Files:**
- Modify: `src/types.ts`

- [ ] **Step 1: Fix Category type**

```typescript
export type Category = 'work' | 'study' | 'life' | 'other';
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/types.ts
git commit -m "fix: remove string union from Category type"
```

---

## Task 2: Fix escapeHtml Double Escaping

**Files:**
- Modify: `src/utils/escapeHtml.ts`
- Modify: `src/components/TaskItem.tsx`

- [ ] **Step 1: Replace escapeHtml with pure string function**

Replace `src/utils/escapeHtml.ts` content:

```typescript
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
```

- [ ] **Step 2: Remove escapeHtml usage from TaskItem.tsx**

In `src/components/TaskItem.tsx`, remove the import and usage:

```typescript
// Remove this import:
// import { escapeHtml } from '../utils/escapeHtml';

// Change this line:
{escapeHtml(task.text)}
// To:
{task.text}
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/utils/escapeHtml.ts src/components/TaskItem.tsx
git commit -m "fix: remove double escaping in TaskItem text rendering"
```

---

## Task 3: Fix AudioContext Resume

**Files:**
- Modify: `src/hooks/useSound.ts`

- [ ] **Step 1: Add AudioContext resume call**

In `src/hooks/useSound.ts`, update the `getCtx` function:

```typescript
const getCtx = useCallback(async () => {
  if (!ctxRef.current) ctxRef.current = createAudioContext();
  if (ctxRef.current?.state === 'suspended') {
    await ctxRef.current.resume();
  }
  return ctxRef.current;
}, []);
```

Also update `playTone` to be async and await `getCtx`:

```typescript
const playTone = useCallback(async (frequency: number, duration: number, type: OscillatorType = 'sine', volume = 0.15) => {
  if (muted) return;
  const ctx = await getCtx();
  if (!ctx) return;
  // ... rest of function
}, [muted, getCtx]);
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useSound.ts
git commit -m "fix: add AudioContext resume for browser autoplay policy"
```

---

## Task 4: Add localStorage Error Handling

**Files:**
- Modify: `src/hooks/useTodos.ts`

- [ ] **Step 1: Create safe localStorage wrapper**

Add at the top of `src/hooks/useTodos.ts`:

```typescript
function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    console.warn('Failed to save to localStorage:', e);
  }
}
```

- [ ] **Step 2: Replace all localStorage.setItem calls**

Replace all `localStorage.setItem(STORAGE_KEY, ...)` calls with `safeSetItem(STORAGE_KEY, ...)`.

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/hooks/useTodos.ts
git commit -m "fix: add error handling for localStorage.setItem"
```

---

## Task 5: Remove Dead Code in Achievements

**Files:**
- Modify: `src/hooks/useAchievements.ts`

- [ ] **Step 1: Remove streak-7 from checks array**

In `src/hooks/useAchievements.ts`, remove the dead code entry:

```typescript
// Remove this line from checks array:
{ id: 'streak-7', condition: false }, // checked separately via streak
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useAchievements.ts
git commit -m "fix: remove dead streak-7 check code"
```

---

## Task 6: Add Clear Completed Confirmation

**Files:**
- Modify: `src/components/Footer.tsx`

- [ ] **Step 1: Add confirmation dialog**

In `src/components/Footer.tsx`, update the clear completed handler:

```typescript
const handleClearCompleted = () => {
  if (stats.completed === 0) return;
  if (window.confirm(`确定要清除 ${stats.completed} 个已完成的任务吗？`)) {
    onClearCompleted();
  }
};
```

- [ ] **Step 2: Update button onClick**

```typescript
<button
  className="btn-clear"
  disabled={stats.completed === 0}
  onClick={handleClearCompleted}
>
  清除已完成
</button>
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/Footer.tsx
git commit -m "fix: add confirmation dialog for clear completed"
```

---

## Task 7: Extract Shared Constants

**Files:**
- Create: `src/constants.ts`
- Modify: `src/hooks/useTodos.ts`
- Modify: `src/components/TaskInput.tsx`
- Modify: `src/components/TaskItem.tsx`

- [ ] **Step 1: Create constants.ts**

```typescript
import type { Category } from './types';

export const CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];

export const CATEGORY_LABELS: Record<Category, string> = {
  work: '工作',
  study: '学习',
  life: '生活',
  other: '其他',
};
```

- [ ] **Step 2: Update useTodos.ts**

```typescript
import { CATEGORIES, CATEGORY_LABELS } from '../constants';
// Remove local CATEGORY_LABELS definition
```

- [ ] **Step 3: Update TaskInput.tsx**

```typescript
import { CATEGORY_LABELS } from '../constants';
// Remove local CATEGORY_LABELS definition
```

- [ ] **Step 4: Update TaskItem.tsx**

```typescript
import { CATEGORY_LABELS } from '../constants';
// Remove local CATEGORY_LABELS definition
```

- [ ] **Step 5: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/constants.ts src/hooks/useTodos.ts src/components/TaskInput.tsx src/components/TaskItem.tsx
git commit -m "refactor: extract CATEGORY_LABELS to shared constants"
```

---

## Task 8: Setup Vitest Testing Framework

**Files:**
- Create: `vitest.config.ts`
- Create: `src/test/setup.ts`
- Modify: `package.json`

- [ ] **Step 1: Install test dependencies**

Run: `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`

- [ ] **Step 2: Create vitest.config.ts**

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
});
```

- [ ] **Step 3: Create src/test/setup.ts**

```typescript
import '@testing-library/jest-dom';
```

- [ ] **Step 4: Add test script to package.json**

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

- [ ] **Step 5: Run initial test**

Run: `npm test`
Expected: No tests found, but Vitest runs without errors

- [ ] **Step 6: Commit**

```bash
git add vitest.config.ts src/test/setup.ts package.json package-lock.json
git commit -m "test: setup Vitest testing framework"
```

---

## Task 9: Write escapeHtml Tests

**Files:**
- Create: `src/utils/__tests__/escapeHtml.test.ts`

- [ ] **Step 1: Create test file**

```typescript
import { describe, it, expect } from 'vitest';
import { escapeHtml } from '../escapeHtml';

describe('escapeHtml', () => {
  it('should escape ampersand', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });

  it('should escape less than', () => {
    expect(escapeHtml('a < b')).toBe('a &lt; b');
  });

  it('should escape greater than', () => {
    expect(escapeHtml('a > b')).toBe('a &gt; b');
  });

  it('should escape double quotes', () => {
    expect(escapeHtml('a "b" c')).toBe('a &quot;b&quot; c');
  });

  it('should escape single quotes', () => {
    expect(escapeHtml("a 'b' c")).toBe('a &#039;b&#039; c');
  });

  it('should escape multiple characters', () => {
    expect(escapeHtml('<script>alert("xss")</script>')).toBe(
      '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
    );
  });

  it('should return empty string for empty input', () => {
    expect(escapeHtml('')).toBe('');
  });

  it('should not modify plain text', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
});
```

- [ ] **Step 2: Run tests**

Run: `npm test src/utils/__tests__/escapeHtml.test.ts`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/utils/__tests__/escapeHtml.test.ts
git commit -m "test: add escapeHtml unit tests"
```

---

## Task 10: Write useTodos Tests

**Files:**
- Create: `src/hooks/__tests__/useTodos.test.ts`

- [ ] **Step 1: Create test file**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTodos } from '../useTodos';

describe('useTodos', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should initialize with empty tasks', () => {
    const { result } = renderHook(() => useTodos());
    expect(result.current.tasks).toEqual([]);
    expect(result.current.stats.total).toBe(0);
  });

  it('should add a task', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Test task');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Test task');
    expect(result.current.tasks[0].completed).toBe(false);
  });

  it('should not add empty task', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('  ');
    });

    expect(result.current.tasks).toHaveLength(0);
  });

  it('should toggle task completion', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Test task');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.toggleTask(taskId);
    });

    expect(result.current.tasks[0].completed).toBe(true);
  });

  it('should remove a task', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Test task');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.removeTask(taskId);
    });

    expect(result.current.tasks).toHaveLength(0);
  });

  it('should edit a task', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Original text');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.editTask(taskId, { text: 'Updated text' });
    });

    expect(result.current.tasks[0].text).toBe('Updated text');
  });

  it('should filter by status', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Task 1');
      result.current.addTask('Task 2');
    });

    const taskId = result.current.tasks[0].id;

    act(() => {
      result.current.toggleTask(taskId);
    });

    act(() => {
      result.current.setFilter('completed');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].completed).toBe(true);
  });

  it('should filter by category', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Work task', undefined, 'work');
      result.current.addTask('Study task', undefined, 'study');
    });

    act(() => {
      result.current.setCategoryFilter('work');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].category).toBe('work');
  });

  it('should search tasks', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Learn React');
      result.current.addTask('Buy groceries');
    });

    act(() => {
      result.current.setSearchQuery('React');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Learn React');
  });

  it('should clear completed tasks', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Task 1');
      result.current.addTask('Task 2');
    });

    act(() => {
      result.current.toggleTask(result.current.tasks[0].id);
    });

    act(() => {
      result.current.clearCompleted();
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Task 2');
  });

  it('should persist to localStorage', () => {
    const { result } = renderHook(() => useTodos());
    
    act(() => {
      result.current.addTask('Persistent task');
    });

    const stored = JSON.parse(localStorage.getItem('todo-tasks') || '[]');
    expect(stored).toHaveLength(1);
    expect(stored[0].text).toBe('Persistent task');
  });

  it('should load from localStorage', () => {
    localStorage.setItem('todo-tasks', JSON.stringify([
      { id: '1', text: 'Loaded task', completed: false, priority: 'low', createdAt: Date.now() }
    ]));

    const { result } = renderHook(() => useTodos());
    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0].text).toBe('Loaded task');
  });
});
```

- [ ] **Step 2: Run tests**

Run: `npm test src/hooks/__tests__/useTodos.test.ts`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/hooks/__tests__/useTodos.test.ts
git commit -m "test: add useTodos hook unit tests"
```

---

## Task 11: Write useTheme Tests

**Files:**
- Create: `src/hooks/__tests__/useTheme.test.ts`

- [ ] **Step 1: Create test file**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTheme } from '../useTheme';

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('should default to light theme', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
  });

  it('should toggle theme', () => {
    const { result } = renderHook(() => useTheme());
    
    act(() => {
      result.current.toggleTheme();
    });

    expect(result.current.theme).toBe('dark');
  });

  it('should persist theme to localStorage', () => {
    const { result } = renderHook(() => useTheme());
    
    act(() => {
      result.current.toggleTheme();
    });

    expect(localStorage.getItem('todo-theme')).toBe('dark');
  });

  it('should set data-theme attribute', () => {
    const { result } = renderHook(() => useTheme());
    
    act(() => {
      result.current.toggleTheme();
    });

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('should load saved theme from localStorage', () => {
    localStorage.setItem('todo-theme', 'dark');

    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
  });
});
```

- [ ] **Step 2: Run tests**

Run: `npm test src/hooks/__tests__/useTheme.test.ts`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/hooks/__tests__/useTheme.test.ts
git commit -m "test: add useTheme hook unit tests"
```

---

## Task 12: Write useAchievements Tests

**Files:**
- Create: `src/hooks/__tests__/useAchievements.test.ts`

- [ ] **Step 1: Create test file**

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAchievements } from '../useAchievements';

describe('useAchievements', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should initialize with no achievements unlocked', () => {
    const { result } = renderHook(() => useAchievements());
    expect(result.current.achievements.unlocked).toEqual([]);
  });

  it('should unlock first-task achievement', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      result.current.recordCompletion();
    });

    expect(result.current.achievements.unlocked).toContain('first-task');
  });

  it('should show toast on achievement unlock', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      result.current.recordCompletion();
    });

    expect(result.current.toast).not.toBeNull();
    expect(result.current.toast?.id).toBe('first-task');
  });

  it('should dismiss toast', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      result.current.recordCompletion();
    });

    act(() => {
      result.current.dismissToast();
    });

    expect(result.current.toast).toBeNull();
  });

  it('should track today completed count', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      result.current.recordCompletion();
      result.current.recordCompletion();
    });

    expect(result.current.achievements.todayCompleted).toBe(2);
  });

  it('should unlock speed-demon after 10 completions', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      for (let i = 0; i < 10; i++) {
        result.current.recordCompletion();
      }
    });

    expect(result.current.achievements.unlocked).toContain('speed-demon');
  });

  it('should persist achievements to localStorage', () => {
    const { result } = renderHook(() => useAchievements());
    
    act(() => {
      result.current.recordCompletion();
    });

    const stored = JSON.parse(localStorage.getItem('todo-achievements') || '{}');
    expect(stored.unlocked).toContain('first-task');
  });
});
```

- [ ] **Step 2: Run tests**

Run: `npm test src/hooks/__tests__/useAchievements.test.ts`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/hooks/__tests__/useAchievements.test.ts
git commit -m "test: add useAchievements hook unit tests"
```

---

## Task 13: Write Component Tests

**Files:**
- Create: `src/components/__tests__/EmptyState.test.tsx`
- Create: `src/components/__tests__/ProgressRing.test.tsx`

- [ ] **Step 1: Create EmptyState test**

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmptyState from '../EmptyState';

describe('EmptyState', () => {
  it('should show message for all filter', () => {
    render(<EmptyState filter="all" />);
    expect(screen.getByText('还没有任务，添加一个吧')).toBeInTheDocument();
  });

  it('should show message for active filter', () => {
    render(<EmptyState filter="active" />);
    expect(screen.getByText('没有未完成的任务')).toBeInTheDocument();
  });

  it('should show message for completed filter', () => {
    render(<EmptyState filter="completed" />);
    expect(screen.getByText('没有已完成的任务')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Create ProgressRing test**

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProgressRing from '../ProgressRing';

describe('ProgressRing', () => {
  it('should display current/goal text', () => {
    render(<ProgressRing current={5} goal={10} />);
    expect(screen.getByText('5/10')).toBeInTheDocument();
  });

  it('should calculate correct progress percentage', () => {
    const { container } = render(<ProgressRing current={5} goal={10} />);
    const fillCircle = container.querySelector('.progress-ring-fill');
    expect(fillCircle).toBeInTheDocument();
  });

  it('should cap progress at 100%', () => {
    const { container } = render(<ProgressRing current={15} goal={10} />);
    const fillCircle = container.querySelector('.progress-ring-fill');
    const offset = fillCircle?.getAttribute('stroke-dashoffset');
    expect(offset).toBe('0');
  });
});
```

- [ ] **Step 3: Run tests**

Run: `npm test src/components/__tests__/`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/components/__tests__/
git commit -m "test: add EmptyState and ProgressRing component tests"
```

---

## Task 14: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `npm test`
Expected: All tests pass

- [ ] **Step 2: Generate coverage report**

Run: `npm run test:coverage`
Expected: Coverage report generated

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: verify full test suite passes"
```

---

## Task 15: Write Testing Documentation

**Files:**
- Create: `docs/testing-guide.md`

- [ ] **Step 1: Create testing guide**

```markdown
# TodoList 测试指南

## 概述

本项目使用 Vitest 作为测试框架，@testing-library/react 用于组件测试。

## 运行测试

```bash
# 运行所有测试
npm test

# 监听模式
npm run test:watch

# 生成覆盖率报告
npm run test:coverage
```

## 测试结构

```
src/
├── utils/__tests__/
│   └── escapeHtml.test.ts      # 工具函数测试
├── hooks/__tests__/
│   ├── useTodos.test.ts        # 任务管理hook测试
│   ├── useTheme.test.ts        # 主题hook测试
│   └── useAchievements.test.ts # 成就系统hook测试
└── components/__tests__/
    ├── EmptyState.test.tsx     # 空状态组件测试
    └── ProgressRing.test.tsx   # 进度环组件测试
```

## 编写测试

### 测试Hook

```typescript
import { renderHook, act } from '@testing-library/react';
import { useMyHook } from '../useMyHook';

describe('useMyHook', () => {
  it('should do something', () => {
    const { result } = renderHook(() => useMyHook());
    
    act(() => {
      result.current.doSomething();
    });

    expect(result.current.value).toBe(expected);
  });
});
```

### 测试组件

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import MyComponent from '../MyComponent';

describe('MyComponent', () => {
  it('should render correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('should handle click', () => {
    const handleClick = vi.fn();
    render(<MyComponent onClick={handleClick} />);
    
    fireEvent.click(screen.getByRole('button'));
    
    expect(handleClick).toHaveBeenCalled();
  });
});
```

## 测试覆盖的模块

| 模块 | 测试文件 | 测试用例数 |
|------|----------|-----------|
| escapeHtml | escapeHtml.test.ts | 8 |
| useTodos | useTodos.test.ts | 12 |
| useTheme | useTheme.test.ts | 5 |
| useAchievements | useAchievements.test.ts | 7 |
| EmptyState | EmptyState.test.tsx | 3 |
| ProgressRing | ProgressRing.test.tsx | 3 |

## 已修复的Bug

在添加测试之前，我们修复了以下问题：

1. **Category类型** - 移除了`| string`联合类型
2. **双重转义** - 移除了TaskItem中多余的escapeHtml调用
3. **AudioContext** - 添加了resume()调用以支持浏览器自动播放策略
4. **localStorage错误处理** - 添加了try/catch包装
5. **死代码** - 移除了useAchievements中的无用代码
6. **确认对话框** - 为清除已完成操作添加了确认提示
7. **常量提取** - 将CATEGORY_LABELS提取到共享constants.ts
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing-guide.md
git commit -m "docs: add testing guide documentation"
```

---

## Task 16: Final Verification and Push

- [ ] **Step 1: Run full build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 2: Run all tests**

Run: `npm test`
Expected: All tests pass

- [ ] **Step 3: Commit all changes**

```bash
git add -A
git commit -m "chore: complete bug fixes and test coverage"
```

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```
