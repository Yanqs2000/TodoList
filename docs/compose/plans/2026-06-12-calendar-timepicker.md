# Calendar TimePicker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign TimePicker to include a calendar view for date selection with month navigation, supporting both time point and time range modes.

**Architecture:** Replace native `<input type="time">` with a custom calendar component showing month view, date selection, and time inputs. TimeField format changes to ISO datetime strings.

**Tech Stack:** React 19, TypeScript 5.8, CSS custom properties

---

## File Map

### Modified Files
- `src/types.ts` — Update TimeField format documentation
- `src/components/TimePicker.tsx` — Complete rewrite with calendar
- `src/styles/TimePicker.css` — Complete rewrite with calendar styles
- `src/components/TaskInput.tsx` — Update time display format
- `src/components/TaskItem.tsx` — Update time tag format

---

## Task 1: Update TimeField Documentation

**Covers:** Data model update

**Files:**
- Modify: `src/types.ts`

- [ ] **Step 1: Update TimeField comment**

In `src/types.ts`, update the TimeField interface comment to reflect ISO format:

```typescript
export interface TimeField {
  start: string;  // ISO datetime: "2026-06-15T14:30"
  end?: string;   // ISO datetime for range end: "2026-06-15T15:30"
}
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/types.ts
git commit -m "docs: update TimeField format to ISO datetime"
```

---

## Task 2: Rewrite TimePicker with Calendar

**Covers:** Calendar UI, date selection, month navigation

**Files:**
- Modify: `src/components/TimePicker.tsx`

- [ ] **Step 1: Create calendar helper functions**

Add these helpers at the top of the file (after imports):

```typescript
function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function formatDate(year: number, month: number, day: number, time: string): string {
  const m = String(month + 1).padStart(2, '0');
  const d = String(day).padStart(2, '0');
  return `${year}-${m}-${d}T${time}`;
}

function parseDateTime(iso: string): { year: number; month: number; day: number; time: string } {
  if (!iso) return { year: new Date().getFullYear(), month: new Date().getMonth(), day: new Date().getDate(), time: '09:00' };
  const [datePart, timePart] = iso.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  return { year, month: month - 1, day, time: timePart || '09:00' };
}
```

- [ ] **Step 2: Rewrite TimePicker component**

Replace the entire `TimePicker` function:

```tsx
function TimePicker({ time, onTimeChange, onClose }: TimePickerProps) {
  const [mode, setMode] = useState<'point' | 'range'>(time?.end ? 'range' : 'point');
  const startParsed = parseDateTime(time?.start || '');
  const endParsed = parseDateTime(time?.end || '');

  const [startDate, setStartDate] = useState(startParsed);
  const [endDate, setEndDate] = useState(endParsed);
  const [startTime, setStartTime] = useState(startParsed.time);
  const [endTime, setEndTime] = useState(endParsed.time);
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

  const handleDateSelect = (day: number, isEnd: boolean = false) => {
    const target = isEnd ? endDate : startDate;
    const setter = isEnd ? setEndDate : setStartDate;
    setter({ ...target, day });
  };

  const handleMonthChange = (delta: number, isEnd: boolean = false) => {
    const target = isEnd ? endDate : startDate;
    const setter = isEnd ? setEndDate : setStartDate;
    let newMonth = target.month + delta;
    let newYear = target.year;
    if (newMonth < 0) { newMonth = 11; newYear--; }
    if (newMonth > 11) { newMonth = 0; newYear++; }
    const maxDay = getDaysInMonth(newYear, newMonth);
    const newDay = Math.min(target.day, maxDay);
    setter({ year: newYear, month: newMonth, day: newDay, time: target.time });
  };

  const handleConfirm = () => {
    const start = formatDate(startDate.year, startDate.month, startDate.day, startTime);
    const end = mode === 'range'
      ? formatDate(endDate.year, endDate.month, endDate.day, endTime)
      : undefined;
    onTimeChange({ start, end });
    onClose();
  };

  const handleClear = () => {
    onTimeChange(undefined);
    onClose();
  };

  const renderCalendar = (date: typeof startDate, onDayClick: (day: number) => void, onMonthChange: (delta: number) => void) => {
    const daysInMonth = getDaysInMonth(date.year, date.month);
    const firstDay = getFirstDayOfMonth(date.year, date.month);
    const today = new Date();
    const isToday = (day: number) =>
      date.year === today.getFullYear() && date.month === today.getMonth() && day === today.getDate();
    const isSelected = (day: number) => day === date.day;

    const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
    const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

    const days: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let i = 1; i <= daysInMonth; i++) days.push(i);

    return (
      <div className="calendar">
        <div className="calendar-header">
          <button className="calendar-nav" onClick={() => onMonthChange(-1)} aria-label="上个月">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
          </button>
          <span className="calendar-title">{date.year}年 {monthNames[date.month]}</span>
          <button className="calendar-nav" onClick={() => onMonthChange(1)} aria-label="下个月">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>
        <div className="calendar-weekdays">
          {weekDays.map(d => <span key={d}>{d}</span>)}
        </div>
        <div className="calendar-days">
          {days.map((day, i) => (
            <button
              key={i}
              className={`calendar-day${day === null ? ' empty' : ''}${isToday(day!) ? ' today' : ''}${isSelected(day!) ? ' selected' : ''}`}
              onClick={() => day && onDayClick(day)}
              disabled={day === null}
            >
              {day}
            </button>
          ))}
        </div>
      </div>
    );
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
        <div className="time-section">
          <label className="time-section-label">开始时间</label>
          {renderCalendar(startDate, (day) => handleDateSelect(day, false), (delta) => handleMonthChange(delta, false))}
          <input
            type="time"
            className="time-input"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>

        {mode === 'range' && (
          <div className="time-section">
            <label className="time-section-label">结束时间</label>
            {renderCalendar(endDate, (day) => handleDateSelect(day, true), (delta) => handleMonthChange(delta, true))}
            <input
              type="time"
              className="time-input"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="time-picker-footer">
        <button className="time-btn-clear" onClick={handleClear}>
          清除
        </button>
        <button className="time-btn-confirm" onClick={handleConfirm}>
          确认
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/TimePicker.tsx
git commit -m "feat: add calendar view to TimePicker"
```

---

## Task 3: Rewrite TimePicker Styles

**Covers:** Calendar styles

**Files:**
- Modify: `src/styles/TimePicker.css`

- [ ] **Step 1: Replace TimePicker styles**

Replace the entire content of `src/styles/TimePicker.css`:

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
  width: 280px;
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
  gap: 16px;
}

.time-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.time-section-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.calendar {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.calendar-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text);
}

.calendar-nav {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition);
}

.calendar-nav:hover {
  background: var(--active-bg);
  color: var(--primary);
}

.calendar-nav svg {
  width: 16px;
  height: 16px;
}

.calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 4px;
}

.calendar-weekdays span {
  text-align: center;
  font-size: 0.6875rem;
  font-weight: 500;
  color: var(--text-light);
  padding: 4px 0;
}

.calendar-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.calendar-day {
  aspect-ratio: 1;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 0.8125rem;
  font-family: inherit;
  color: var(--text);
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
}

.calendar-day:hover:not(.empty):not(.selected) {
  background: var(--active-bg);
}

.calendar-day.empty {
  cursor: default;
}

.calendar-day.today {
  font-weight: 700;
  color: var(--primary);
}

.calendar-day.selected {
  background: var(--primary);
  color: #fff;
  font-weight: 600;
}

.time-input {
  width: 100%;
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

.time-input:focus {
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
```

- [ ] **Step 2: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/styles/TimePicker.css
git commit -m "style: add calendar styles to TimePicker"
```

---

## Task 4: Update Time Display Format

**Covers:** Display format update

**Files:**
- Modify: `src/components/TaskInput.tsx`
- Modify: `src/components/TaskItem.tsx`

- [ ] **Step 1: Update TaskInput formatTimeDisplay**

In `src/components/TaskInput.tsx`, update the `formatTimeDisplay` function:

```typescript
const formatTimeDisplay = (t: TimeField): string => {
  const formatSingle = (iso: string): string => {
    if (!iso) return '';
    const [datePart, timePart] = iso.split('T');
    const [, month, day] = datePart.split('-');
    return `${month}/${day} ${timePart}`;
  };
  if (t.end) {
    return `${formatSingle(t.start)} - ${formatSingle(t.end)}`;
  }
  return formatSingle(t.start);
};
```

- [ ] **Step 2: Update TaskItem formatTimeTag**

In `src/components/TaskItem.tsx`, update the `formatTimeTag` function:

```typescript
const formatTimeTag = (time: TimeField): string => {
  const formatSingle = (iso: string): string => {
    if (!iso) return '';
    const [datePart, timePart] = iso.split('T');
    const [, month, day] = datePart.split('-');
    return `${month}/${day} ${timePart}`;
  };
  if (time.end) {
    return `${formatSingle(time.start)} - ${formatSingle(time.end)}`;
  }
  return formatSingle(time.start);
};
```

- [ ] **Step 3: Run type check**

Run: `npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/components/TaskInput.tsx src/components/TaskItem.tsx
git commit -m "feat: update time display format to MM/DD HH:MM"
```

---

## Task 5: Final Verification

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
1. Click clock icon → calendar popover opens
2. See month view with current month highlighted
3. Click left/right arrows → month changes
4. Click a date → date is selected (highlighted)
5. Set time → time input updates
6. Switch to "时间段" → second calendar appears
7. Set end date and time
8. Click confirm → task created with datetime
9. Task shows time tag in "MM/DD HH:MM" format
10. Click outside popover → closes
11. Click "清除" → time is removed

- [ ] **Step 4: Commit final changes**

```bash
git add -A
git commit -m "feat: complete calendar time picker implementation"
```
