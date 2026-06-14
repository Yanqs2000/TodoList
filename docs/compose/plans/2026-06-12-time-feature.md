# Time Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add time point and time range support to task creation, with popover time picker and time-sorted display.

**Architecture:** Extend Todo type with optional time field. Add TimePicker popover component. Modify TaskInput to include time selection. Update TaskItem to display time tags. Adjust useTodos sorting to prioritize timed tasks.

**Tech Stack:** React 19, TypeScript 5.8, CSS custom properties, native `<input type="time">`

---

## File Map

### New Files
- `src/components/TimePicker.tsx` — popover time picker component
- `src/styles/TimePicker.css` — time picker styles

### Modified Files
- `src/types.ts` — add TimeField type to Todo
- `src/hooks/useTodos.ts` — add time parameter to addTask, sort by time
- `src/components/TaskInput.tsx` — add clock icon, integrate TimePicker
- `src/components/TaskItem.tsx` — display time tag
- `src/styles/TaskItem.css` — time tag styles

---

## Task 1: Data Model Update

**Covers:** S1 (data model)

**Files:**
- Modify: `src/types.ts`

- [ ] **Step 1: Add TimeField type to Todo**

```typescript
export type Priority = 'low' | 'medium' | 'high';
export type FilterType = 'all' | 'active' | 'completed';

export interface TimeField {
  start: string;  // "14:30"
  end?: string;   // "15:30" (optional, for time range)
}

export interface Todo {
  id: string;
  text: string;
  completed: boolean;
  priority: Priority;
  createdAt: number;
  time?: TimeField;
}

export interface AchievementDef {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export interface AchievementState {
  unlocked: string[];
  streakDays: number;
  lastActiveDate: string;
  todayCompleted: number;
  todayDate: string;
}
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/types.ts
git commit -m "feat: add TimeField type to Todo"
```

---

## Task 2: useTodos Hook Update

**Covers:** S2 (addTask), S4 (sorting)

**Files:**
- Modify: `src/hooks/useTodos.ts`

- [ ] **Step 1: Update addTask to accept time parameter**

Replace `addTask` function (lines 23-40):

```typescript
import { useState, useCallback } from 'react';
import { Todo, TimeField, Priority, FilterType } from '../types';

// ... existing code ...

const addTask = useCallback((text: string, time?: TimeField) => {
  const trimmed = text.trim();
  if (!trimmed) return;

  const newTask: Todo = {
    id: generateId(),
    text: trimmed,
    completed: false,
    priority,
    createdAt: Date.now(),
    time,
  };

  setTasks(prev => {
    const updated = [newTask, ...prev];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  });
}, [priority]);
```

- [ ] **Step 2: Add time-based sorting to filteredTasks**

Replace `filteredTasks` logic (lines 87-91):

```typescript
const filteredTasks = tasks.filter(t => {
  if (filter === 'active') return !t.completed;
  if (filter === 'completed') return t.completed;
  return true;
}).sort((a, b) => {
  // Tasks with time go first, sorted by start time
  if (a.time && b.time) return a.time.start.localeCompare(b.time.start);
  if (a.time && !b.time) return -1;
  if (!a.time && b.time) return 1;
  return 0;
});
```

- [ ] **Step 3: Update return type**

Update the return object to include the new signature:

```typescript
return {
  tasks: filteredTasks,
  allTasks: tasks,
  filter,
  priority,
  stats,
  addTask,  // now accepts (text: string, time?: TimeField)
  toggleTask,
  removeTask,
  clearCompleted,
  reorderTasks,
  setFilter,
  setPriority,
};
```

- [ ] **Step 4: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useTodos.ts
git commit -m "feat: add time support to useTodos hook"
```

---

## Task 3: TimePicker Component

**Covers:** S3 (UI)

**Files:**
- Create: `src/components/TimePicker.tsx`
- Create: `src/styles/TimePicker.css`

- [ ] **Step 1: Create TimePicker component**

```tsx
import { useState, useRef, useEffect } from 'react';
import type { TimeField } from '../types';
import '../styles/TimePicker.css';

interface TimePickerProps {
  time?: TimeField;
  onTimeChange: (time: TimeField | undefined) => void;
  onClose: () => void;
}

function TimePicker({ time, onTimeChange, onClose }: TimePickerProps) {
  const [mode, setMode] = useState<'point' | 'range'>(time?.end ? 'range' : 'point');
  const [start, setStart] = useState(time?.start || '');
  const [end, setEnd] = useState(time?.end || '');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleConfirm = () => {
    if (start) {
      onTimeChange({ start, end: mode === 'range' ? end : undefined });
    }
    onClose();
  };

  const handleClear = () => {
    onTimeChange(undefined);
    onClose();
  };

  return (
    <div className="time-picker" ref={ref}>
      <div className="time-picker-header">
        <button
          className={`time-mode-btn${mode === 'point' ? ' active' : ''}`}
          onClick={() => setMode('point')}
        >
          时间点
        </button>
        <button
          className={`time-mode-btn${mode === 'range' ? ' active' : ''}`}
          onClick={() => setMode('range')}
        >
          时间段
        </button>
      </div>

      <div className="time-picker-body">
        <div className="time-input-group">
          <label>开始</label>
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>

        {mode === 'range' && (
          <div className="time-input-group">
            <label>结束</label>
            <input
              type="time"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="time-picker-footer">
        <button className="time-btn-clear" onClick={handleClear}>
          清除
        </button>
        <button className="time-btn-confirm" onClick={handleConfirm} disabled={!start}>
          确认
        </button>
      </div>
    </div>
  );
}

export default TimePicker;
```

- [ ] **Step 2: Create TimePicker styles**

```css
.time-picker {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  min-width: 240px;
  animation: fadeIn 150ms ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.time-picker-header {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.time-mode-btn {
  flex: 1;
  padding: 10px;
  border: none;
  background: transparent;
  font-size: 0.8125rem;
  font-weight: 500;
  font-family: inherit;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition);
}

.time-mode-btn:hover {
  color: var(--text);
  background: var(--active-bg);
}

.time-mode-btn.active {
  color: var(--primary);
  background: var(--active-bg);
}

.time-picker-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.time-input-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.time-input-group label {
  font-size: 0.8125rem;
  color: var(--text-muted);
  min-width: 32px;
}

.time-input-group input[type="time"] {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.875rem;
  font-family: inherit;
  background: var(--bg);
  color: var(--text);
  outline: none;
  transition: border-color var(--transition);
}

.time-input-group input[type="time"]:focus {
  border-color: var(--primary);
}

.time-picker-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--border);
}

.time-btn-clear,
.time-btn-confirm {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}

.time-btn-clear {
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-muted);
}

.time-btn-clear:hover {
  border-color: var(--danger);
  color: var(--danger);
}

.time-btn-confirm {
  border: none;
  background: var(--primary);
  color: #fff;
}

.time-btn-confirm:hover {
  background: var(--primary-light);
}

.time-btn-confirm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/TimePicker.tsx src/styles/TimePicker.css
git commit -m "feat: add TimePicker popover component"
```

---

## Task 4: TaskInput Integration

**Covers:** S3 (UI), S2 (addTask)

**Files:**
- Modify: `src/components/TaskInput.tsx`

- [ ] **Step 1: Update TaskInput with TimePicker integration**

```tsx
import { useState, useRef, useEffect, useCallback } from 'react';
import type { TimeField } from '../types';
import TimePicker from './TimePicker';
import '../styles/TaskInput.css';

interface TaskInputProps {
  addTask: (text: string, time?: TimeField) => void;
}

function TaskInput({ addTask }: TaskInputProps) {
  const [value, setValue] = useState('');
  const [time, setTime] = useState<TimeField | undefined>();
  const [showTimePicker, setShowTimePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    if (value.trim()) {
      addTask(value, time);
      setValue('');
      setTime(undefined);
      inputRef.current?.focus();
    }
  }, [value, time, addTask]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isComposingRef.current) {
      handleSubmit();
    }
  };

  const handleCompositionStart = () => {
    isComposingRef.current = true;
  };

  const handleCompositionEnd = () => {
    isComposingRef.current = false;
  };

  const handleTimeChange = (newTime: TimeField | undefined) => {
    setTime(newTime);
  };

  const formatTimeDisplay = (t: TimeField): string => {
    if (t.end) {
      return `${t.start}-${t.end}`;
    }
    return t.start;
  };

  return (
    <div className="input-area">
      <div className="input-row">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={handleCompositionStart}
          onCompositionEnd={handleCompositionEnd}
          placeholder="添加新任务..."
          autoComplete="off"
        />
        <div className="input-actions">
          {time && (
            <span className="time-preview">{formatTimeDisplay(time)}</span>
          )}
          <button
            className={`icon-btn time-btn${time ? ' has-time' : ''}`}
            onClick={() => setShowTimePicker(!showTimePicker)}
            aria-label="设置时间"
            title="设置时间"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </button>
          {showTimePicker && (
            <TimePicker
              time={time}
              onTimeChange={handleTimeChange}
              onClose={() => setShowTimePicker(false)}
            />
          )}
        </div>
        <button className="btn-add" onClick={handleSubmit}>
          添加
        </button>
      </div>
    </div>
  );
}

export default TaskInput;
```

- [ ] **Step 2: Update TaskInput styles for new layout**

Replace `src/styles/TaskInput.css`:

```css
.input-area {
  margin-bottom: 16px;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-row input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  font-size: 0.9375rem;
  font-family: inherit;
  background: var(--card-bg);
  color: var(--text);
  outline: none;
  transition: border-color var(--transition);
}

.input-row input:focus {
  border-color: var(--primary);
}

.input-row input::placeholder {
  color: var(--text-light);
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}

.icon-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-bg);
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition);
  flex-shrink: 0;
}

.icon-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.icon-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.icon-btn svg {
  width: 20px;
  height: 20px;
}

.time-btn.has-time {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--active-bg);
}

.time-preview {
  font-size: 0.75rem;
  color: var(--primary);
  font-weight: 500;
  white-space: nowrap;
}

.btn-add {
  padding: 12px 20px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  font-size: 0.9375rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background var(--transition), opacity var(--transition);
  white-space: nowrap;
}

.btn-add:hover {
  background: var(--primary-light);
}

.btn-add:active {
  opacity: 0.85;
}

.btn-add:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

@media (max-width: 480px) {
  .input-row {
    flex-wrap: wrap;
  }

  .input-row input {
    min-width: 100%;
  }

  .btn-add {
    width: 100%;
    padding: 12px;
  }
}
```

- [ ] **Step 3: Update App.tsx addTask prop**

In `src/App.tsx`, the TaskInput component is used with `addTask={todoState.addTask}`. Since the signature changed from `(text: string)` to `(text: string, time?: TimeField)`, this should work without changes due to TypeScript's optional parameter compatibility. Verify:

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/TaskInput.tsx src/styles/TaskInput.css
git commit -m "feat: integrate TimePicker into TaskInput"
```

---

## Task 5: TaskItem Time Tag

**Covers:** S3 (UI display)

**Files:**
- Modify: `src/components/TaskItem.tsx`
- Modify: `src/styles/TaskItem.css`

- [ ] **Step 1: Update TaskItem to display time tag**

In `src/components/TaskItem.tsx`, add time display after the priority tag (around line 91):

```tsx
import { useState, useCallback, useRef } from 'react';
import type { Todo, Priority } from '../types';
import { escapeHtml } from '../utils/escapeHtml';
import '../styles/TaskItem.css';
import '../styles/DragDrop.css';

// ... existing code ...

const formatTimeTag = (time?: { start: string; end?: string }): string => {
  if (!time) return '';
  if (time.end) {
    return `${time.start}-${time.end}`;
  }
  return time.start;
};

// In the JSX, after the priority tag:
<span className={`priority-tag ${task.priority}`}>
  {priorityLabels[task.priority]}
</span>
{task.time && (
  <span className="time-tag">
    {formatTimeTag(task.time)}
  </span>
)}
```

- [ ] **Step 2: Add time tag styles**

In `src/styles/TaskItem.css`, add:

```css
.time-tag {
  font-size: 0.6875rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--active-bg);
  color: var(--primary);
  white-space: nowrap;
}
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/TaskItem.tsx src/styles/TaskItem.css
git commit -m "feat: display time tag on TaskItem"
```

---

## Task 6: Final Integration & Test

**Covers:** All sections

**Files:**
- Verify: all modified files

- [ ] **Step 1: Run full type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 2: Run build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual test checklist**

Run: `npm run dev`

Test:
1. Add a task with no time → no time tag shown
2. Add a task with time point (14:30) → time tag shows "14:30"
3. Add a task with time range (14:00-15:30) → time tag shows "14:00-15:30"
4. Verify timed tasks sort to top of list
5. Click clock icon → popover opens
6. Switch between time point and range modes
7. Set time, confirm → tag appears
8. Clear time → tag disappears
9. Click outside popover → closes

- [ ] **Step 4: Commit final changes**

```bash
git add -A
git commit -m "feat: complete time feature implementation"
```
