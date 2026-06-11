# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tech Stack

- **Framework**: React 19 + TypeScript 5.8
- **Build**: Vite 7 with `@vitejs/plugin-react`
- **Styling**: Plain CSS with custom properties (CSS variables) for theming
- **State**: React hooks with localStorage persistence
- **Desktop**: Tauri 2 (Rust-based, wraps web app as native Mac .app)
- **Zero dependencies** beyond React — Canvas API for particles, Web Audio API for sound

## Commands

- `npm run dev` - Start dev server (Vite)
- `npm run build` - Type-check with `tsc -b` then build with Vite
- `npm run preview` - Preview production build
- `npm run tauri dev` - Run as desktop app in development mode
- `npm run tauri build` - Build standalone Mac .app and .dmg

## Architecture

Single-page todo list app with Chinese UI, gamification, and visual effects. Components use function declarations with default exports.

**Data flow**: `App.tsx` orchestrates multiple hooks → passes state/handlers down as props

**Hooks**:
- `useTodos` — task CRUD, filtering, reorder, localStorage sync
- `useTheme` — dark/light mode, `data-theme` attribute on `<html>`, localStorage persistence
- `useSound` — Web Audio API oscillator synthesis (complete/delete/achievement sounds), mute toggle
- `useAchievements` — achievement unlock tracking, streak calculation, toast notifications
- `useDragDrop` — HTML5 drag & drop state management
- `useConfetti` (in ConfettiCanvas.tsx) — Canvas particle burst system

**Types** (`src/types.ts`): `Todo`, `Priority`, `FilterType`, `AchievementDef`, `AchievementState`

**Component structure**:
- `Header` — title + action buttons (mute, achievements, theme toggle)
- `TaskInput` — text input with Enter-to-submit
- `PrioritySelector` — low/medium/high priority picker
- `FilterTabs` — all/active/completed filter
- `TaskList` → `TaskItem` — task items with toggle/delete, drag-drop reordering
- `EmptyState` — shown when no tasks match filter
- `Footer` — progress ring, streak counter, total stats, clear-completed
- `ConfettiCanvas` — fixed fullscreen canvas overlay for particle effects
- `AchievementDrawer` — slide-in panel showing achievements and stats
- `Toast` — achievement unlock notification
- `ProgressRing` — SVG circular progress indicator

**CSS theming**: `:root` defines light theme variables, `[data-theme="dark"]` overrides them. All components use `var(--*)` references.

**localStorage keys**: `todo-tasks`, `todo-theme`, `todo-muted`, `todo-achievements`

## Tauri Desktop Build

Config: `src-tauri/tauri.conf.json`. Window: 640×800, resizable. Identifier: `com.todo-app.desktop`.

Output:
- `.app`: `src-tauri/target/release/bundle/macos/Todo List.app`
- `.dmg`: `src-tauri/target/release/bundle/dmg/Todo List_0.1.0_aarch64.dmg`

Requires Rust toolchain (`rustup`). In China, configure crates.io mirror in `~/.cargo/config.toml`.

## TypeScript Config

Strict mode enabled. `noUnusedLocals` and `noUnusedParameters` are enforced - remove any unused imports/variables.
