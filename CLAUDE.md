# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tech Stack

- **Framework**: React 19 + TypeScript 5.8
- **Build**: Vite 7 with `@vitejs/plugin-react`
- **Styling**: Plain CSS with custom properties (CSS variables) for theming
- **State**: React hooks with localStorage persistence
- **Desktop**: Tauri 2 (Rust-based, wraps web app as native Mac .app)
- **Testing**: Vitest 4 + @testing-library/react
- **Zero runtime deps** beyond React — Canvas API for particles, Web Audio API for sound

## Commands

- `npm run dev` - Start dev server (Vite)
- `npm run build` - Type-check with `tsc -b` then build with Vite
- `npm run preview` - Preview production build
- `npm test` - Run Vitest test suite
- `npm run test:watch` - Watch mode
- `npm run test:coverage` - Coverage report
- `npm run tauri dev` - Run as desktop app in development mode
- `npm run tauri build` - Build standalone Mac .app and .dmg

## Project Structure (feature-based)

```
src/
├── app/                          # App entry
│   ├── App.tsx                   # Root component, orchestrates hooks
│   ├── main.tsx                  # ReactDOM render
│   └── styles/App.css            # Global styles + theme variables
├── features/                     # Business features
│   ├── tasks/                    # Task management
│   │   ├── components/           # TaskList, TaskItem, Sidebar, DetailPanel,
│   │   │                         # CreateTaskModal, TimePicker, EmptyState
│   │   ├── hooks/                # useTodos, useDragDrop
│   │   ├── lib/                  # validateTodo, id, formatTime
│   │   └── styles/
│   ├── achievements/             # AchievementDrawer, Toast, useAchievements
│   ├── theme/                    # useTheme, ThemeSwitcher (6 themes: 3 styles × 2 modes)
│   ├── sound/                    # useSound
│   ├── confetti/                 # ConfettiCanvas + useConfetti
│   ├── feedback/                 # InfoToast
│   ├── header/                   # Header
│   └── stats/                    # Footer + ProgressRing
├── shared/                       # Cross-feature shared code
│   ├── lib/storage.ts            # safeSetItem / safeGetItem
│   ├── constants.ts              # CATEGORIES, CATEGORY_LABELS, PRIORITY_LABELS, DAILY_GOAL
│   └── types.ts                  # Todo, Priority, FilterType, Category, TimeField, etc.
├── test/setup.ts
└── vite-env.d.ts
```

**Path alias**: `@/*` → `src/*`. Use absolute imports for cross-feature references:

```typescript
import { useTodos } from '@/features/tasks/hooks/useTodos';
import { safeSetItem } from '@/shared/lib/storage';
import type { Todo } from '@/shared/types';
```

Relative imports (`./`, `../`) are fine for intra-feature references (e.g. `./TaskItem` within `features/tasks/components/`).

## Architecture

Single-page todo list app with Chinese UI, gamification, and visual effects. Components use function declarations with default exports.

**Data flow**: `app/App.tsx` orchestrates hooks → passes state/handlers down as props → components trigger hook methods → state updates persist to localStorage.

**Hooks**:
- `useTodos` (`features/tasks/hooks/`) — task CRUD, filtering, sortMode (manual/time), reorder, search, import/export, localStorage sync
- `useTheme` (`features/theme/hooks/`) — 6 themes (workspace/editor/paper × light/dark), `data-theme` attribute on `<html>`, localStorage persistence with legacy migration
- `useSound` (`features/sound/hooks/`) — Web Audio API oscillator synthesis (complete/delete/achievement sounds), mute toggle
- `useAchievements` (`features/achievements/hooks/`) — achievement unlock tracking, streak calculation, toast notifications
- `useDragDrop` (`features/tasks/hooks/`) — HTML5 drag & drop state, dragover throttled via ref
- `useConfetti` (in `features/confetti/components/ConfettiCanvas.tsx`) — Canvas particle burst system

**Types** (`src/shared/types.ts`): `Todo`, `Priority`, `FilterType`, `Category`, `TimeField`, `AchievementDef`, `AchievementState`

**CSS theming**: `[data-theme="<id>"]` defines 24 CSS variables per theme (6 themes: workspace/editor/paper × light/dark). All components use `var(--*)` references including `--category-*` and `--priority-*`. New components use BEM class naming. CSS files live alongside their feature in `features/<name>/styles/`.

**Layout**: CSS Grid three-column shell (Sidebar 240px + List + Detail 320px), responsive breakpoints at 1024px and 720px. Task items use dual-row design (main row + sub row for tags).

**localStorage keys**: `todo-tasks`, `todo-theme`, `todo-muted`, `todo-achievements`

## Documentation

- `README.md` — project intro (latest version), mirrored in `docs/project-overview.md`
- `docs/development-logs/` — per-version development logs (`v0.1.0-*.md` through `v0.2.0-redesign.md`)

## Tauri Desktop Build

Config: `src-tauri/tauri.conf.json`. Window: 1080×720 (min 720×560), resizable. Identifier: `com.todo-app.desktop`.

Output:
- `.app`: `src-tauri/target/release/bundle/macos/Todo List.app`
- `.dmg`: `src-tauri/target/release/bundle/dmg/Todo List_0.2.0_aarch64.dmg`

Requires Rust toolchain (`rustup`). In China, configure crates.io mirror in `~/.cargo/config.toml` (USTC mirror works).

## TypeScript Config

Strict mode enabled. `noUnusedLocals` and `noUnusedParameters` are enforced - remove any unused imports/variables. `@/*` path alias configured in `tsconfig.json`.
