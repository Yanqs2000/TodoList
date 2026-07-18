# TodoList Bilingual UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted Chinese/English interface switch that localizes every first-party UI string while keeping user content and the application version unchanged at 1.0.0.

**Architecture:** A small typed `features/i18n` layer owns translation lookup, date formatting, error-code copy, and the document language. The existing settings API persists `zh-CN` or `en` in SQLite through migration 002; React publishes a language change only after the backend confirms it. Existing components consume translations through context, while stable task/category/achievement IDs remain language-neutral.

**Tech Stack:** React 19, TypeScript 5.8, Vitest, FastAPI, Pydantic, Python `sqlite3`, pytest, Tauri 2, Rust.

## Global Constraints

- Supported languages are exactly `zh-CN` and `en`; default is `zh-CN`.
- English dates use `en-US`; user task titles and notes are never translated.
- Do not add runtime dependencies, `localStorage`, a browser persistence fallback, or language-specific CSS.
- Preserve current Chinese copy and visual styling.
- Keep every package and application version at `1.0.0`.
- Do not modify `backend/migrations/001_initial.sql`; add migration 002.
- Do not use subagents for execution.

---

## File Structure

New files:

- `backend/migrations/002_add_language_setting.sql` — upgrades existing settings rows with a constrained language column.
- `frontend/src/features/i18n/translations.ts` — typed dictionaries, interpolation, error-code mapping, and locale helpers.
- `frontend/src/features/i18n/I18nProvider.tsx` — React context and `<html lang>` synchronization.
- `frontend/src/features/i18n/hooks/useLanguage.ts` — database-first language state and serialized writes.
- `frontend/src/features/i18n/__tests__/translations.test.ts` — dictionary parity and interpolation tests.
- `frontend/src/features/i18n/hooks/__tests__/useLanguage.test.ts` — persistence and rollback tests.

Existing files change only where they own translated text, settings contracts, tests, or v1.0.0 documentation.

---

### Task 1: Persist the Language Setting in SQLite

**Files:**
- Create: `backend/migrations/002_add_language_setting.sql`
- Modify: `backend/src/todo_backend/models.py`
- Modify: `backend/src/todo_backend/repositories/settings.py`
- Modify: `backend/tests/test_database.py`
- Modify: `backend/tests/test_bootstrap_api.py`
- Modify: `backend/tests/test_settings_api.py`
- Test: `backend/tests/test_database.py`
- Test: `backend/tests/test_bootstrap_api.py`
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Produces: `Language = Literal["zh-CN", "en"]`.
- Produces: `AppSettings.language: Language` and `SettingsPatchCommand.language: Language | None`.
- Produces: settings JSON field `language` and accepted patch body `{ "language": "en" }`.

- [ ] **Step 1: Write failing backend tests**

Add assertions that a migrated database has `PRAGMA user_version == 2`, `app_settings.language == "zh-CN"`, bootstrap contains `"language": "zh-CN"`, patching to `en` survives a new client, and `fr` receives HTTP 422.

```python
def test_language_setting_defaults_and_persists(client: TestClient) -> None:
    headers = {"Authorization": "Bearer test-token"}
    changed = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"language": "en"},
    )
    assert changed.status_code == 200
    assert changed.json()["settings"]["language"] == "en"


def test_settings_patch_rejects_unsupported_language(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings",
        headers={"Authorization": "Bearer test-token"},
        json={"language": "fr"},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run --directory backend pytest tests/test_database.py tests/test_bootstrap_api.py tests/test_settings_api.py
```

Expected: failures because the schema and settings responses do not contain `language`.

- [ ] **Step 3: Implement migration and models**

Create the migration:

```sql
ALTER TABLE app_settings
ADD COLUMN language TEXT NOT NULL DEFAULT 'zh-CN'
CHECK (language IN ('zh-CN', 'en'));
```

Add the type and fields:

```python
Language = Literal["zh-CN", "en"]

class AppSettings(WireModel):
    theme: ThemeId
    muted: bool
    shortcut: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    language: Language

class SettingsPatchCommand(WireModel):
    theme: ThemeId | None = None
    muted: bool | None = None
    shortcut: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None
    language: Language | None = None
```

Update `SettingsRepository.get()` to select and return `language`. Existing generic patch logic then persists it without a new route.

- [ ] **Step 4: Run focused backend tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the backend setting**

```bash
git add backend/migrations/002_add_language_setting.sql backend/src/todo_backend/models.py backend/src/todo_backend/repositories/settings.py backend/tests/test_database.py backend/tests/test_bootstrap_api.py backend/tests/test_settings_api.py
git commit -m "feat: persist interface language"
```

---

### Task 2: Build the Typed Internationalization Core

**Files:**
- Create: `frontend/src/features/i18n/translations.ts`
- Create: `frontend/src/features/i18n/I18nProvider.tsx`
- Create: `frontend/src/features/i18n/__tests__/translations.test.ts`
- Modify: `frontend/src/test/setup.ts`
- Test: `frontend/src/features/i18n/__tests__/translations.test.ts`

**Interfaces:**
- Produces: `type Language = 'zh-CN' | 'en'`.
- Produces: `translate(language, key, params?)`, `translationForError(language, code)`, and `localeFor(language)`.
- Produces: `I18nProvider`, `useI18n()`, and context fields `language`, `t`, `errorText`, `locale`.

- [ ] **Step 1: Write failing dictionary tests**

```typescript
import { describe, expect, it } from 'vitest';
import { translate, translationKeys } from '../translations';

describe('translations', () => {
  it('provides every key in both languages', () => {
    expect(translationKeys('zh-CN')).toEqual(translationKeys('en'));
  });

  it('interpolates dynamic values without changing user text', () => {
    expect(translate('en', 'feedback.reminder', { task: '写周报' }))
      .toBe('⏰ Time for: 写周报');
  });
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
npm --prefix frontend test -- src/features/i18n/__tests__/translations.test.ts
```

Expected: failure because the i18n modules do not exist.

- [ ] **Step 3: Implement the dictionaries and provider**

Use a flat dictionary whose English shape is checked against Chinese:

```typescript
export type Language = 'zh-CN' | 'en';

const zhCN = {
  'header.newTask': '新建任务',
  'header.switchToEnglish': '切换为英文',
  'feedback.reminder': '⏰ 任务到时间了：{task}',
  'errors.generic': '操作失败，请重试。',
} as const;

export type TranslationKey = keyof typeof zhCN;
const en: Record<TranslationKey, string> = {
  'header.newTask': 'New Task',
  'header.switchToEnglish': 'Switch to English',
  'feedback.reminder': '⏰ Time for: {task}',
  'errors.generic': 'Something went wrong. Please try again.',
};
```

Create explicit namespaces for `header`, `sidebar`, `task`, `timeline`, `create`, `detail`, `timePicker`, `settings`, `theme`, `achievement`, `footer`, `confirm`, `feedback`, `startup`, `errors`, `accessibility`, `category`, and `priority`. Copy every current Chinese production literal in those areas verbatim into `zhCN`, provide its approved natural-English counterpart in `en`, and implement `{name}` interpolation without HTML parsing. `I18nProvider` memoizes its context value and updates `document.documentElement.lang` in an effect. After component migration, this audit must report no Chinese production literals outside `translations.ts`:

```bash
rg -n --glob '*.tsx' --glob '*.ts' '[一-龥]' frontend/src \
  | rg -v 'features/i18n/translations.ts|__tests__'
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: the dictionary tests pass.

- [ ] **Step 5: Commit the i18n core**

```bash
git add frontend/src/features/i18n frontend/src/test/setup.ts
git commit -m "feat: add typed bilingual copy"
```

---

### Task 3: Connect Bootstrap, Persistence, and the Header Button

**Files:**
- Create: `frontend/src/features/i18n/hooks/useLanguage.ts`
- Create: `frontend/src/features/i18n/hooks/__tests__/useLanguage.test.ts`
- Modify: `frontend/src/shared/api/contracts.ts`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/features/header/components/Header.tsx`
- Modify: `frontend/src/features/header/styles/Header.css`
- Modify: `frontend/src/app/__tests__/App.test.tsx`
- Modify: `frontend/src/app/hooks/__tests__/useBootstrap.test.ts`
- Modify: `frontend/src/shared/api/__tests__/client.test.ts`
- Test: `frontend/src/features/i18n/hooks/__tests__/useLanguage.test.ts`
- Test: `frontend/src/app/__tests__/App.test.tsx`

**Interfaces:**
- Consumes: backend `settings.language` and Task 2 `Language`/`I18nProvider`.
- Produces: `useLanguage(initialLanguage, api, onInfrastructureError)` returning `{ language, setLanguage, pending }`.
- Produces: Header button that displays `EN` in Chinese and `中文` in English.

- [ ] **Step 1: Write failing persistence and header tests**

Test successful database-first switching, failed writes retaining Chinese, bootstrap restoring English, and the button label changing only after resolution.

```typescript
it('publishes English only after settings persistence succeeds', async () => {
  const deferred = Promise.withResolvers<AppSettings>();
  api.updateSettings.mockReturnValue(deferred.promise);
  const { result } = renderHook(
    () => useLanguage('zh-CN', api, onInfrastructureError),
  );
  let operation: Promise<boolean>;
  act(() => { operation = result.current.setLanguage('en'); });
  expect(result.current.language).toBe('zh-CN');
  deferred.resolve({ ...settings, language: 'en' });
  await act(async () => { await operation; });
  expect(result.current.language).toBe('en');
});
```

- [ ] **Step 2: Run focused frontend tests and verify RED**

```bash
npm --prefix frontend test -- src/features/i18n/hooks/__tests__/useLanguage.test.ts src/app/__tests__/App.test.tsx src/shared/api/__tests__/client.test.ts
```

Expected: failures because contracts and the language button are absent.

- [ ] **Step 3: Implement the controlled language flow**

Add `language` to `AppSettings` and `SettingsPatch`. Mount `I18nProvider` around `StartupGate`. `useLanguage` starts with `zh-CN`, synchronizes a non-null bootstrap language, serializes writes, and changes state only from the returned `settings.language`.

Pass only behavior state to Header:

```typescript
interface HeaderProps {
  onToggleLanguage: () => void;
  languagePending: boolean;
  // existing props remain unchanged
}
```

Header reads its label and accessible copy from `useI18n()` and places the compact text button immediately before the sound button.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the working language switch**

```bash
git add frontend/src/features/i18n/hooks frontend/src/shared/api frontend/src/app frontend/src/features/header
git commit -m "feat: add persisted language switch"
```

---

### Task 4: Localize the Main Navigation and Task List

**Files:**
- Modify: `frontend/src/shared/constants.ts`
- Modify: `frontend/src/features/tasks/components/Sidebar.tsx`
- Modify: `frontend/src/features/tasks/components/TaskList.tsx`
- Modify: `frontend/src/features/tasks/components/TaskItem.tsx`
- Modify: `frontend/src/features/tasks/components/DayTimeline.tsx`
- Modify: `frontend/src/features/tasks/components/EmptyState.tsx`
- Modify: `frontend/src/features/stats/components/Footer.tsx`
- Modify: `frontend/src/features/tasks/components/__tests__/TaskList.test.tsx`
- Modify: `frontend/src/features/tasks/components/__tests__/DayTimeline.test.tsx`
- Modify: `frontend/src/features/tasks/components/__tests__/EmptyState.test.tsx`
- Test: existing component tests above

**Interfaces:**
- Consumes: `useI18n().t` and stable category/priority/filter IDs.
- Produces: localized navigation, task actions, time groups, empty states, and footer.

- [ ] **Step 1: Add failing English component assertions**

Wrap representative renders with `I18nProvider language="en"` and assert `All`, `Active`, `Completed`, `Manual`, `By Time`, `Overdue`, `Today`, `Later`, `Unscheduled`, and English action labels. Keep task text such as `写周报` unchanged.

- [ ] **Step 2: Run the component tests and verify RED**

```bash
npm --prefix frontend test -- src/features/tasks/components/__tests__/TaskList.test.tsx src/features/tasks/components/__tests__/DayTimeline.test.tsx src/features/tasks/components/__tests__/EmptyState.test.tsx
```

Expected: English assertions fail against current Chinese literals.

- [ ] **Step 3: Replace main-shell literals with translation keys**

Keep `CATEGORIES`, `PRIORITIES`, filter values, and task values unchanged. Replace exported localized label records with functions or translation-key records:

```typescript
export const CATEGORY_LABEL_KEYS: Record<Category, TranslationKey> = {
  work: 'category.work',
  study: 'category.study',
  life: 'category.life',
  other: 'category.other',
};
```

Components translate at render time. Dynamic counts use interpolation keys rather than concatenating Chinese fragments.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: Chinese legacy assertions and new English assertions pass.

- [ ] **Step 5: Commit main-interface translations**

```bash
git add frontend/src/shared/constants.ts frontend/src/features/tasks frontend/src/features/stats
git commit -m "feat: localize task navigation"
```

---

### Task 5: Localize Dialogs, Settings, Themes, and Achievements

**Files:**
- Modify: `frontend/src/features/tasks/components/CreateTaskModal.tsx`
- Modify: `frontend/src/features/tasks/components/DetailPanel.tsx`
- Modify: `frontend/src/features/tasks/components/TimePicker.tsx`
- Modify: `frontend/src/features/desktop/components/SettingsModal.tsx`
- Modify: `frontend/src/features/theme/hooks/useTheme.ts`
- Modify: `frontend/src/features/achievements/hooks/useAchievements.ts`
- Modify: `frontend/src/features/achievements/components/AchievementDrawer.tsx`
- Modify: `frontend/src/shared/components/ConfirmDialog.tsx`
- Modify: `frontend/src/app/__tests__/App.test.tsx`
- Modify: `frontend/src/features/achievements/hooks/__tests__/useAchievements.test.ts`
- Modify: `frontend/src/features/theme/hooks/__tests__/useTheme.test.ts`
- Modify: `frontend/src/shared/components/__tests__/ConfirmDialog.test.tsx`
- Test: existing frontend component/hook tests

**Interfaces:**
- Consumes: Task 2 translation keys and `locale`.
- Produces: localized modals, calendar, theme copy, achievement copy, and confirmations.

- [ ] **Step 1: Add failing English workflow assertions**

Render the application with bootstrap language `en`; open New Task, Settings, and a task detail. Assert English headings, fields, buttons, theme descriptions, weekday/month labels, achievement names, and confirmation copy.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
npm --prefix frontend test -- src/app/__tests__/App.test.tsx src/features/achievements/hooks/__tests__/useAchievements.test.ts src/features/theme/hooks/__tests__/useTheme.test.ts src/shared/components/__tests__/ConfirmDialog.test.tsx
```

Expected: new English assertions fail.

- [ ] **Step 3: Translate dialogs and stable metadata**

Use translation keys for theme names/descriptions and achievement name/description while retaining theme IDs, achievement IDs, icons, and persisted values. Generate calendar month/weekday copy from the current locale. ConfirmDialog receives already localized copy from the caller and localizes only its own default button labels.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit remaining component translations**

```bash
git add frontend/src/features/tasks/components frontend/src/features/desktop frontend/src/features/theme frontend/src/features/achievements frontend/src/shared/components frontend/src/app/__tests__/App.test.tsx
git commit -m "feat: localize dialogs and settings"
```

---

### Task 6: Localize Dates, Notifications, Feedback, and Errors

**Files:**
- Modify: `frontend/src/features/tasks/lib/formatTime.ts`
- Modify: `frontend/src/features/reminders/hooks/useReminders.ts`
- Modify: `frontend/src/features/tasks/hooks/useTodos.ts`
- Modify: `frontend/src/app/hooks/useBootstrap.ts`
- Modify: `frontend/src/app/components/StartupGate.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: tests for the files above
- Test: `frontend/src/app/components/__tests__/StartupGate.test.tsx`
- Test: `frontend/src/features/reminders/hooks/__tests__/useReminders.test.ts`
- Test: `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts`

**Interfaces:**
- Consumes: `translationForError`, `locale`, and dynamic interpolation.
- Produces: localized date strings, notification titles, feedback messages, startup copy, and stable-code errors.

- [ ] **Step 1: Write failing dynamic-copy tests**

Assert English startup states, reminder notification title/body, clear-completed count, delete confirmation interpolation, and date formatting. Assert a task named `写周报` remains unchanged inside English feedback.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
npm --prefix frontend test -- src/app/components/__tests__/StartupGate.test.tsx src/features/reminders/hooks/__tests__/useReminders.test.ts src/features/tasks/hooks/__tests__/useTodos.test.ts
```

Expected: failures against hard-coded Chinese and raw backend messages.

- [ ] **Step 3: Implement localized dynamic copy**

Store stable business error codes in `useTodos` instead of backend messages. Translate codes at the App boundary. Change `formatTimeField` to accept `Language` or locale and use `Intl.DateTimeFormat`. Translate browser notifications when they are created, so they use the active language at event time.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit dynamic localization**

```bash
git add frontend/src/features/tasks frontend/src/features/reminders frontend/src/app
git commit -m "feat: localize dates and feedback"
```

---

### Task 7: Update v1.0.0 Documentation Without a Version Bump

**Files:**
- Modify: `README.md`
- Modify: `docs/project-overview.md`
- Modify: `docs/development-logs/v1.0.0-python-sqlite-desktop.md`
- Modify: `docs/architecture/installation.md` only if release instructions or verification counts change

**Interfaces:**
- Consumes: verified feature behavior and final test counts.
- Produces: current v1.0.0 documentation and release notes mentioning the bilingual switch.

- [ ] **Step 1: Update current documentation**

Document the homepage `EN`/`中文` control, SQLite persistence, complete first-party translation scope, English date behavior, and unchanged user content. Keep every version reference at v1.0.0 and append verified test counts only after running them.

- [ ] **Step 2: Verify documentation and version consistency**

```bash
git diff --check
rg -n '"version": "1\.0\.0"|^version = "1\.0\.0"' frontend/package.json desktop/package.json desktop/src-tauri/tauri.conf.json desktop/src-tauri/Cargo.toml backend/pyproject.toml
```

Expected: no whitespace errors and no package version change away from 1.0.0.

- [ ] **Step 3: Commit documentation**

```bash
git add README.md docs/project-overview.md docs/development-logs/v1.0.0-python-sqlite-desktop.md docs/architecture/installation.md
git commit -m "docs: include bilingual UI in v1.0.0"
```

---

### Task 8: Full Verification, Packaging, and v1.0.0 Replacement

**Files:**
- Generated: `desktop/src-tauri/target/release/bundle/macos/Todo List.app`
- Generated: `desktop/src-tauri/target/release/bundle/dmg/Todo List_1.0.0_aarch64.dmg`
- External: GitHub `main`, tag `v1.0.0`, Release asset, and TodoList Notion pages

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: verified source, signed macOS package, updated GitHub v1.0.0, and synchronized Notion documentation.

- [ ] **Step 1: Run complete local verification**

```bash
uv run --directory backend pytest
uv run --directory backend ruff check .
uv run --directory backend pyright
npm --prefix frontend test
npm --prefix frontend run build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Build and sign the unchanged v1.0.0 package**

```bash
npm --prefix desktop run build
npm --prefix desktop run sign:macos
```

Expected: `Todo List_1.0.0_aarch64.dmg` is regenerated and both signature checks pass.

- [ ] **Step 3: Verify the actual DMG sidecar**

Run:

```bash
DMG='desktop/src-tauri/target/release/bundle/dmg/Todo List_1.0.0_aarch64.dmg'
MOUNT_DIR=$(mktemp -d)
trap 'hdiutil detach "$MOUNT_DIR" >/dev/null 2>&1 || true; rmdir "$MOUNT_DIR" 2>/dev/null || true' EXIT
hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT_DIR" "$DMG" >/dev/null
SIDECAR="$MOUNT_DIR/Todo List.app/Contents/MacOS/todo-backend"
codesign -d --verbose=4 "$SIDECAR" 2>&1 | rg 'flags=0x2\(adhoc\)'
TODO_BACKEND_BINARY="$SIDECAR" uv run --directory backend pytest tests/test_packaging_smoke.py
shasum -a 256 "$DMG"
hdiutil detach "$MOUNT_DIR" >/dev/null
rmdir "$MOUNT_DIR"
trap - EXIT
```

Expected: smoke test passes, the sidecar signature is ad-hoc without hardened runtime, and SHA-256 is printed.

- [ ] **Step 4: Finish the feature branch and fast-forward `main`**

Use `superpowers:finishing-a-development-branch`, selecting the already authorized local merge path. From the primary worktree, fast-forward `main` to the verified feature commit and confirm both commits match:

```bash
git -C "/Users/yanqs/Documents/GitHub/vibe_coding/to do list" merge --ff-only codex/bilingual-ui
git -C "/Users/yanqs/Documents/GitHub/vibe_coding/to do list" rev-parse HEAD
git rev-parse HEAD
```

Expected: the two commit IDs are identical.

- [ ] **Step 5: Push source and move the authorized public tag**

```bash
git -C "/Users/yanqs/Documents/GitHub/vibe_coding/to do list" push origin main
git -C "/Users/yanqs/Documents/GitHub/vibe_coding/to do list" tag -f -a v1.0.0 -m 'TodoList v1.0.0' HEAD
git -C "/Users/yanqs/Documents/GitHub/vibe_coding/to do list" push --force origin refs/tags/v1.0.0
```

Expected: remote `main` and `v1.0.0` resolve to the final verified commit.

- [ ] **Step 6: Replace and verify the GitHub Release**

```bash
gh release upload v1.0.0 "desktop/src-tauri/target/release/bundle/dmg/Todo List_1.0.0_aarch64.dmg" --repo Yanqs2000/TodoList --clobber
gh release edit v1.0.0 --repo Yanqs2000/TodoList --notes-file docs/development-logs/v1.0.0-python-sqlite-desktop.md
gh release view v1.0.0 --repo Yanqs2000/TodoList --json tagName,url,assets
```

Expected: one canonical v1.0.0 DMG asset with the new digest.

- [ ] **Step 7: Update and verify Notion**

Update `TodoList 项目概览与架构`, `TodoList 项目开发索引`, and `TodoList v1.0.0 — Python SQLite 桌面架构（2026-07-16）` with bilingual UI details and the unchanged GitHub Release URL. Read all three pages back with `ntn pages get`; expected content mentions Chinese/English switching and v1.0.0.

- [ ] **Step 8: Final remote-state audit**

```bash
git fetch origin --tags
git status --short --branch
git rev-list --left-right --count origin/main...main
git rev-list -n 1 v1.0.0
git rev-parse HEAD
```

Expected: clean worktree, `0 0`, and tag/HEAD commit IDs match.
