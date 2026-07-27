# Core LangGraph Agent Redesign Verification and Regression Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `dev-agent` 分支上，以 2026-07-22 的 LangGraph agent 重构设计和实现为准，修复已经实测定位的后端与前端核心门禁问题，补齐高风险回归测试，并产出一份明确区分 core、packaging 与真实方舟验收范围的可审计结论。

**Architecture:** 验证分成“环境与基线、最小缺陷修复、安全回归补测、分层回归门禁、真实方舟手工验收、差异审计”六个阶段。后端保留 `AssistantTurnGraph` 只生成提议、`ProposalApplyGraph` 在确认后直接调用 task service 的双图架构；前端只修正测试 fake 和补 hook 失败恢复测试，不改变生产 API 或 UI 设计。

**Tech Stack:** Python 3.12.13、FastAPI、Pydantic、SQLite、LangGraph 1.2.9、`langgraph-checkpoint-sqlite` 3.1.0、pytest、Ruff、Pyright；本机 Node.js 26.3.0、npm 11.16.0、React 19、TypeScript 5.8、Vitest 4.1.8、Vite 7.3.2、jsdom 29.1.1。

## Global Constraints

- 当前目标分支是 `dev-agent`，制定计划时 `HEAD` 为 `b051f65`，且与 `origin/dev-agent` 同步。执行前必须重新核对，不得通过 reset、checkout 或覆盖来清理用户改动。
- `plan.md` 是本次获准创建的交接文件；执行者看到 `?? plan.md` 时应保留它，不得把它当作垃圾文件删除。
- 前端所有命令直接使用本机 Node.js 26；不要切换到 Node 18，不要改写 `package.json` 或 `package-lock.json` 的 engine/依赖来迎合旧交接说明。
- 后端只使用 `backend/.venv/bin/python` 的 Python 3.12；不要使用系统 Python 3.14。
- 自动化测试只使用 fake Ark 和固定合成文本；测试源码不得包含真实凭据、个人内容或生产数据，日志和结果不得泄漏 API Key、附件 base64、完整模型 payload 或真实消息/任务正文。
- Todo SQLite 是业务事实来源；LangGraph checkpoint 继续独立保存在 `assistant_graph.sqlite3`。本计划不合并两个数据库，也不伪造跨库事务。
- `AssistantTurnGraph` 不得写真实任务；`ProposalApplyGraph` 的确认路径不得调用模型。所有新增测试都必须维护这两个边界。
- create/update 保持同批次确认，每个 delete 保持独立批次；确认请求只允许编辑六个字段：`text`、`priority`、`category`、`time_start`、`time_end`、`notes`。
- 修复必须保留当前实现中“未提供字段”和“显式提供 `null`”的 Pydantic 兼容语义。这是避免本轮回归所需的实现约定；2026-07-22 design spec 并未把 `null` 明确定义成产品层面的通用“清字段”操作。
- 只修改本计划列出的文件。不要顺手重构、格式化或清理相邻代码。
- `ProposalFields = PlannedFields` 兼容别名仍被现有 repository 和测试使用。它与当前失败无关，本轮只记录这个计划偏差，不删除或迁移它。
- Task 14 的 PyInstaller、Tauri sidecar、签名、安装包和 `test_packaging_smoke.py` 明确不在本轮范围内；不得通过修改 packaging spec 或降低 smoke 断言来让本轮门禁变绿。只要 packaging 未验证，最终结论不得写成完整设计 `PASS`；若现有 Pyright debt 也未清零，使用 `TARGETED REPAIR PASS / PYRIGHT BASELINE FAILED / PACKAGING UNVERIFIED` 或更保守的状态。
- 未经用户另行明确授权，不执行 `git add`、`git commit`、`git push` 或创建 PR。每个任务末尾用 diff 和测试结果作为审查点。
- 任何阶段出现与本文记录不同的失败签名时，先停止扩展测试范围，保留完整输出，按最小复现定位后再继续。

---

## 1. Authoritative Inputs

执行者必须先阅读以下三份 2026-07-22 文档，不能只依赖本计划中的摘要：

1. `docs/superpowers/specs/2026-07-22-langgraph-agent-redesign-design.md`
2. `docs/superpowers/plans/2026-07-22-langgraph-agent-redesign.md`
3. `docs/superpowers/plans/2026-07-22-langgraph-agent-redesign-test-handoff.md`

其中第三份交接文档的“Commits: none”和“前端只能用 Node 18”已经过时：实现现已位于提交 `b051f65`，本轮按用户明确要求使用本机 Node 26。其余设计契约仍需与第一、第二份文档交叉核对。

## 2. Verified Starting Evidence

以下结果是在 `b051f65` 上实测得到的基线，不得写成当前修复后的结果：

| Gate | Observed result before repair | Interpretation |
|---|---:|---|
| Backend default suite | `281 passed, 20 failed, 1 skipped, 1 warning` | 后端当前不绿；skip 是 packaging smoke |
| Backend assistant slice | `195 passed, 20 failed, 1 warning` | 20 个失败都经过 mutation → proposal 路径 |
| Checkpoint + proposal service/repository | `38 passed` | checkpoint 与底层批次事务的已有 focused tests 通过 |
| Backend collection excluding packaging | `301 tests collected` | 修复前自动化基数 |
| Backend Pyright | `143 errors` | 现存 typing debt；本轮只能建立 no-new-diagnostics 差异门禁，不能宣称通过 |
| Frontend focused July-22 tests | `6 files, 46 tests passed` | Vitest 行为测试可运行 |
| Frontend full Vitest | `26 files, 176 tests passed` | 当前前端单测绿 |
| TypeScript `tsc -b` | 2 个 `TS2353` | 两个 `TodoApi` fake 仍使用已删除的单 proposal 方法名 |
| Standalone Vite build to temp dir | `98 modules transformed`, success | Vite 本身可构建；正式脚本被 TypeScript 门禁挡住 |

### Backend common root cause

20 个失败来自同一个数据语义丢失：

1. `backend/src/todo_backend/agent/turn_graph.py` 的 `_plan_intent()` 使用 `plan.model_dump(mode="json")`，把没有设置的 `PlannedFields.priority/category/...` 也写成 `null`。
2. 后续 `_build_proposals()` 再执行 `IntentPlan.model_validate(state["plan"])` 后，这些 `null` 进入 `model_fields_set`。
3. `backend/src/todo_backend/agent/proposals.py::_overlay()` 按 `model_fields_set` 合并字段，于是 create 默认值 `priority="medium"`、`category="other"` 被错误覆盖为 `None`。
4. `ProposalCardFields` 严格校验抛出 validation error；`AssistantTurnWorkflow.run()` 把 turn 标为 failed，因此 service/API 看不到 proposal batch。

最小正确修复是只在图状态序列化处增加 `exclude_unset=True`。不要修改 `_overlay()`，因为当前实现仍依靠显式 `null` 与 unset 的区别；是否把 `null` 正式定义成产品层面的通用清字段操作，应另行进入 design spec，而不是在本轮静默决定。

### Frontend formal-build blocker

以下两个 fake 仍实现旧接口：

- `frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts`
- `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts`

它们需要把 `acceptAssistantProposal` / `rejectAssistantProposal` 替换成当前 `TodoApi` 的 `confirmAssistantProposalBatch` / `rejectAssistantProposalBatch`。不需要修改 `frontend/src/shared/api/contracts.ts` 或生产 API client。

## 3. Planned File Changes

| File | Responsibility | Planned change |
|---|---|---|
| `backend/src/todo_backend/agent/turn_graph.py` | turn graph 状态序列化 | 一行修复：dump plan 时排除未设置字段 |
| `backend/tests/test_assistant_api.py` | HTTP 请求边界与不可变字段保护 | 新增 4 个参数化防篡改 case |
| `backend/tests/test_assistant_service.py` | 服务层并发、幂等与持久化 | 新增双 service 并发确认回归 |
| `frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts` | `TodoApi` test fake | 替换两个过期方法名 |
| `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts` | `TodoApi` test fake | 替换两个过期方法名 |
| `frontend/src/features/assistant/__tests__/useAssistant.test.ts` | batch hook 状态机 | 新增 confirm/reject 失败恢复测试各一条 |
| `plan.md` | 执行交接与结果记录 | 执行过程中勾选步骤，并在末尾追加真实结果 |

不应出现其他 tracked 文件变更。依赖安装可能更新被忽略的 `frontend/tsconfig.tsbuildinfo` mtime 和本地 cache；不要提交这些生成物。

## 4. Coverage Matrix

| Design contract | Primary automated evidence | Additional action in this plan |
|---|---|---|
| Turn graph 只生成 proposal，不写任务 | `test_assistant_turn_graph.py` | 修复 unset/null round-trip 后重跑全部 turn tests |
| Confirm 前 interrupt，confirm 后直接写 task | `test_assistant_apply_graph.py` | assistant slice 与 full backend 重跑 |
| Confirm 路径零模型调用 | `test_confirm_edited_batch_never_calls_ark` | full assistant slice 重跑，真实断网场景手工复核 |
| 稳定 turn/batch ID 与 retry/reopen | turn/service/checkpoint tests | assistant slice 与重启手工场景 |
| create/update 合批、delete 独立 | proposal builder tests | full assistant slice |
| partial success、失败项重试、accepted 锁定 | apply/service/API/frontend card tests | automated full gates + 手工 stale-item 场景 |
| duplicate confirm 不重复写 | existing API/apply tests | 新增两个 service 实例并发确认回归 |
| 客户端不能改 action/target/snapshot/unsupported fields | strict Pydantic wire model | 新增 4 个 HTTP 防篡改 case，并断言零 task 写入 |
| unknown/duplicate/cross-batch proposal ID 整体拒绝 | `test_duplicate_proposal_ids_reject_entire_command_before_writes`、`test_unknown_proposal_id_rejects_valid_sibling_before_writes`、`test_proposal_from_another_batch_rejects_command_before_writes` | proposal service gate 明确复跑 |
| 前端请求失败后保留卡片并解除 submitting | `useAssistant` implementation | 新增 confirm/reject 失败测试 |
| 页面刷新/进程重启恢复服务端状态 | service/checkpoint/component tests | automated reopen tests + 手工重启场景 |
| 旧单 proposal endpoints 兼容 | API compatibility tests | full backend gate |
| provider 失败后同 turn retry | `test_plan_generic_error_does_not_trigger_fallback`、`test_retry_same_turn_does_not_duplicate_messages_or_batches` | Ark client 与 service gate 联合验证；provider 类型逐类矩阵列为未关闭风险 |
| 两库初始化失败后只补 checkpoint | `test_retry_resumes_failed_review_initialization_without_duplicate_rows` | turn graph gate 明确复跑 |
| active turn 数据库并发约束 | `test_concurrent_turn_requests_receive_active_error` | service gate 明确复跑 |
| historical proposal migration | `test_migration_005_wraps_legacy_proposals_without_changing_status` | full backend gate 明确复跑 |
| accepted 后拒绝 pending sibling 不回滚 | `test_reject_changes_only_remaining_pending_items` | proposal service gate 明确复跑 |
| post-commit verify 不重放写操作 | `test_post_commit_verify_records_error_without_replaying_write` | proposal service gate 明确复跑 |
| 精确删除所属 checkpoint | `test_delete_conversation_removes_only_owned_checkpoint_threads` | service gate 明确复跑 |
| packaging | 独立 Task 14 | 本计划排除，不作为当前成功条件 |

### Explicitly Unclosed Verification Risks

这些项目必须出现在最终结果里，不能被 full core test 的绿色状态掩盖：

- `test_packaging_smoke.py`、PyInstaller hidden imports、Tauri sidecar、签名和安装包均未纳入本计划；core 通过不等于完整设计完成标准通过。
- `b051f65` 的完整 Pyright 基线实测为 143 errors；focused 基线为 turn graph + test 73 errors、API test 2 errors、service test 16 errors。本计划的一行生产修复和测试补充不能合理清理整仓 typing debt，因此本轮采用“不得新增诊断”的差异门禁，不能把 Pyright 描述为通过。
- 现有 checkpoint tests 证明 reopen/delete 和 JSON-safe，但没有直接扫描持久化 blob 以证明 API key、附件 base64、消息/任务 canary 和完整模型 payload 全部缺席；日志测试只覆盖 thinking capability event。将其记录为 security verification gap，不要虚构为已验证。
- timeout、rate limit、5xx 最终都会映射为 `ArkUnavailableError`，现有 service retry 测试覆盖统一恢复路径；但三类 provider 错误逐类注入、failed/active/checkpoint 状态矩阵尚无独立参数化 test。
- `AssistantTurnWorkflow.run()` 内部会把 graph-node exception 收敛成 failed response；现有外层异常测试不能证明所有内部异常分类都保留了 `ASSISTANT_UNAVAILABLE` 与 `TURN_GRAPH_FAILED` 的区别。
- 真实桌面手工结果只有在 runtime 能证明来自本次被测 SHA 时才有效；“文件存在”不能证明 sidecar provenance。

---

### Task 1: Establish a Reproducible Local Environment and Baseline

**Files:**
- Read: `AGENTS.md`
- Read: `README.md`
- Read: `backend/pyproject.toml`
- Read: `backend/uv.lock`
- Read: `frontend/package.json`
- Read: `frontend/package-lock.json`
- Preserve: every existing user change, including `plan.md`

**Interfaces:**
- Consumes: current `dev-agent` checkout and local Node 26 installation.
- Produces: synced backend/frontend dependencies and a recorded baseline whose failure signatures match Section 2.

- [x] **Step 1: Confirm repository identity and preserve current changes**

Run from the repository root:

```bash
pwd
git status --short --branch
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git show --stat --name-status --oneline HEAD
git diff --check HEAD^ HEAD
```

Expected:

- `pwd` ends in `/Users/yanqs/Documents/GitHub/vibe_coding/to do list`.
- branch is `dev-agent`.
- expected baseline commit is `b051f65`.
- `git diff --check HEAD^ HEAD` exits 0.
- `plan.md` may be the only untracked file. If any other change exists, list it and preserve it; do not reset or overwrite it.

If `HEAD` differs, compare `git log --oneline b051f65..HEAD` and the six planned source/test files before executing. Do not silently assume this plan still applies.

- [x] **Step 2: Verify the exact runtimes**

```bash
uv --version
backend/.venv/bin/python --version
node --version
npm --version
```

Expected at plan creation:

```text
uv 0.11.20
Python 3.12.13
v26.3.0
11.16.0
```

Python must satisfy `>=3.12,<3.13`. Node must be the local 26.x binary. If versions drift within those accepted major/minor constraints, record the actual value; do not rewrite locks merely to reproduce the patch version.

- [x] **Step 3: Sync the locked backend environment**

```bash
uv sync --directory backend --frozen --python .venv/bin/python --group dev
backend/.venv/bin/python -c "import langgraph; import langgraph.checkpoint.sqlite; print('langgraph imports: ok')"
```

Expected: frozen sync exits 0 and the import probe prints `langgraph imports: ok`. If frozen sync reports lock drift, stop and report it; do not run an unlocked dependency update.

- [x] **Step 4: Install the locked frontend dependencies with Node 26**

```bash
npm --prefix frontend ci
```

Expected: exit 0 with no manifest or lockfile diff. Do not use `npm install` and do not change Node versions.

- [x] **Step 5: Reproduce the known backend failure before editing**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_turn_graph.py \
  backend/tests/test_assistant_service.py \
  backend/tests/test_assistant_api.py -v
```

Expected baseline: 61 collected, 20 failed and 41 passed. The failures must be the mutation/proposal failures described in Section 2. If the count or exception signature differs, save the first complete traceback and re-evaluate the root cause before modifying code.

- [x] **Step 6: Reproduce the known frontend gate split before editing**

```bash
npm --prefix frontend test -- --no-color
npm --prefix frontend exec -- tsc -b frontend/tsconfig.json
```

Expected baseline:

- Vitest: 26 files / 176 tests pass.
- TypeScript: exactly two `TS2353` errors, in `useTodos-sort.test.ts` and `useTodos.test.ts`, stating that `acceptAssistantProposal` does not exist in `TodoApi`.

- [x] **Step 7: Capture the pre-edit Pyright debt instead of assuming a green baseline**

```bash
pyright_report=$(mktemp /tmp/todo-agent-pyright-before.XXXXXX.json)
pyright_status=0
backend/.venv/bin/pyright \
  --project backend/pyproject.toml \
  --pythonpath backend/.venv/bin/python \
  --outputjson >"$pyright_report" || pyright_status=$?
backend/.venv/bin/python -c \
  'import json, sys; print(json.load(open(sys.argv[1]))["summary"])' \
  "$pyright_report"
printf 'pyright_exit=%s\npyright_report=%s\n' "$pyright_status" "$pyright_report"
```

Expected at `b051f65`: non-zero exit and 143 errors. Record the actual summary and report path before any edit. This is pre-existing technical debt, not a passing gate; the task-level criterion is that the planned changes add no new Pyright diagnostic.

- [x] **Step 8: Review the baseline diff without committing**

```bash
git status --short
git diff --stat
```

Expected: no tracked source change has occurred. Dependency directories and build caches must remain ignored.

---

### Task 2: Preserve Unset Planned Fields Across the Turn-Graph Round Trip

**Files:**
- Modify: `backend/src/todo_backend/agent/turn_graph.py` in `AssistantTurnWorkflow._plan_intent()`
- Existing regression tests: `backend/tests/test_assistant_turn_graph.py`
- Existing integration regressions: `backend/tests/test_assistant_service.py`
- Existing HTTP regressions: `backend/tests/test_assistant_api.py`

**Interfaces:**
- Consumes: `IntentPlan.model_dump()` and Pydantic's `exclude_unset` semantics.
- Produces: serialized graph state that omits absent planned fields while preserving fields explicitly supplied as `null`.

- [x] **Step 1: Use an existing red regression as the TDD failure**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_turn_graph.py::test_explicit_create_never_updates_duplicate_title -vv
```

Expected before repair: FAIL because the turn finishes failed/no batch is produced after `priority` and `category` become `None`.

- [x] **Step 2: Make the single-line production fix**

Replace:

```python
"plan": plan.model_dump(mode="json"),
```

with:

```python
"plan": plan.model_dump(mode="json", exclude_unset=True),
```

Do not change `backend/src/todo_backend/agent/proposals.py::_overlay()`. `exclude_unset=True` is deliberately narrow: a missing field is omitted, while a field explicitly set to `None` remains present under the current implementation. Treat this as a compatibility regression boundary, not as a newly approved product-wide null/clear specification.

- [x] **Step 3: Verify the representative regression turns green**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_turn_graph.py::test_explicit_create_never_updates_duplicate_title -vv
```

Expected: 1 passed.

- [x] **Step 4: Verify all 20 shared failures are removed**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_turn_graph.py \
  backend/tests/test_assistant_service.py \
  backend/tests/test_assistant_api.py -v
```

Expected before adding later tests: 61 passed, 0 failed.

- [x] **Step 5: Run focused static checks on the one-line change**

```bash
backend/.venv/bin/ruff check \
  backend/src/todo_backend/agent/turn_graph.py \
  backend/tests/test_assistant_turn_graph.py
backend/.venv/bin/pyright \
  --project backend/pyproject.toml \
  --pythonpath backend/.venv/bin/python \
  backend/src/todo_backend/agent/turn_graph.py \
  backend/tests/test_assistant_turn_graph.py
```

Expected:

- Ruff exits 0.
- Pyright remains at the captured focused baseline (73 errors at `b051f65`) and reports no new diagnostic on the changed `model_dump(...)` line. Do not call this Pyright pass; record it as unchanged existing debt.

- [x] **Step 6: Review only this task's diff**

```bash
git diff -- backend/src/todo_backend/agent/turn_graph.py
git diff --check
```

Expected: exactly one semantic source line changed and whitespace check exits 0.

---

### Task 3: Add HTTP Regression Coverage for Server-Owned and Unsupported Fields

**Files:**
- Modify: `backend/tests/test_assistant_api.py` immediately after `test_invalid_confirmation_payload_returns_stable_422`
- Production contract under test: `backend/src/todo_backend/models.py::WireModel`, `ConfirmProposalItem`, and `ProposalCardFields`

**Interfaces:**
- Consumes: `POST /api/v1/assistant/proposal-batches/{batch_id}/confirm`, strict `extra="forbid"` Pydantic models, and existing `seed_batch()` / `_confirmation_payload()` helpers.
- Produces: four request-boundary regression cases proving clients cannot replace server-owned proposal metadata or add an unsupported task field.

- [x] **Step 1: Add the exact parameterized test**

Insert this test without changing production request models:

```python
@pytest.mark.parametrize(
    ("location", "field_name", "value"),
    [
        ("item", "action", "delete"),
        ("item", "targetTaskId", "attacker-selected-task"),
        ("item", "beforeSnapshot", {"text": "forged snapshot"}),
        ("payload", "completed", True),
    ],
)
def test_confirmation_rejects_server_owned_and_unsupported_fields(
    client: TestClient,
    location: str,
    field_name: str,
    value: Any,
) -> None:
    batch = seed_batch(client)
    command = _confirmation_payload(batch)
    target: dict[str, Any] = (
        command["items"][0]
        if location == "item"
        else command["items"][0]["payload"]
    )
    target[field_name] = value

    response = client.post(
        f"/api/v1/assistant/proposal-batches/{batch['id']}/confirm",
        headers=_HEADERS,
        json=command,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    with _service(client).database.transaction() as connection:
        stored = ProposalBatchesRepository().get_batch(connection, batch["id"])
        task_row = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
    assert task_row is not None
    assert int(task_row[0]) == 0
    assert stored.status == "pending"
    assert stored.proposals[0].status == "pending"
```

Why these cases are distinct:

- `action`, `targetTaskId`, and `beforeSnapshot` are server-owned metadata and are not members of `ConfirmProposalItem`.
- `completed` is not one of the six editable card fields and is rejected inside `ProposalCardFields`.
- The database assertions prove request validation happens before any task or proposal mutation.
- “请求被拒绝、零任务写入、proposal 不变”是设计不变量；`422 INVALID_REQUEST` 是当前 `WireModel`/FastAPI envelope 的兼容回归断言，不代表设计规范永远只能使用这一错误形态。
- Proposal ID 的 unknown、duplicate 和 cross-batch 保护已经由 `test_proposal_batch_service.py` 的三条 transaction-level tests 覆盖，并会在 Task 7 复跑；不要把客户端提供的 ID 当作可编辑 action/target metadata。

- [x] **Step 2: Run only the new test cases**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_api.py \
  -k confirmation_rejects_server_owned_and_unsupported_fields -vv
```

Expected after the Task 2 production fix: 4 passed. If any case reaches the service or writes a task, treat it as a security boundary failure; do not weaken the expected 422.

- [x] **Step 3: Run the complete API test module**

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_api.py -v
```

Expected: 28 passed.

- [x] **Step 4: Run focused lint and type checks**

```bash
backend/.venv/bin/ruff check backend/tests/test_assistant_api.py
backend/.venv/bin/pyright \
  --project backend/pyproject.toml \
  --pythonpath backend/.venv/bin/python \
  backend/tests/test_assistant_api.py
```

Expected:

- Ruff exits 0.
- Pyright does not exceed the focused API baseline (2 errors at `b051f65`) and adds no diagnostic attributable to the new parameterized test. Record the unchanged diagnostics rather than claiming this file is type-clean.

- [x] **Step 5: Review the test-only diff**

```bash
git diff -- backend/tests/test_assistant_api.py
git diff --check
```

Expected: one parameterized test with four cases; no production schema relaxation.

---

### Task 4: Add Cross-Service Concurrent Confirmation Idempotency Coverage

**Files:**
- Modify: `backend/tests/test_assistant_service.py` after `test_confirm_edited_batch_never_calls_ark`
- Production contracts under test: `AssistantService.confirm_proposal_batch()`, `ProposalApplyWorkflow`, `ProposalBatchExecutor`, Todo SQLite, and the SQLite checkpointer

**Interfaces:**
- Consumes: existing `PersistentServiceFactory.open()`, `seed_create_batch()`, `_confirm_stored_batch()`, and Python `threading` imports.
- Produces: a regression proving two independent service instances can confirm the same batch concurrently with exactly one task side effect and the same stored `result_task_id`.

- [x] **Step 1: Add the exact concurrency test**

```python
def test_concurrent_batch_confirmation_is_idempotent_across_services(
    persistent_service_factory: PersistentServiceFactory,
) -> None:
    first = persistent_service_factory.open(FakeArk())
    second = persistent_service_factory.open(FakeArk())
    batch = seed_create_batch(first.database, text="并发确认")
    command = _confirm_stored_batch(batch)
    gate = threading.Barrier(3)
    results: list[Any] = []
    errors: list[BaseException] = []

    def confirm(service: AssistantService) -> None:
        try:
            gate.wait(timeout=5)
            results.append(service.confirm_proposal_batch(batch.id, command))
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=confirm, args=(first,)),
        threading.Thread(target=confirm, args=(second,)),
    ]
    try:
        for thread in threads:
            thread.start()
        gate.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert len(results) == 2
        assert [result.batch.status for result in results] == ["accepted", "accepted"]
        result_task_ids = {
            result.items[0].proposal.result_task_id for result in results
        }
        assert None not in result_task_ids
        assert len(result_task_ids) == 1
        with first.database.transaction() as connection:
            task_row = connection.execute(
                "SELECT COUNT(*), MIN(text), MAX(text) FROM tasks"
            ).fetchone()
        assert task_row is not None
        assert int(task_row[0]) == 1
        assert task_row[1] == "并发确认"
        assert task_row[2] == "并发确认"
    finally:
        gate.abort()
        for thread in threads:
            thread.join(timeout=10)
        alive = [thread for thread in threads if thread.is_alive()]
        if not alive:
            second.close()
            first.close()
        assert alive == []
```

This is intentionally a service-level test rather than another same-process double-click test. Each `AssistantService` has its own in-memory locks, so correctness must come from stable IDs, SQLite transactions, persisted proposal status, and checkpoint replay.

- [x] **Step 2: Run the new concurrency test repeatedly enough to catch lock races**

Run the single case three separate times; do not hide failures with an automatic retry plugin:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_service.py::test_concurrent_batch_confirmation_is_idempotent_across_services -vv
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_service.py::test_concurrent_batch_confirmation_is_idempotent_across_services -vv
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_service.py::test_concurrent_batch_confirmation_is_idempotent_across_services -vv
```

Expected each time on the current API contract: 1 passed, two accepted responses, one task row, one non-null `result_task_id` value. “一个任务、一个 result ID、无重复副作用”是设计不变量；两次并发调用都立即返回 accepted 是当前实现的额外兼容门禁。

- [x] **Step 3: Run the complete service module**

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_service.py -v
```

Expected: 22 passed.

- [x] **Step 4: Run focused lint and type checks**

```bash
backend/.venv/bin/ruff check backend/tests/test_assistant_service.py
backend/.venv/bin/pyright \
  --project backend/pyproject.toml \
  --pythonpath backend/.venv/bin/python \
  backend/tests/test_assistant_service.py
```

Expected:

- Ruff exits 0.
- Pyright does not exceed the focused service baseline (16 errors at `b051f65`) and adds no diagnostic attributable to the new concurrency test. Record the unchanged diagnostics rather than claiming this file is type-clean.

- [x] **Step 5: Review the test-only diff**

```bash
git diff -- backend/tests/test_assistant_service.py
git diff --check
```

Expected: no production lock or retry abstraction was added; the current persistence contract is tested directly.

---

### Task 5: Restore the Frontend TypeScript Build Gate Under Local Node 26

**Files:**
- Modify: `frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts` in `fakeApi()`
- Modify: `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts` in `fakeApi()`
- Contract source: `frontend/src/shared/api/contracts.ts::TodoApi`

**Interfaces:**
- Consumes: current batch methods `confirmAssistantProposalBatch(id, input)` and `rejectAssistantProposalBatch(id)`.
- Produces: typed test fakes conforming to the current `TodoApi`; no runtime behavior change.

- [x] **Step 1: Confirm the type gate is red for the expected reason**

```bash
npm --prefix frontend exec -- tsc -b frontend/tsconfig.json
```

Expected before the edit: exactly two `TS2353` errors naming `acceptAssistantProposal`.

- [x] **Step 2: Replace the stale fake methods in both files**

Replace this pair:

```typescript
acceptAssistantProposal: vi.fn(),
rejectAssistantProposal: vi.fn(),
```

with:

```typescript
confirmAssistantProposalBatch: vi.fn(),
rejectAssistantProposalBatch: vi.fn(),
```

Make the identical replacement in both `useTodos-sort.test.ts` and `useTodos.test.ts`. Do not add the old methods back to `TodoApi`; the product migrated to batch endpoints intentionally.

- [x] **Step 3: Verify the two affected test modules still pass**

```bash
npm --prefix frontend test -- --no-color \
  src/features/tasks/hooks/__tests__/useTodos-sort.test.ts \
  src/features/tasks/hooks/__tests__/useTodos.test.ts
```

Expected: both files pass.

- [x] **Step 4: Verify the TypeScript project now builds**

```bash
npm --prefix frontend exec -- tsc -b frontend/tsconfig.json
```

Expected: exit 0 with no diagnostics.

- [x] **Step 5: Verify the official frontend build command**

```bash
npm --prefix frontend run build
```

Expected: `tsc -b && vite build` exits 0; Vite reports approximately 98 transformed modules. Bundle size notices are informational unless the command exits non-zero.

- [x] **Step 6: Review only the two fake changes**

```bash
git diff -- \
  frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts \
  frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts
git diff --check
```

Expected: four deleted stale fake entries and four replacement entries across the two files; no production code change.

---

### Task 6: Add Frontend Batch Failure-Recovery Regressions

**Files:**
- Modify: `frontend/src/features/assistant/__tests__/useAssistant.test.ts` after the successful confirm/reject cases
- Production contract under test: `frontend/src/features/assistant/hooks/useAssistant.ts::runBatchMutation`

**Interfaces:**
- Consumes: existing `fakeApi()`, `batch`, `editedItems`, `InfrastructureError`, and the hook's `confirmBatch` / `rejectBatch` methods.
- Produces: two regression tests proving a failed request keeps the persisted card visible, clears the submitting guard, returns `undefined`, and reports exactly one error.

- [x] **Step 1: Add confirmation-failure coverage**

```typescript
it('keeps the batch and clears submitting state when confirmation fails', async () => {
  const api = fakeApi();
  const error = new InfrastructureError(
    'infrastructure', 'INTERNAL_ERROR', 'Confirmation failed', 500,
  );
  api.confirmAssistantProposalBatch = vi.fn().mockRejectedValue(error);
  const onError = vi.fn();
  const { result } = renderHook(() => useAssistant(api, onError));
  await waitFor(() => expect(result.current.activeId).toBe('c1'));
  const originalBatch = result.current.proposalBatches[0];

  const response = await act(() => result.current.confirmBatch('b1', editedItems));

  expect(response).toBeUndefined();
  expect(api.confirmAssistantProposalBatch).toHaveBeenCalledWith('b1', {
    items: editedItems,
  });
  expect(result.current.proposalBatches[0]).toEqual(originalBatch);
  expect(result.current.submittingBatchIds.has('b1')).toBe(false);
  expect(onError).toHaveBeenCalledTimes(1);
  expect(onError).toHaveBeenCalledWith(error);
});
```

- [x] **Step 2: Add rejection-failure coverage**

```typescript
it('keeps the batch and clears submitting state when rejection fails', async () => {
  const api = fakeApi();
  const error = new InfrastructureError(
    'infrastructure', 'INTERNAL_ERROR', 'Rejection failed', 500,
  );
  api.rejectAssistantProposalBatch = vi.fn().mockRejectedValue(error);
  const onError = vi.fn();
  const { result } = renderHook(() => useAssistant(api, onError));
  await waitFor(() => expect(result.current.activeId).toBe('c1'));
  const originalBatch = result.current.proposalBatches[0];

  const response = await act(() => result.current.rejectBatch('b1'));

  expect(response).toBeUndefined();
  expect(api.rejectAssistantProposalBatch).toHaveBeenCalledWith('b1');
  expect(result.current.proposalBatches[0]).toEqual(originalBatch);
  expect(result.current.submittingBatchIds.has('b1')).toBe(false);
  expect(onError).toHaveBeenCalledTimes(1);
  expect(onError).toHaveBeenCalledWith(error);
});
```

These tests are expected to pass against the current production hook. If they fail, make only the minimal change inside `runBatchMutation`; do not refresh the whole conversation automatically, remove the card optimistically, or add a second error callback.

- [x] **Step 3: Run the hook module**

```bash
npm --prefix frontend test -- --no-color \
  src/features/assistant/__tests__/useAssistant.test.ts
```

Expected: 11 tests passed.

- [x] **Step 4: Run the July-22 frontend focused slice plus the two Todo hook modules**

```bash
npm --prefix frontend test -- --no-color \
  src/shared/api/__tests__/assistant-client.test.ts \
  src/features/assistant/__tests__/assistant-components.test.tsx \
  src/features/assistant/__tests__/proposal-cards.test.tsx \
  src/features/assistant/__tests__/useAssistant.test.ts \
  src/features/i18n/__tests__/translations.test.ts \
  src/app/__tests__/App.test.tsx \
  src/features/tasks/hooks/__tests__/useTodos-sort.test.ts \
  src/features/tasks/hooks/__tests__/useTodos.test.ts
```

Expected: all eight files pass. The six original July-22 files increase from 46 to 48 tests because this task adds two cases.

- [x] **Step 5: Review the test-only diff**

```bash
git diff -- frontend/src/features/assistant/__tests__/useAssistant.test.ts
git diff --check
```

Expected: exactly two failure-path tests and no production hook change when current behavior satisfies them.

---

### Task 7: Run the Layered Backend Verification Gates

**Files:**
- Verify: all `backend/src/todo_backend/agent/`, assistant service/API, repository, model, and related tests
- Exclude: `backend/tests/test_packaging_smoke.py`

**Interfaces:**
- Consumes: Tasks 2–4 changes and the frozen Python 3.12 environment.
- Produces: focused, assistant-slice, full-backend, lint, and type-check evidence.

- [x] **Step 1: Verify checkpoint and apply workflow foundations**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_agent_checkpoints.py \
  backend/tests/test_assistant_apply_graph.py \
  backend/tests/test_proposal_batch_service.py \
  backend/tests/test_proposal_batches_repository.py -v
```

Expected after adding no tests to these files: 50 passed.

- [x] **Step 2: Verify planning, target resolution, proposal building, and turn routing**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_ark_client.py \
  backend/tests/test_assistant_planning.py \
  backend/tests/test_assistant_task_resolution.py \
  backend/tests/test_assistant_proposals.py \
  backend/tests/test_assistant_turn_graph.py -v
```

Expected: 105 passed. This gate must include explicit create with duplicate title, target resolution, supersession sibling copy-forward, repair limit, retry/reopen, no task writes, and English mutation behavior.

- [x] **Step 3: Verify the complete assistant slice**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_assistant_*.py \
  backend/tests/test_agent_checkpoints.py \
  backend/tests/test_proposal_batch_service.py \
  backend/tests/test_proposal_batches_repository.py -v
```

Expected after Tasks 3 and 4: 220 passed. There must be no real Ark/network request.

- [x] **Step 4: Verify the complete backend except explicitly deferred packaging**

```bash
backend/.venv/bin/python -m pytest \
  backend/tests \
  --ignore=backend/tests/test_packaging_smoke.py -v
```

Expected: 306 passed, 0 failed. If the repository gained unrelated tests after `b051f65`, use “all collected tests passed” as the controlling condition and record the new count.

- [x] **Step 5: Run full Ruff and the Pyright no-regression gate**

```bash
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pyright \
  --project backend/pyproject.toml \
  --pythonpath backend/.venv/bin/python
```

Expected:

- Ruff exits 0 with no errors.
- Pyright is expected to remain non-zero because `b051f65` has 143 pre-existing errors. Its error count must not exceed the Task 1 baseline, and no diagnostic may be newly introduced on a changed or newly added line. Save the actual summary in the execution results and label the gate `PYRIGHT BASELINE FAILED / NO NEW DIAGNOSTICS`, never `PASS`.
- If Pyright exceeds the captured baseline, stop and repair only diagnostics introduced by this plan. Clearing the repository-wide 143-error baseline is a separate scoped task and must not be folded into these six surgical files.

- [x] **Step 6: Classify known warnings accurately**

The Starlette `TestClient` / httpx deprecation warning may still appear. Record it as a dependency-compatibility warning; do not change dependency versions in this task. A warning is not permission to describe a failed command as passed.

---

### Task 8: Run the Complete Frontend Verification Gates with Node 26

**Files:**
- Verify: all `frontend/src/**/*.test.ts` and `frontend/src/**/*.test.tsx`
- Verify: TypeScript project references and Vite production bundle

**Interfaces:**
- Consumes: Tasks 5 and 6 test changes and local Node 26.
- Produces: full Vitest, TypeScript, and official build evidence.

- [x] **Step 1: Confirm Node 26 is still active**

```bash
node --version
npm --version
```

Expected: Node 26.x and npm 11.x. Do not invoke `nvm`, `fnm`, `volta`, or another runtime switcher.

- [x] **Step 2: Run the full frontend test suite**

```bash
npm --prefix frontend test -- --no-color
```

Expected after Task 6: 26 files / 178 tests passed.

- [x] **Step 3: Run TypeScript independently for a precise diagnostic boundary**

```bash
npm --prefix frontend exec -- tsc -b frontend/tsconfig.json
```

Expected: exit 0, no diagnostics.

- [x] **Step 4: Run the official build script**

```bash
npm --prefix frontend run build
```

Expected: exit 0 after both `tsc -b` and `vite build`; Vite transforms approximately 98 modules.

- [x] **Step 5: Classify the known jsdom warning accurately**

Node 26 workers may print an experimental `localStorage` warning from jsdom. The repository's production frontend does not use a localStorage fallback. Record the warning without changing product code or suppressing the test process globally.

---

### Task 9: Perform Conditional Real-Ark Product Acceptance

**Files:**
- Read: `README.md` section “AI 助手配置”
- Read: `docs/frontend/testing.md`
- Do not edit: credentials, model defaults, packaging spec, or sidecar build scripts

**Interfaces:**
- Consumes: a runnable desktop development environment whose sidecar provenance matches the tested commit, an isolated test app-data profile, user-authorized Ark credentials entered through the settings UI, and network access for proposal generation.
- Produces: a scenario-by-scenario product verdict. This phase never blocks the automated test verdict when credentials/runtime are not authorized, but its absence must remain explicit.

- [x] **Step 1: Check whether manual acceptance is authorized and runnable**

Do not ask the user to paste a key into chat or a shell. A real test is allowed only when all conditions are true:

1. the user has explicitly authorized use of their Ark credentials and enters them through the app settings UI;
2. a runnable desktop dev sidecar exists and a build record/hash proves it was produced from the same full commit SHA and repaired source being reported;
3. Tauri is launched with a separate verification identifier so the scenarios cannot mutate the user's normal `com.todo-app.desktop` app-data database.

Read-only probe:

```bash
test -x desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin
```

Binary existence is necessary but not sufficient; record `git rev-parse HEAD` beside the sidecar build provenance. If any condition is false, do not fabricate a pass. Record one or more exact verdicts as applicable:

```text
Manual Ark acceptance: BLOCKED — credentials not authorized.
Manual desktop acceptance: BLOCKED — runnable sidecar is not available within this plan's scope.
Manual desktop acceptance: BLOCKED — runtime provenance does not match the tested checkout.
Manual desktop acceptance: BLOCKED — isolated app-data profile was not established.
```

- [ ] **Step 2: Launch the existing development runtime only when Step 1 permits it**

```bash
npm --prefix desktop ci
npm --prefix desktop run dev -- \
  --config '{"identifier":"com.todo-app.desktop.verification"}'
```

The alternate identifier causes Tauri to use separate app data instead of the user's normal `todo.sqlite3`. Confirm the verification window starts empty before creating synthetic tasks. Do not run `desktop/scripts/build-sidecar.sh` as a workaround in this plan. If launch fails because the excluded packaging work is incomplete or the inline config is unsupported, stop manual acceptance and keep the automated results separate; do not fall back to the user's production profile.

- [ ] **Step 3: Configure Ark through the settings UI**

Use the app path: header `✦` → `⚙` → enter API Key, Base URL, chat model, and audio model → save. Verify the displayed key remains masked. Do not inspect or print the SQLite key value.

- [ ] **Step 4: Execute the ten acceptance scenarios**

| # | Scenario | Exact action | Required observation |
|---:|---|---|---|
| 1 | Explicit create with duplicate title | Ensure one synthetic task named “买菜” exists, then say “新建一个买菜任务” and confirm | The same turn directly produces a create card without oral pre-confirmation; task count increases by one; the old same-title task ID/content remains unchanged |
| 2 | Low- and high-confidence target resolution | With two similar tasks, issue one underspecified update; then issue a second update containing exact title/time/category context | Low-confidence case asks only for needed disambiguation and produces no unsafe card; sufficiently reliable case may auto-select but must show the real target and complete before/after state. Do not invent a numeric threshold |
| 3 | Pending correction and sibling copy-forward | Generate one batch with two pending create/update items, then correct only one item in chat before confirming | New batch contains the corrected item plus the other pending sibling exactly once; old batch is visibly superseded and cannot be confirmed |
| 4 | Mixed create/update batch | Request one create and one update in one turn, edit one card field, press the single confirm button | Both non-delete items share one batch/button and apply once; no extra confirmation chat message is sent |
| 5 | Partial success and retry | Generate two updates, mutate one target through the normal task UI before confirming, then confirm | Unchanged target succeeds; stale target remains pending with a safe conflict error. Use a read-only API/DB inspection or network capture to prove retry contains only the failed proposal ID |
| 6 | Duplicate confirmation | Confirm a create batch, then send the same confirm request twice using a safe request replay/network tool | Exactly one real task exists. Read-only API/DB inspection proves both responses reuse the same accepted proposal and `result_task_id`; UI debounce alone is insufficient evidence |
| 7 | Restart recovery | Leave a batch pending, quit and reopen the matching-SHA verification app, revisit the conversation, then confirm | Pending card restores from the server/checkpoint and confirms without duplicate message/batch/task |
| 8 | Thinking fallback | Use an authorized endpoint that rejects extended-thinking mode once | The planning request retries with thinking disabled and succeeds; one non-sensitive capability event is observable. Cross-turn probe caching is an implementation compatibility regression, not an extra design requirement |
| 9 | Confirm with external network disconnected | Generate a create/update card while online, disconnect only external networking while keeping local WebView ↔ sidecar loopback communication, then confirm | Confirmation still succeeds locally, proving the apply path does not call Ark; no new chat message appears |
| 10 | Independent delete cards | Request deletion of two fully populated synthetic tasks | Two separate delete cards appear; each shows title, time, category, priority, notes and completion; action/target are not editable; confirming one does not resolve the other and does not call Ark |

For each scenario, record pass/fail/blocked, the user-visible result, whether task count changed, whether a new chat message appeared, and whether restart/retry was involved. Keep API/DB/network inspection read-only except for the explicit synthetic confirmation requests. Do not record the API key or message/task body beyond the fixed synthetic labels above.

- [x] **Step 5: State the manual acceptance boundary honestly**

If targeted runtime tests are green but any real-Ark scenario was not executed, use this exact final qualification:

```text
Targeted automated runtime tests passed; real-Ark product acceptance remains unverified.
```

---

### Task 10: Final Diff Audit, Result Recording, and Handoff

**Files:**
- Review: every file in Section 3
- Update: checkbox state and execution-results section in `plan.md`
- Do not stage or commit without separate authorization

**Interfaces:**
- Consumes: all automated command outputs and any authorized manual results.
- Produces: a minimal reviewed diff and a final verdict that distinguishes pass, fail, warning, skipped, and blocked.

- [x] **Step 1: Run whitespace and scope checks**

```bash
git diff --check
git diff --check HEAD^ HEAD
git diff --no-index --check /dev/null plan.md
test $? -eq 1
git status --short
git diff --stat
git diff -- \
  backend/src/todo_backend/agent/turn_graph.py \
  backend/tests/test_assistant_api.py \
  backend/tests/test_assistant_service.py \
  frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts \
  frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts \
  frontend/src/features/assistant/__tests__/useAssistant.test.ts
```

Expected:

- both tracked-file whitespace checks exit 0; the no-index `plan.md` check emits no whitespace diagnostic, returns the normal “files differ” status 1, and the following `test` exits 0;
- only the six implementation/test files above and `plan.md` are changed/untracked;
- production change is the one-line `exclude_unset=True` repair;
- all other changes are tests or typed fakes.

- [x] **Step 2: Search for stale frontend proposal API names**

```bash
rg -n '\b(?:acceptAssistantProposal|rejectAssistantProposal)\b' frontend/src
```

Expected: no matches. This search concerns the removed frontend method names; legacy backend HTTP endpoints remain intentionally covered.

- [x] **Step 3: Search for accidental scope expansion**

```bash
git diff --name-only
git status --short
```

If files outside Section 3 appear, explain exactly why they changed and revert only changes made by the executing agent when safe. Never discard a pre-existing user change.

- [x] **Step 4: Append factual execution results to this file**

Add a final `## Execution Results` section only after commands run. It must contain:

- branch and full commit SHA tested;
- actual Python, uv, Node, and npm versions;
- one row per command with exit code and exact passed/failed/skipped/warning count;
- changed file list and one-sentence reason per file;
- manual scenario status or the exact blocked/unverified wording from Task 9;
- known warnings kept separate from failures;
- final verdict: `FAIL`, `TARGETED REPAIR PASS / PYRIGHT BASELINE FAILED / PACKAGING UNVERIFIED`, or that same qualified status with `/ MANUAL BLOCKED` appended.

Do not write anticipated counts as observed results. If a count differs only because new tests were added after this plan, record the actual count and prove all collected tests passed.

- [ ] **Step 5: Offer commits only if the user authorizes them**

If the user explicitly asks for commits after reviewing the diff, use small intent-focused commits in this order:

```bash
git add backend/src/todo_backend/agent/turn_graph.py
git commit -m "fix(agent): preserve unset planned fields"

git add backend/tests/test_assistant_api.py backend/tests/test_assistant_service.py
git commit -m "test(assistant): cover confirmation safety"

git add \
  frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts \
  frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts \
  frontend/src/features/assistant/__tests__/useAssistant.test.ts
git commit -m "test(frontend): verify proposal batch recovery"

git add plan.md
git commit -m "docs: add agent redesign verification plan"
```

Without explicit authorization, do not run these commands and leave the reviewed changes unstaged.

---

## 5. Failure Triage Rules

Use the following decision order instead of changing multiple layers at once:

1. **Dependency import/collection failure:** confirm `backend/.venv/bin/python`, rerun frozen `uv sync`, and stop if the lock is inconsistent.
2. **The original 20 backend failures remain:** inspect the serialized `state["plan"]`; confirm the one-line fix is in `_plan_intent()` and no later dump reintroduces unset nulls.
3. **Only explicit-null update tests fail:** the fix was broadened too far. Restore `_overlay()` and verify `exclude_unset=True` preserves explicitly supplied `None`.
4. **Concurrent confirm creates two tasks:** keep the new regression red and inspect transaction/idempotency boundaries in `ProposalBatchExecutor`; do not solve it with a process-local lock because two service instances must be safe.
5. **HTTP tamper test reaches application logic:** keep strict models; do not accept client `action`, `targetTaskId`, `beforeSnapshot`, or `completed` and then ignore them silently.
6. **Vitest passes but build fails:** run `tsc -b` separately and fix the exact typed fake/interface mismatch; do not weaken `TodoApi` or add `as any`.
7. **Frontend failure test leaves submitting true:** inspect the `finally` branch in `runBatchMutation`; preserve the existing batch and call `onError` once.
8. **Only packaging smoke fails/skips:** report it as excluded Task 14 work. Do not modify packaging files in this plan.
9. **Real Ark unavailable:** retain automated fake-based verdict and mark manual acceptance blocked/unverified; never add a secret to test code.

## 6. Definition of Done

This plan is complete only when all applicable conditions below are true:

- [x] `turn_graph.py` serializes `IntentPlan` with `exclude_unset=True`; all existing proposal/null compatibility tests remain green, without claiming a new product-level null/clear contract.
- [x] The original 61 turn/service/API tests pass.
- [x] Four HTTP tamper cases return `422 INVALID_REQUEST`, write zero tasks, and leave the proposal pending.
- [x] Cross-service concurrent confirmation passes three direct runs and creates exactly one task/result ID.
- [x] Both `useTodos` fakes implement the current batch API names; no stale frontend method name remains.
- [x] `useAssistant` has confirm and reject failure-recovery tests, and both pass.
- [x] Full assistant slice passes (expected 220 tests at `b051f65` plus this plan's tests).
- [x] Full backend excluding packaging passes (expected 306 tests at `b051f65` plus this plan's tests).
- [x] Full Ruff passes; Pyright is rerun, remains at or below the captured 143-error baseline, adds no diagnostic on changed/new lines, and is reported as failed existing debt rather than a pass.
- [x] Full frontend Vitest passes (expected 178 tests), independent `tsc -b` passes, and official Vite build passes under local Node 26.
- [x] Warnings, skips, exclusions, and manual blockers are reported separately and accurately.
- [x] Final verdict remains qualified for the unresolved Pyright baseline and packaging exclusion; full design `PASS` is not claimed.
- [x] Final diff contains no unrelated tracked changes and `git diff --check` passes.
- [x] `plan.md` contains factual execution results rather than anticipated outcomes.
- [x] No credentials, secrets, private content, generated package, or cache file is staged.

## Execution Results

> 本节全部为 2026-07-22 实测结果，不含预期值。执行者：Claude Code 会话（用户授权"测试出现问题可以修改代码"）。

### Environment

- Branch: `dev-agent`（与 `origin/dev-agent` 同步），full SHA: `b051f65f5c6d2729f2a19f9a39b3b3417a7c8c59`（short `b051f65`）。
- 执行开始时 `git status` 仅 `?? plan.md`；`git diff --check HEAD^ HEAD` exit 0。
- uv 0.11.20；Python 3.12.13（`backend/.venv/bin/python`）；Node v26.3.0；npm 11.16.0。与计划基线逐项一致。
- `uv sync --directory backend --frozen --python .venv/bin/python --group dev` exit 0；`import langgraph; import langgraph.checkpoint.sqlite` 成功。
- `npm --prefix frontend ci` exit 0，无 manifest/lockfile 差异。

### Command Ledger

| # | Command | Exit | Result |
|---:|---|---:|---|
| 1 | pytest turn_graph + service + api（修复前基线） | 1 | 20 failed, 41 passed, 1 warning（61 collected），签名与 Section 2 一致 |
| 2 | `npm --prefix frontend test`（修复前基线） | 0 | 26 files / 176 tests passed |
| 3 | `tsc -b frontend/tsconfig.json`（修复前基线） | 1 | 恰好 2 个 TS2353（`useTodos-sort.test.ts:36`、`useTodos.test.ts:52`，`acceptAssistantProposal`） |
| 4 | Pyright 全量（修复前基线） | 1 | 143 errors, 0 warnings（/tmp/todo-agent-pyright-before.XXXXXX.json） |
| 5 | pytest `test_explicit_create_never_updates_duplicate_title`（TDD 红） | 1 | 1 failed（IndexError: list index out of range） |
| 6 | 同上（`exclude_unset=True` 一行修复后） | 0 | 1 passed |
| 7 | pytest 61-test 组（修复后首轮） | 1 | 1 failed, 60 passed — **新失败签名**：`test_pending_correction_copies_unmentioned_siblings` AssertionError `['B', 'A'] == ['A', 'B']` |
| 8 | pytest 同测试（`rowid ASC` 排序修复后） | 0 | 1 passed |
| 9 | pytest turn_graph + service + api | 0 | 61 passed, 1 warning |
| 10 | ruff（turn_graph.py + proposal_batches.py + test_assistant_turn_graph.py） | 0 | All checks passed |
| 11 | Pyright focused（上述 3 文件） | 1 | 73 errors（= turn-graph focused 基线；proposal_batches.py 贡献 0 诊断） |
| 12 | pytest 4 个防篡改 case | 0 | 4 passed |
| 13 | pytest test_assistant_api.py | 0 | 28 passed, 1 warning |
| 14 | ruff + Pyright（test_assistant_api.py） | 0 / 1 | ruff 通过；Pyright 2 errors（= API focused 基线，均为既有） |
| 15 | pytest 并发幂等测试 × 3 次独立运行 | 0 | 每次 1 passed（两次 accepted、1 个任务、1 个 result_task_id） |
| 16 | pytest test_assistant_service.py | 0 | 22 passed |
| 17 | ruff + Pyright（test_assistant_service.py） | 0 / 1 | ruff 通过；Pyright 16 errors（= service focused 基线，均为既有） |
| 18 | Vitest useTodos-sort + useTodos（fake 替换后） | 0 | 2 files / 23 tests passed |
| 19 | `tsc -b`（fake 替换后） | 0 | 无诊断 |
| 20 | `npm --prefix frontend run build` | 0 | `tsc -b && vite build` 成功 |
| 21 | Vitest useAssistant.test.ts（新增 2 条失败恢复测试） | 0 | 11 tests passed（无需修改生产 hook） |
| 22 | Vitest 8 文件聚焦切片 | 0 | 8 files / 71 tests passed（July-22 六文件 46→48） |
| 23 | Gate 1: checkpoints + apply + proposal service/repository | 0 | 50 passed |
| 24 | Gate 2: ark_client + planning + task_resolution + proposals + turn_graph | 0 | 105 passed |
| 25 | Gate 3: 完整 assistant slice | 0 | 220 passed, 1 warning |
| 26 | Gate 4: 全量后端（排除 test_packaging_smoke.py） | 0 | 306 passed, 1 warning |
| 27 | ruff `src tests` 全量 | 0 | All checks passed |
| 28 | Pyright 全量（修复后） | 1 | 143 errors, 0 warnings（= 基线；按 file/rule/message 多重集比对与修复前完全一致，10 处行号位移来自测试插入，零内容新增） |
| 29 | Vitest 全量（Node 26） | 0 | 26 files / 178 tests passed |
| 30 | `tsc -b` 独立复核 | 0 | 无诊断 |
| 31 | `npm run build` 官方构建 | 0 | 98 modules transformed |
| 32 | `rg '\b(acceptAssistantProposal\|rejectAssistantProposal)\b' frontend/src` | 1 | 无匹配 |
| 33 | `git diff --check` / `git diff --check HEAD^ HEAD` / plan.md no-index 检查 | 0 / 0 / 1 | 全部符合预期 |

### New Failure Signature Discovered During Task 2 (documented deviation)

Task 2 一行修复后出现计划未记录的新签名（`['B', 'A'] == ['A', 'B']`）。按计划全局约束停止扩展、保留输出、最小复现定位：

- 根因：`ProposalBatchesRepository.insert_batches()` 对同批所有 proposal 写入同一个 `created_at`（`now` 只取一次），而 `_list_proposals_for_batch()` 的 `ORDER BY created_at ASC, id ASC` 在时间戳相同后按 uuid5 十六进制 ID 字典序回退，与插入序（=计划序）无关。修复前 create/update 批次全部校验失败不落库，因此该缺陷从未被观察到。
- 最小修复：`ORDER BY created_at ASC, id ASC` → `ORDER BY created_at ASC, rowid ASC`（`assistant_proposals` 为普通 rowid 表，rowid 保持插入序；`INSERT OR IGNORE` 重放不改写既有行）。
- 偏差说明：`backend/src/todo_backend/repositories/proposal_batches.py` 不在 Section 3 文件清单内。该改动依据用户本轮明确授权（"如果测试出现问题，你可以进行修改代码"），且为单行、与计划一行修复同性质的序列化/读取语义修复；未触碰 `_overlay()`、请求模型或任何 UI/生产 API。
- 同类遗留（**未修复，仅记录**）：同文件 125/136/273 行的**批次间**排序使用同一 `created_at ASC, id ASC` 模式，同一 turn 的多个批次（可编辑批 + delete 批）理论上也会被 ID 字典序重排。当前无测试断言跨批次顺序，本轮未观察到相关失败，按精准修改原则不顺手修复。

### Changed Files

| File | Change | Reason |
|---|---|---|
| `backend/src/todo_backend/agent/turn_graph.py` | 1 行：`plan.model_dump(mode="json", exclude_unset=True)` | 消除 20 个共享失败（未设置字段被序列化为 null 覆盖 create 默认值） |
| `backend/src/todo_backend/repositories/proposal_batches.py` | 1 行：读回排序 `id ASC` → `rowid ASC` | 修复 Task 2 后暴露的批内 proposal 顺序错乱（上文详述） |
| `backend/tests/test_assistant_api.py` | +41 行：4 个参数化防篡改 case | 证明 action/targetTaskId/beforeSnapshot/completed 在请求边界被 422 拒绝、零任务写入、proposal 保持 pending |
| `backend/tests/test_assistant_service.py` | +57 行：跨 service 并发确认幂等测试 | 两个独立 service 实例并发确认同一批次：恰好 1 个任务、1 个 result_task_id、两次均 accepted |
| `frontend/src/features/tasks/hooks/__tests__/useTodos-sort.test.ts` | fake 方法名 ×2 替换 | 恢复 TS 构建门禁（`confirmAssistantProposalBatch`/`rejectAssistantProposalBatch`） |
| `frontend/src/features/tasks/hooks/__tests__/useTodos.test.ts` | fake 方法名 ×2 替换 | 同上 |
| `frontend/src/features/assistant/__tests__/useAssistant.test.ts` | +44 行：confirm/reject 失败恢复测试各 1 条 | 失败时保留卡片、解除 submitting、返回 undefined、onError 恰好一次（生产 hook 现状即满足，未改生产代码） |
| `plan.md` | 未跟踪文件：勾选步骤 + 本节 | 交接记录 |

`git status` 确认除上述 7 个文件与 `plan.md` 外无任何 tracked 变更；构建产物与缓存均被忽略。

### Warnings (separate from failures)

- 后端 pytest 的 1 个 warning：Starlette `TestClient`/httpx 弃用提示（依赖兼容性，未改依赖版本）。
- 前端 Vitest 在 Node 26 下输出 jsdom `ExperimentalWarning: localStorage is not available because --localstorage-file was not provided`（生产前端不使用 localStorage 回退，未抑制、未改产品代码）。
- `npm ci` 的 esbuild/fsevents allow-scripts 提示（npm 策略性提示，平台二进制经 optional dependencies 提供，Vitest/Vite 构建实测正常）。

### Manual Ark / Desktop Acceptance (Task 9)

只读探测：`desktop/src-tauri/binaries/todo-backend-aarch64-apple-darwin` 存在且可执行（mtime 2026-07-21 22:55），但无构建记录/哈希证明其产出自被测 SHA `b051f65f5c6d2729f2a19f9a39b3b3417a7c8c59` 与修复后源码（本轮修复尚未提交，任何既有二进制都不可能包含）。未启动桌面 runtime，未建立隔离 app-data profile，未请求或接收任何凭据。逐项判定：

```text
Manual Ark acceptance: BLOCKED — credentials not authorized.
Manual desktop acceptance: BLOCKED — runtime provenance does not match the tested checkout.
Manual desktop acceptance: BLOCKED — isolated app-data profile was not established.
Targeted automated runtime tests passed; real-Ark product acceptance remains unverified.
```

### Explicitly Unclosed Verification Risks (carried forward from Section 4)

- packaging（Task 14：PyInstaller hidden imports、Tauri sidecar、签名、安装包、`test_packaging_smoke.py`）未验证，core 绿不等于完整设计通过。
- Pyright 全仓 143 errors 为既有 typing debt：本轮门禁为"不新增诊断"（已满足），**不是**通过。
- checkpoint 持久化 blob 无 canary 级敏感数据扫描（API key、附件 base64、消息/任务正文、完整模型 payload 缺席证明）；日志测试仅覆盖 thinking capability event。
- provider 错误（timeout / rate limit / 5xx）逐类注入矩阵与 failed/active/checkpoint 状态矩阵无独立参数化测试。
- `AssistantTurnWorkflow.run()` 内部异常分类是否全部保留 `ASSISTANT_UNAVAILABLE` 与 `TURN_GRAPH_FAILED` 区别未被外层测试完全证明。
- `ProposalFields = PlannedFields` 兼容别名仍在使用，本轮只记录偏差、未迁移。
- 批次间排序的同类潜在问题（上文"同类遗留"）未修复。

### Final Verdict

```text
TARGETED REPAIR PASS / PYRIGHT BASELINE FAILED / PACKAGING UNVERIFIED / MANUAL BLOCKED
```

- 原始 20 个后端共享失败全部消除；61 个 turn/service/API 测试、220 个 assistant slice、306 个除 packaging 外全量后端测试通过。
- 4 个 HTTP 防篡改 case 返回 422 INVALID_REQUEST、零任务写入、proposal 保持 pending；跨 service 并发确认 3 次独立运行均恰好 1 个任务/1 个 result ID。
- 前端 178 个 Vitest 测试、独立 `tsc -b`、官方 Vite 构建在 Node 26 下全绿；无陈旧前端方法名残留。
- 未宣称完整设计 PASS：Pyright 143 既有错误未清零（无新增）、packaging 未验证、真实方舟手工验收 BLOCKED。
- 未执行 `git add`/`git commit`/`git push`；变更保留在工作区供审查（Task 10 Step 5 的提交清单在用户明确授权后可用）。

### Postscript: Rebuild & Install (2026-07-22, user-authorized, after the verification round)

用户在本轮验证之后明确要求"重新构建并安装 app"。以下为实测记录：

- `npm --prefix desktop ci` exit 0；`npm --prefix desktop run build` exit 0：`build-sidecar.sh`（`uv sync --frozen` + PyInstaller）重新生成了包含本次两处修复的 sidecar，`tauri build` 产出 `Todo List.app` 与 `Todo List_1.0.0_aarch64.dmg`（Rust release 增量编译 17.8s）。
- `npm --prefix desktop run sign:macos`：.app 与 .dmg ad-hoc 签名，`codesign --verify --deep --strict` 通过。
- 安装前已优雅退出运行中的旧版 app 并清理其 9 个残留 sidecar 进程；用户数据位于 `~/Library/Application Support/com.todo-app.desktop/todo.sqlite3`，与 app 包独立，未受影响。
- 覆盖安装至 `/Applications/Todo List.app`；已安装 sidecar 与仓库 `binaries/` 及 bundle 产物的 SHA-1 三者一致（`dc197394...`），来源可溯。
- 对已安装二进制运行 `test_packaging_smoke.py`（`TODO_BACKEND_BINARY=/Applications/.../todo-backend`，临时数据库）：首次失败于 `assert user_version == 4` —— 冒烟测试的 schema 版本钉值停留在迁移 005 之前，属重构提交遗漏同步的测试期望（二进制本身启动、健康检查、建库、优雅退出均正常）。将断言更新为 `user_version == 5`（严格钉值不变，仅对齐当前 schema）后：1 passed。
- 因此 packaging 的**运行时冒烟**已验证；Tauri 启动器与安装包分发的完整 Task 14 范围（hidden imports 全矩阵、公证、安装器流程）仍不等同于全部完成。
- 本次新增变更仅 `backend/tests/test_packaging_smoke.py` 一行（`4` → `5`）。仍未执行任何提交。
