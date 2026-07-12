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

**总计: 38 个测试用例**

## 已修复的Bug

在添加测试之前，我们修复了以下问题：

1. **Category类型** - 移除了`| string`联合类型
2. **双重转义** - 移除了TaskItem中多余的escapeHtml调用
3. **AudioContext** - 添加了resume()调用以支持浏览器自动播放策略
4. **localStorage错误处理** - 添加了try/catch包装
5. **死代码** - 移除了useAchievements中的无用代码
6. **确认对话框** - 为清除已完成操作添加了确认提示
7. **常量提取** - 将CATEGORY_LABELS提取到共享constants.ts
