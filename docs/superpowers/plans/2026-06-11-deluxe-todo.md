# Deluxe Todo App Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add gamification, visual upgrades, and smart features to the existing React todo app — all zero-dependency.

**Architecture:** Features are implemented as isolated modules (hooks, components, utilities) that integrate into the existing component tree via props. CSS variables drive theming. Canvas handles particles. Web Audio API handles sound.

**Tech Stack:** React 19, TypeScript 5.8, Vite 7, CSS custom properties, Canvas API, Web Audio API

---

## File Map

### New Files
- `src/hooks/useTheme.ts` — dark mode state + localStorage persistence
- `src/hooks/useSound.ts` — Web Audio synthesis + mute toggle
- `src/hooks/useAchievements.ts` — achievement tracking + unlock logic
- `src/hooks/useDragDrop.ts` — drag & drop reorder logic
- `src/components/ConfettiCanvas.tsx` — particle animation overlay
- `src/components/AchievementDrawer.tsx` — achievement panel
- `src/components/Toast.tsx` — notification toast
- `src/components/ProgressRing.tsx` — SVG circular progress
- `src/styles/ThemeToggle.css` — theme/mute button styles
- `src/styles/AchievementDrawer.css` — drawer panel styles
- `src/styles/Toast.css` — toast animation styles
- `src/styles/ProgressRing.css` — progress ring styles
- `src/styles/DragDrop.css` — drag visual feedback styles

### Modified Files
- `src/styles/App.css` — add dark theme CSS variables
- `src/App.tsx` — wire new hooks and components
- `src/components/Header.tsx` — add theme toggle, mute toggle, trophy icon
- `src/components/Footer.tsx` — add stats, progress ring
- `src/components/TaskItem.tsx` — add drag handlers, confetti trigger
- `src/components/TaskList.tsx` — add drag-drop reordering
- `src/types.ts` — add achievement types
- `src/hooks/useTodos.ts` — expose reorder function

---

## Task 1: Dark Mode Theme

### Step 1.1: Add dark theme CSS variables

**File:** Modify `src/styles/App.css`

Add dark theme variables after the `:root` block (after line 25):

```css
[data-theme="dark"] {
  --primary: #14B8A6;
  --primary-light: #2DD4BF;
  --cta: #FB923C;
  --bg: #0F172A;
  --card-bg: #1E293B;
  --text: #E2E8F0;
  --text-muted: #94A3B8;
  --text-light: #64748B;
  --border: #334155;
  --danger: #F87171;
  --danger-hover: #EF4444;
  --active-bg: #134E4A;
  --completed-opacity: 0.4;
}
```

### Step 1.2: Create useTheme hook

**File:** Create `src/hooks/useTheme.ts`

```typescript
import { useState, useEffect, useCallback } from 'react';

export type Theme = 'light' | 'dark';
const STORAGE_KEY = 'todo-theme';

function getInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState(prev => (prev === 'light' ? 'dark' : 'light'));
  }, []);

  return { theme, toggleTheme };
}
```

### Step 1.3: Create ThemeToggle component

**File:** Create `src/components/ThemeToggle.tsx`

```tsx
import '../styles/ThemeToggle.css';

interface ThemeToggleProps {
  theme: 'light' | 'dark';
  onToggle: () => void;
}

function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  return (
    <button
      className="icon-btn theme-toggle"
      onClick={onToggle}
      aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'}
      title={theme === 'light' ? '深色模式' : '浅色模式'}
    >
      {theme === 'light' ? (
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
        </svg>
      )}
    </button>
  );
}

export default ThemeToggle;
```

### Step 1.4: Create ThemeToggle styles

**File:** Create `src/styles/ThemeToggle.css`

```css
.icon-btn {
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 10px;
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

.header-actions {
  display: flex;
  gap: 8px;
  position: absolute;
  top: 0;
  right: 0;
}
```

### Step 1.5: Update Header to include theme toggle

**File:** Modify `src/components/Header.tsx`

Replace entire file with:

```tsx
import type { Theme } from '../hooks/useTheme';
import '../styles/Header.css';

interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
  onOpenAchievements: () => void;
}

function Header({ theme, onToggleTheme, onOpenAchievements }: HeaderProps) {
  return (
    <div className="header">
      <div className="header-actions">
        <button
          className="icon-btn"
          onClick={onOpenAchievements}
          aria-label="成就"
          title="成就"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-4.5A3.375 3.375 0 0 0 19.875 10.875 3.375 3.375 0 0 0 16.5 7.5h0a3.375 3.375 0 0 0-3.375 3.375v0A3.375 3.375 0 0 1 9.75 7.5h0a3.375 3.375 0 0 0-3.375 3.375 3.375 3.375 0 0 0-3.375 3.375V18.75m9 0h-9" />
          </svg>
        </button>
        <button
          className="icon-btn theme-toggle"
          onClick={onToggleTheme}
          aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'}
          title={theme === 'light' ? '深色模式' : '浅色模式'}
        >
          {theme === 'light' ? (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
            </svg>
          )}
        </button>
      </div>
      <h1>Todo List</h1>
      <p>管理你的每日任务</p>
    </div>
  );
}

export default Header;
```

### Step 1.6: Update Header CSS for positioning

**File:** Modify `src/styles/Header.css`

Replace entire file with:

```css
.header {
  text-align: center;
  margin-bottom: 32px;
  position: relative;
}

.header h1 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}

.header p {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.header-actions {
  display: flex;
  gap: 8px;
  position: absolute;
  top: 0;
  right: 0;
}

@media (max-width: 480px) {
  .header h1 {
    font-size: 1.5rem;
  }
}
```

### Step 1.7: Wire theme into App.tsx

**File:** Modify `src/App.tsx`

Replace entire file with:

```tsx
import { useTodos } from './hooks/useTodos';
import { useTheme } from './hooks/useTheme';
import Header from './components/Header';
import TaskInput from './components/TaskInput';
import PrioritySelector from './components/PrioritySelector';
import FilterTabs from './components/FilterTabs';
import TaskList from './components/TaskList';
import Footer from './components/Footer';

function App() {
  const todoState = useTodos();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="container">
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenAchievements={() => {}}
      />
      <TaskInput addTask={todoState.addTask} />
      <PrioritySelector
        priority={todoState.priority}
        setPriority={todoState.setPriority}
      />
      <FilterTabs
        filter={todoState.filter}
        setFilter={todoState.setFilter}
      />
      <TaskList
        tasks={todoState.tasks}
        filter={todoState.filter}
        onToggle={todoState.toggleTask}
        onDelete={todoState.removeTask}
        onReorder={todoState.reorderTasks}
      />
      <Footer
        stats={todoState.stats}
        onClearCompleted={todoState.clearCompleted}
      />
    </div>
  );
}

export default App;
```

### Step 1.8: Verify dark mode works

Run: `npm run dev`
- Click the moon/sun icon in top-right
- Verify background, text, cards all switch theme
- Refresh page — theme should persist

---

## Task 2: Sound Effects

### Step 2.1: Create useSound hook

**File:** Create `src/hooks/useSound.ts`

```typescript
import { useState, useCallback, useRef } from 'react';

const STORAGE_KEY = 'todo-muted';

function getInitialMuted(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true';
}

function createAudioContext(): AudioContext | null {
  try {
    return new (window.AudioContext || (window as any).webkitAudioContext)();
  } catch {
    return null;
  }
}

export function useSound() {
  const [muted, setMutedState] = useState(getInitialMuted);
  const ctxRef = useRef<AudioContext | null>(null);

  const getCtx = useCallback(() => {
    if (!ctxRef.current) ctxRef.current = createAudioContext();
    return ctxRef.current;
  }, []);

  const playTone = useCallback((frequency: number, duration: number, type: OscillatorType = 'sine', volume = 0.15) => {
    if (muted) return;
    const ctx = getCtx();
    if (!ctx) return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, ctx.currentTime);
    gain.gain.setValueAtTime(volume, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  }, [muted, getCtx]);

  const playComplete = useCallback(() => {
    playTone(523, 0.1, 'sine', 0.12);
    setTimeout(() => playTone(659, 0.1, 'sine', 0.12), 60);
    setTimeout(() => playTone(784, 0.15, 'sine', 0.1), 120);
  }, [playTone]);

  const playDelete = useCallback(() => {
    playTone(300, 0.08, 'square', 0.08);
  }, [playTone]);

  const playAchievement = useCallback(() => {
    playTone(523, 0.12, 'sine', 0.15);
    setTimeout(() => playTone(659, 0.12, 'sine', 0.15), 100);
    setTimeout(() => playTone(784, 0.12, 'sine', 0.15), 200);
    setTimeout(() => playTone(1047, 0.2, 'sine', 0.12), 300);
  }, [playTone]);

  const toggleMuted = useCallback(() => {
    setMutedState(prev => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  return { muted, toggleMuted, playComplete, playDelete, playAchievement };
}
```

### Step 2.2: Add mute button to Header

**File:** Modify `src/components/Header.tsx`

Update the interface to include `muted` and `onToggleMuted`:

```tsx
interface HeaderProps {
  theme: Theme;
  onToggleTheme: () => void;
  onOpenAchievements: () => void;
  muted: boolean;
  onToggleMuted: () => void;
}
```

Add the mute button inside `header-actions`, before the theme toggle button:

```tsx
<button
  className="icon-btn"
  onClick={onToggleMuted}
  aria-label={muted ? '开启音效' : '关闭音效'}
  title={muted ? '开启音效' : '关闭音效'}
>
  {muted ? (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75 19.5 12m0 0 2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6 4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 0 1 2.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75Z" />
    </svg>
  ) : (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 0 1 0 12.728M16.463 8.288a5.25 5.25 0 0 1 0 7.424M6.75 8.25l4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 0 1 2.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75Z" />
    </svg>
  )}
</button>
```

### Step 2.3: Wire sound into App.tsx

**File:** Modify `src/App.tsx`

Add import:
```tsx
import { useSound } from './hooks/useSound';
```

Add hook call:
```tsx
const sound = useSound();
```

Pass to Header:
```tsx
<Header
  theme={theme}
  onToggleTheme={toggleTheme}
  onOpenAchievements={() => {}}
  muted={sound.muted}
  onToggleMuted={sound.toggleMuted}
/>
```

### Step 2.4: Verify sound works

Run: `npm run dev`
- Add a task, toggle it complete — hear ascending chirp
- Delete a task — hear short pop
- Click mute button — sounds should stop
- Refresh — mute state should persist

---

## Task 3: Confetti Particle System

### Step 3.1: Create ConfettiCanvas component

**File:** Create `src/components/ConfettiCanvas.tsx`

```tsx
import { useRef, useCallback, useEffect } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  rotation: number;
  rotationSpeed: number;
  opacity: number;
  life: number;
}

const COLORS = ['#0D9488', '#F97316', '#EAB308', '#EC4899', '#8B5CF6', '#3B82F6', '#EF4444'];

function createParticle(x: number, y: number): Particle {
  const angle = Math.random() * Math.PI * 2;
  const speed = 2 + Math.random() * 4;
  return {
    x,
    y,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed - 2,
    size: 3 + Math.random() * 4,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    rotation: Math.random() * 360,
    rotationSpeed: (Math.random() - 0.5) * 10,
    opacity: 1,
    life: 1,
  };
}

export function useConfetti() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animFrameRef = useRef<number>(0);

  const animate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particlesRef.current = particlesRef.current.filter(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.15; // gravity
      p.rotation += p.rotationSpeed;
      p.life -= 0.015;
      p.opacity = p.life;

      if (p.life <= 0) return false;

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate((p.rotation * Math.PI) / 180);
      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
      ctx.restore();

      return true;
    });

    if (particlesRef.current.length > 0) {
      animFrameRef.current = requestAnimationFrame(animate);
    }
  }, []);

  const burst = useCallback((x: number, y: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    for (let i = 0; i < 40; i++) {
      particlesRef.current.push(createParticle(x, y));
    }

    cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(animate);
  }, [animate]);

  useEffect(() => {
    return () => cancelAnimationFrame(animFrameRef.current);
  }, []);

  return { canvasRef, burst };
}

interface ConfettiCanvasProps {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
}

function ConfettiCanvas({ canvasRef }: ConfettiCanvasProps) {
  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    />
  );
}

export default ConfettiCanvas;
```

### Step 3.2: Wire confetti into App.tsx

**File:** Modify `src/App.tsx`

Add import:
```tsx
import ConfettiCanvas, { useConfetti } from './components/ConfettiCanvas';
```

Add hook:
```tsx
const confetti = useConfetti();
```

Add canvas element before the closing `</div>`:
```tsx
<ConfettiCanvas canvasRef={confetti.canvasRef} />
```

Pass `burst` to TaskList:
```tsx
<TaskList
  tasks={todoState.tasks}
  filter={todoState.filter}
  onToggle={todoState.toggleTask}
  onDelete={todoState.removeTask}
  onReorder={todoState.reorderTasks}
  onBurstConfetti={confetti.burst}
  onCompleteSound={sound.playComplete}
  onDeleteSound={sound.playDelete}
/>
```

---

## Task 4: Drag & Drop Reorder

### Step 4.1: Add types

**File:** Modify `src/types.ts`

Add at the end:

```typescript
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

### Step 4.2: Add reorder function to useTodos

**File:** Modify `src/hooks/useTodos.ts`

Add after `clearCompleted` (around line 66):

```typescript
const reorderTasks = useCallback((fromId: string, toId: string) => {
  setTasks(prev => {
    const fromIdx = prev.findIndex(t => t.id === fromId);
    const toIdx = prev.findIndex(t => t.id === toId);
    if (fromIdx === -1 || toIdx === -1) return prev;
    const updated = [...prev];
    const [moved] = updated.splice(fromIdx, 1);
    updated.splice(toIdx, 0, moved);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  });
}, []);
```

Add `reorderTasks` to the return object.

### Step 4.3: Create useDragDrop hook

**File:** Create `src/hooks/useDragDrop.ts`

```typescript
import { useState, useCallback, useRef } from 'react';

export function useDragDrop(onReorder: (fromId: string, toId: string) => void) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const dragCounterRef = useRef(0);

  const handleDragStart = useCallback((e: React.DragEvent, id: string) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, id: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setOverId(id);
  }, []);

  const handleDragLeave = useCallback(() => {
    setOverId(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, toId: string) => {
    e.preventDefault();
    const fromId = e.dataTransfer.getData('text/plain');
    if (fromId && fromId !== toId) {
      onReorder(fromId, toId);
    }
    setDraggingId(null);
    setOverId(null);
  }, [onReorder]);

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setOverId(null);
  }, []);

  return {
    draggingId,
    overId,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
  };
}
```

### Step 4.4: Create DragDrop styles

**File:** Create `src/styles/DragDrop.css`

```css
.task-item.dragging {
  opacity: 0.4;
  transform: scale(0.98);
}

.task-item.drag-over {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-light);
  transform: translateY(2px);
}

.task-item[draggable="true"] {
  cursor: grab;
}

.task-item[draggable="true"]:active {
  cursor: grabbing;
}
```

### Step 4.5: Update TaskItem with drag handlers

**File:** Modify `src/components/TaskItem.tsx`

Update interface:
```tsx
interface TaskItemProps {
  task: Todo;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  draggingId?: string | null;
  overId?: string | null;
  onDragStart?: (e: React.DragEvent, id: string) => void;
  onDragOver?: (e: React.DragEvent, id: string) => void;
  onDragLeave?: () => void;
  onDrop?: (e: React.DragEvent, id: string) => void;
  onDragEnd?: () => void;
}
```

Add import for DragDrop styles:
```tsx
import '../styles/DragDrop.css';
```

Update the component to destructure new props and add drag attributes:

```tsx
function TaskItem({
  task, onToggle, onDelete,
  draggingId, overId,
  onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd,
}: TaskItemProps) {
  const [removing, setRemoving] = useState(false);
  const removeRef = useRef(onDelete);
  removeRef.current = onDelete;

  const handleToggle = useCallback(() => {
    onToggle(task.id);
  }, [onToggle, task.id]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle(task.id);
    }
  };

  const handleDelete = useCallback(() => {
    setRemoving(true);
    const onEnd = () => {
      removeRef.current(task.id);
    };
    const el = document.querySelector(`[data-task-id="${task.id}"]`);
    if (el) {
      el.addEventListener('animationend', onEnd, { once: true });
      setTimeout(onEnd, 200);
    } else {
      removeRef.current(task.id);
    }
  }, [task.id]);

  const isDragging = draggingId === task.id;
  const isOver = overId === task.id && draggingId !== task.id;

  return (
    <div
      className={`task-item${task.completed ? ' completed' : ''}${removing ? ' removing' : ''}${isDragging ? ' dragging' : ''}${isOver ? ' drag-over' : ''}`}
      data-task-id={task.id}
      draggable={!!onDragStart}
      onDragStart={onDragStart ? (e) => onDragStart(e, task.id) : undefined}
      onDragOver={onDragOver ? (e) => onDragOver(e, task.id) : undefined}
      onDragLeave={onDragLeave}
      onDrop={onDrop ? (e) => onDrop(e, task.id) : undefined}
      onDragEnd={onDragEnd}
    >
      <div
        className="checkbox"
        role="checkbox"
        aria-checked={task.completed}
        tabIndex={0}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <path
            d="M5 13l4 4L19 7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <span className="task-text">{escapeHtml(task.text)}</span>
      <span className={`priority-tag ${task.priority}`}>
        {priorityLabels[task.priority]}
      </span>
      <button
        className="btn-delete"
        aria-label="删除任务"
        onClick={handleDelete}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2}>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}
```

### Step 4.6: Update TaskList with drag-drop

**File:** Modify `src/components/TaskList.tsx`

Replace entire file:

```tsx
import type { Todo, FilterType } from '../types';
import { useDragDrop } from '../hooks/useDragDrop';
import '../styles/TaskList.css';
import TaskItem from './TaskItem';
import EmptyState from './EmptyState';

interface TaskListProps {
  tasks: Todo[];
  filter: FilterType;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onReorder: (fromId: string, toId: string) => void;
}

function TaskList({ tasks, filter, onToggle, onDelete, onReorder }: TaskListProps) {
  const drag = useDragDrop(onReorder);

  if (tasks.length === 0) {
    return <EmptyState filter={filter} />;
  }

  return (
    <div className="task-list">
      {tasks.map(task => (
        <TaskItem
          key={task.id}
          task={task}
          onToggle={onToggle}
          onDelete={onDelete}
          draggingId={drag.draggingId}
          overId={drag.overId}
          onDragStart={drag.handleDragStart}
          onDragOver={drag.handleDragOver}
          onDragLeave={drag.handleDragLeave}
          onDrop={drag.handleDrop}
          onDragEnd={drag.handleDragEnd}
        />
      ))}
    </div>
  );
}

export default TaskList;
```

### Step 4.7: Verify drag-drop

Run: `npm run dev`
- Add 3+ tasks
- Drag one task to a new position
- Verify visual feedback (opacity on drag, border on hover)
- Verify order persists after refresh

---

## Task 5: Achievement System

### Step 5.1: Create useAchievements hook

**File:** Create `src/hooks/useAchievements.ts`

```typescript
import { useState, useCallback, useRef } from 'react';
import type { AchievementDef, AchievementState } from '../types';

const STORAGE_KEY = 'todo-achievements';

export const ACHIEVEMENTS: AchievementDef[] = [
  { id: 'first-task', name: '初出茅庐', description: '完成你的第一个任务', icon: '🌱' },
  { id: 'speed-demon', name: '效率达人', description: '一天内完成10个任务', icon: '⚡' },
  { id: 'streak-7', name: '永不言弃', description: '连续7天完成任务', icon: '🔥' },
];

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function getInitialState(): AchievementState {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return { unlocked: [], streakDays: 0, lastActiveDate: '', todayCompleted: 0, todayDate: getToday() };
}

export function useAchievements(onUnlockSound?: () => void) {
  const [state, setState] = useState(getInitialState);
  const [toast, setToast] = useState<AchievementDef | null>(null);
  const toastTimerRef = useRef<number>(0);

  const checkAchievements = useCallback((completedCount: number, newUnlocked: string[]) => {
    const checks: { id: string; condition: boolean }[] = [
      { id: 'first-task', condition: completedCount >= 1 },
      { id: 'speed-demon', condition: completedCount >= 10 },
      { id: 'streak-7', condition: false }, // checked separately via streak
    ];

    for (const check of checks) {
      if (check.condition && !newUnlocked.includes(check.id)) {
        newUnlocked.push(check.id);
      }
    }
    return newUnlocked;
  }, []);

  const recordCompletion = useCallback(() => {
    setState(prev => {
      const today = getToday();
      let todayCompleted = prev.todayDate === today ? prev.todayCompleted + 1 : 1;
      let streakDays = prev.streakDays;

      // Update streak
      if (prev.lastActiveDate !== today) {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().slice(0, 10);
        streakDays = prev.lastActiveDate === yesterdayStr ? streakDays + 1 : 1;
      }

      let unlocked = [...prev.unlocked];
      unlocked = checkAchievements(todayCompleted, unlocked);

      // Check streak achievement
      if (streakDays >= 7 && !unlocked.includes('streak-7')) {
        unlocked.push('streak-7');
      }

      // Find newly unlocked
      const newlyUnlocked = unlocked.filter(id => !prev.unlocked.includes(id));
      if (newlyUnlocked.length > 0) {
        const achievement = ACHIEVEMENTS.find(a => a.id === newlyUnlocked[0]);
        if (achievement) {
          setToast(achievement);
          onUnlockSound?.();
          clearTimeout(toastTimerRef.current);
          toastTimerRef.current = window.setTimeout(() => setToast(null), 3000);
        }
      }

      const newState: AchievementState = {
        unlocked,
        streakDays,
        lastActiveDate: today,
        todayCompleted,
        todayDate: today,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newState));
      return newState;
    });
  }, [checkAchievements, onUnlockSound]);

  const dismissToast = useCallback(() => {
    setToast(null);
  }, []);

  return {
    achievements: state,
    toast,
    dismissToast,
    recordCompletion,
    allAchievements: ACHIEVEMENTS,
  };
}
```

### Step 5.2: Create Toast component

**File:** Create `src/components/Toast.tsx`

```tsx
import '../styles/Toast.css';

interface ToastProps {
  icon: string;
  title: string;
  description: string;
  onDismiss: () => void;
}

function Toast({ icon, title, description, onDismiss }: ToastProps) {
  return (
    <div className="toast" onClick={onDismiss}>
      <span className="toast-icon">{icon}</span>
      <div className="toast-content">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </div>
  );
}

export default Toast;
```

### Step 5.3: Create Toast styles

**File:** Create `src/styles/Toast.css`

```css
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: var(--card-bg);
  border: 1px solid var(--primary);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  z-index: 10000;
  animation: toastIn 300ms ease-out;
}

.toast-icon {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.toast-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toast-content strong {
  font-size: 0.875rem;
  color: var(--text);
}

.toast-content span {
  font-size: 0.75rem;
  color: var(--text-muted);
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}
```

### Step 5.4: Create AchievementDrawer component

**File:** Create `src/components/AchievementDrawer.tsx`

```tsx
import type { AchievementDef, AchievementState } from '../types';
import '../styles/AchievementDrawer.css';

interface AchievementDrawerProps {
  open: boolean;
  onClose: () => void;
  achievements: AchievementState;
  allAchievements: AchievementDef[];
}

function AchievementDrawer({ open, onClose, achievements, allAchievements }: AchievementDrawerProps) {
  if (!open) return null;

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-header">
          <h2>成就</h2>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="drawer-stats">
          <div className="stat-item">
            <span className="stat-value">{achievements.streakDays}</span>
            <span className="stat-label">连续天数</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{achievements.todayCompleted}</span>
            <span className="stat-label">今日完成</span>
          </div>
        </div>
        <div className="achievement-list">
          {allAchievements.map(a => {
            const unlocked = achievements.unlocked.includes(a.id);
            return (
              <div key={a.id} className={`achievement-card${unlocked ? ' unlocked' : ''}`}>
                <span className="achievement-icon">{unlocked ? a.icon : '🔒'}</span>
                <div className="achievement-info">
                  <strong>{a.name}</strong>
                  <span>{a.description}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

export default AchievementDrawer;
```

### Step 5.5: Create AchievementDrawer styles

**File:** Create `src/styles/AchievementDrawer.css`

```css
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 9998;
  animation: fadeIn 200ms ease;
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 320px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg);
  border-left: 1px solid var(--border);
  z-index: 9999;
  padding: 24px;
  overflow-y: auto;
  animation: slideInRight 250ms ease-out;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.drawer-header h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text);
}

.drawer-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-item {
  flex: 1;
  text-align: center;
  padding: 16px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 4px;
}

.achievement-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.achievement-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  opacity: 0.5;
  transition: all var(--transition);
}

.achievement-card.unlocked {
  opacity: 1;
  border-color: var(--primary-light);
}

.achievement-icon {
  font-size: 1.75rem;
  flex-shrink: 0;
}

.achievement-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.achievement-info strong {
  font-size: 0.875rem;
  color: var(--text);
}

.achievement-info span {
  font-size: 0.75rem;
  color: var(--text-muted);
}

@keyframes slideInRight {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### Step 5.6: Wire achievements into App.tsx

**File:** Modify `src/App.tsx`

Add imports:
```tsx
import { useAchievements } from './hooks/useAchievements';
import AchievementDrawer from './components/AchievementDrawer';
import Toast from './components/Toast';
```

Add state and hooks:
```tsx
const [drawerOpen, setDrawerOpen] = useState(false);
const achievements = useAchievements(sound.playAchievement);
```

Add to JSX (after the container div opening, before Header):
```tsx
<AchievementDrawer
  open={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  achievements={achievements.achievements}
  allAchievements={achievements.allAchievements}
/>
{achievements.toast && (
  <Toast
    icon={achievements.toast.icon}
    title={achievements.toast.name}
    description={achievements.toast.description}
    onDismiss={achievements.dismissToast}
  />
)}
```

Update Header props:
```tsx
<Header
  theme={theme}
  onToggleTheme={toggleTheme}
  onOpenAchievements={() => setDrawerOpen(true)}
  muted={sound.muted}
  onToggleMuted={sound.toggleMuted}
/>
```

### Step 5.7: Hook achievement recording into task toggle

The `recordCompletion` needs to be called when a task is toggled to completed. This will be wired through the TaskList/TaskItem chain. For now, wire it in App by wrapping `toggleTask`:

**File:** Modify `src/App.tsx`

Replace the `onToggle` prop:
```tsx
onToggle={(id) => {
  const task = todoState.allTasks.find(t => t.id === id);
  todoState.toggleTask(id);
  if (task && !task.completed) {
    achievements.recordCompletion();
  }
}}
```

### Step 5.8: Add useState import

**File:** Modify `src/App.tsx`

Add `useState` to the React import (or add a standalone import):
```tsx
import { useState } from 'react';
```

---

## Task 6: Streak & Stats with Progress Ring

### Step 6.1: Create ProgressRing component

**File:** Create `src/components/ProgressRing.tsx`

```tsx
import '../styles/ProgressRing.css';

interface ProgressRingProps {
  current: number;
  goal: number;
  size?: number;
  strokeWidth?: number;
}

function ProgressRing({ current, goal, size = 48, strokeWidth = 4 }: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(current / goal, 1);
  const offset = circumference * (1 - progress);

  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          className="progress-ring-bg"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
        />
        <circle
          className="progress-ring-fill"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="progress-ring-text">{current}/{goal}</span>
    </div>
  );
}

export default ProgressRing;
```

### Step 6.2: Create ProgressRing styles

**File:** Create `src/styles/ProgressRing.css`

```css
.progress-ring {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.progress-ring-bg {
  stroke: var(--border);
}

.progress-ring-fill {
  stroke: var(--primary);
  transition: stroke-dashoffset 500ms ease;
}

.progress-ring-text {
  position: absolute;
  font-size: 0.625rem;
  font-weight: 600;
  color: var(--text-muted);
}
```

### Step 6.3: Update Footer with stats and progress ring

**File:** Modify `src/components/Footer.tsx`

Replace entire file:

```tsx
import type { AchievementState } from '../types';
import ProgressRing from './ProgressRing';
import '../styles/Footer.css';

interface FooterProps {
  stats: {
    total: number;
    active: number;
    completed: number;
  };
  onClearCompleted: () => void;
  achievements?: AchievementState;
}

const DAILY_GOAL = 10;

function Footer({ stats, onClearCompleted, achievements }: FooterProps) {
  const todayCompleted = achievements?.todayCompleted ?? 0;
  const streakDays = achievements?.streakDays ?? 0;

  return (
    <div className="footer">
      <div className="footer-stats">
        <div className="footer-stat">
          <ProgressRing current={todayCompleted} goal={DAILY_GOAL} />
          <span className="footer-stat-label">今日目标</span>
        </div>
        <div className="footer-stat">
          <span className="footer-stat-value">{streakDays}</span>
          <span className="footer-stat-label">连续天数</span>
        </div>
        <div className="footer-stat">
          <span className="footer-stat-value">{stats.completed}</span>
          <span className="footer-stat-label">总完成</span>
        </div>
      </div>
      <div className="footer-actions">
        <span className="footer-summary">
          共 {stats.total} 项 · 未完成 {stats.active}
        </span>
        <button
          className="btn-clear"
          disabled={stats.completed === 0}
          onClick={onClearCompleted}
        >
          清除已完成
        </button>
      </div>
    </div>
  );
}

export default Footer;
```

### Step 6.4: Update Footer styles

**File:** Modify `src/styles/Footer.css`

Replace entire file:

```css
.footer {
  margin-top: 20px;
  padding: 16px 0;
}

.footer-stats {
  display: flex;
  justify-content: center;
  gap: 32px;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.footer-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.footer-stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--primary);
}

.footer-stat-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
}

.footer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-summary {
  font-size: 0.8125rem;
  color: var(--text-light);
}

.btn-clear {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card-bg);
  font-size: 0.8125rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  color: var(--text-muted);
  transition: all var(--transition);
}

.btn-clear:hover {
  border-color: var(--danger);
  color: var(--danger);
}

.btn-clear:focus-visible {
  outline: 2px solid var(--danger);
  outline-offset: 2px;
}

.btn-clear:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

### Step 6.5: Wire achievements into Footer

**File:** Modify `src/App.tsx`

Update Footer props:
```tsx
<Footer
  stats={todoState.stats}
  onClearCompleted={todoState.clearCompleted}
  achievements={achievements.achievements}
/>
```

---

## Task 7: Final Polish & Integration

### Step 7.1: Final App.tsx

**File:** Verify `src/App.tsx` has all imports and hooks wired correctly:

```tsx
import { useState } from 'react';
import { useTodos } from './hooks/useTodos';
import { useTheme } from './hooks/useTheme';
import { useSound } from './hooks/useSound';
import { useAchievements } from './hooks/useAchievements';
import { useConfetti } from './components/ConfettiCanvas';
import Header from './components/Header';
import TaskInput from './components/TaskInput';
import PrioritySelector from './components/PrioritySelector';
import FilterTabs from './components/FilterTabs';
import TaskList from './components/TaskList';
import Footer from './components/Footer';
import ConfettiCanvas from './components/ConfettiCanvas';
import AchievementDrawer from './components/AchievementDrawer';
import Toast from './components/Toast';

function App() {
  const todoState = useTodos();
  const { theme, toggleTheme } = useTheme();
  const sound = useSound();
  const achievements = useAchievements(sound.playAchievement);
  const confetti = useConfetti();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="container">
      <AchievementDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        achievements={achievements.achievements}
        allAchievements={achievements.allAchievements}
      />
      {achievements.toast && (
        <Toast
          icon={achievements.toast.icon}
          title={achievements.toast.name}
          description={achievements.toast.description}
          onDismiss={achievements.dismissToast}
        />
      )}
      <ConfettiCanvas canvasRef={confetti.canvasRef} />
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenAchievements={() => setDrawerOpen(true)}
        muted={sound.muted}
        onToggleMuted={sound.toggleMuted}
      />
      <TaskInput addTask={todoState.addTask} />
      <PrioritySelector
        priority={todoState.priority}
        setPriority={todoState.setPriority}
      />
      <FilterTabs
        filter={todoState.filter}
        setFilter={todoState.setFilter}
      />
      <TaskList
        tasks={todoState.tasks}
        filter={todoState.filter}
        onToggle={(id) => {
          const task = todoState.allTasks.find(t => t.id === id);
          todoState.toggleTask(id);
          if (task && !task.completed) {
            achievements.recordCompletion();
            sound.playComplete();
            const el = document.querySelector(`[data-task-id="${id}"]`);
            if (el) {
              const rect = el.getBoundingClientRect();
              confetti.burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
            }
          }
        }}
        onDelete={(id) => {
          sound.playDelete();
          todoState.removeTask(id);
        }}
        onReorder={todoState.reorderTasks}
      />
      <Footer
        stats={todoState.stats}
        onClearCompleted={todoState.clearCompleted}
        achievements={achievements.achievements}
      />
    </div>
  );
}

export default App;
```

### Step 7.2: Build and verify

Run: `npm run build`

Expected: TypeScript compiles without errors, Vite produces dist/ output.

### Step 7.3: Full feature test

Run: `npm run dev`

Test each feature:
1. **Dark mode**: Click sun/moon toggle, verify all elements switch theme
2. **Sound**: Toggle complete/delete, hear sounds. Mute button silences all
3. **Confetti**: Complete a task, particles burst from checkbox
4. **Drag-drop**: Drag a task to reorder, verify position changes
5. **Achievements**: Complete first task → toast appears. Open drawer via trophy icon
6. **Stats**: Footer shows today's count, streak, total. Progress ring fills
7. **Animations**: Task add/remove have smooth transitions

### Step 7.4: Commit

```bash
git add -A
git commit -m "feat: add deluxe features — dark mode, confetti, drag-drop, achievements, sound, stats"
```

---

## Verification Checklist

- [ ] Dark mode toggles and persists across refresh
- [ ] Confetti bursts from checkbox on task completion
- [ ] Sound effects play for complete/delete/achievement
- [ ] Mute toggle works and persists
- [ ] Drag and drop reorders tasks
- [ ] Achievement toast appears on first completion
- [ ] Achievement drawer shows all achievements with unlock status
- [ ] Footer shows today count, streak, total with progress ring
- [ ] All animations are smooth (add, remove, theme switch)
- [ ] No new npm dependencies added
- [ ] `npm run build` succeeds with no errors
- [ ] Chinese UI maintained throughout
