# Deluxe Todo App Enhancements Design

## Overview

Enhance the existing React todo list app with gamification, visual upgrades, and smart features — all zero-dependency, using Canvas/CSS/Web Audio APIs.

## Features

### 1. Confetti Particle System
- Canvas overlay triggered on task completion
- Particles burst from the checkbox position with gravity, rotation, fade
- 30-50 particles per burst, 800ms lifetime
- Canvas auto-removes after animation ends

### 2. Dark Mode
- CSS custom properties (`--bg`, `--text`, `--accent`, etc.) on `:root` / `[data-theme="dark"]`
- Toggle button (sun/moon icon) in top-right corner
- Preference persisted to `localStorage` key `todo-theme`
- System preference detection via `prefers-color-scheme`

### 3. Drag & Drop Reorder
- `draggable` attribute on task items
- Visual feedback: dragged item opacity, drop target highlight
- Reorder updates task array order in state and localStorage
- Works within filtered view (reorders within current filter)

### 4. Achievement System
- Three achievements with unlock conditions:
  - `first-task`: Complete your first task
  - `speed-demon`: Complete 10 tasks in one day
  - `streak-7`: Maintain a 7-day completion streak
- Achievement state stored in localStorage key `todo-achievements`
- Toast notification on unlock (slide-in from top, auto-dismiss 3s)
- Trophy icon in header opens achievement drawer (slide-in panel from right)

### 5. Streak & Stats
- Footer enhanced with: today's completed count, current streak days, total completed
- Circular progress ring (SVG) showing today's progress toward goal (default: 10 tasks/day)
- Streak calculated from localStorage date records

### 6. Sound Effects
- Web Audio API oscillator-based synthesis (no audio files)
- Three sounds: complete (ascending chirp), delete (short pop), achievement (fanfare)
- Mute toggle button next to theme toggle
- Preference persisted to `localStorage` key `todo-muted`

### 7. Smooth Animations
- CSS transitions on all interactive elements (hover, active states)
- Task add: slide-in from left + fade
- Task remove: slide-out to right + fade (existing, enhanced)
- Theme switch: 300ms background/color transition
- Achievement toast: slide-in from top

## Data Model Changes

New localStorage keys:
- `todo-theme`: `'light' | 'dark'`
- `todo-muted`: `'true' | 'false'`
- `todo-order`: `string[]` (task IDs in display order)
- `todo-achievements`: `{ unlocked: string[], streakDays: number, lastActiveDate: string }`

No changes to existing `todo-tasks` key structure.

## Component Changes

- `App.tsx`: Add theme context, achievement manager, canvas container
- `Header.tsx`: Add theme toggle, mute toggle, trophy icon
- `Footer.tsx`: Add stats display, progress ring
- `TaskItem.tsx`: Add drag handlers, confetti trigger on toggle
- `TaskList.tsx`: Add drag-drop reordering logic
- New: `AchievementDrawer.tsx`, `Toast.tsx`, `ConfettiCanvas.tsx`, `ProgressRing.tsx`

## Constraints

- Zero new npm dependencies
- All animations 60fps target
- Chinese UI maintained throughout
