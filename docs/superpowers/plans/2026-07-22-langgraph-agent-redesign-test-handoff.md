# LangGraph Agent Redesign Verification Handoff

Status: **UNVERIFIED per user instruction**

本文件是后续验证 agent 的可执行交接，不是检查结果。2026-07-22 的当前任务按用户要求只更新文档：没有运行 Python/Node 命令、测试、构建、类型检查、lint、import、依赖同步、代码审查或打包。不要把下列 expected behavior 写成已通过；每一步都必须记录实际命令、退出码和关键输出。

当前设计与实施计划：

- [LangGraph agent redesign 设计](../specs/2026-07-22-langgraph-agent-redesign-design.md)
- [LangGraph agent redesign 实施计划](2026-07-22-langgraph-agent-redesign.md)

## 已有证据与验证边界

Tasks 1–3 有当时的范围内验证证据：

- Task 1：数据库/model 目标测试 `14 passed in 0.25s`；目标 Pyright `0 errors`；Ruff `All checks passed!`；`git diff --check` 无输出。
- Task 2：repository 目标测试 `18 passed in 0.48s`；Ruff 和 Pyright 均为 0；独立只读 review 无 Critical/Important；`git diff --check` 无输出。
- Task 3：目标测试最终 `56 passed, 1 warning in 3.39s`；Ruff 通过；Task 3 精确范围 Pyright `0 errors`。当时 whole-services Pyright 在尚未迁移的 `services/assistant.py` 有 21 个越界错误，因此全 services 检查不是绿色；该文件后来由 Task 11 改写，但没有复跑。不能把 Tasks 1–3 的证据外推为当前整仓通过。

Tasks 4–13 全部是 **UNVERIFIED per user instruction**。相应 pytest、Ruff、Pyright、Node 测试、TypeScript/Vite 构建、import/runtime、端到端、并发与重启验证均未执行。Task 12 的临时旧 UI 不兼容已由 Task 13 源码迁移，但迁移结果同样未验证。

## 必须先解决的环境决策

### 前端：Node 18 only 与当前锁文件冲突

当前允许的运行时是 **Node 18 only**。不要安装或切换到 Node 20/22，不要修改全局 Node/npm 环境，也不要用一个更高版本 Node 偷跑后声称 Node 18 兼容。

当前 `frontend/package-lock.json` 锁定：

| 包 | 锁定版本 | 声明的 Node engine |
| --- | --- | --- |
| Vite | 7.3.2 | `^20.19.0 || >=22.12.0` |
| Vitest | 4.1.8 | `^20.0.0 || ^22.0.0 || >=24.0.0` |
| jsdom | 29.1.1 | `^20.19.0 || ^22.13.0 || >=24.0.0` |

三者均不支持 Node 18，不能直接把当前 npm 结果当作有效验证。执行任何 frontend npm 命令前，先让用户明确选择并授权 Node 18 兼容依赖处理方案（包括允许修改的 manifest/lock 文件、目标版本和锁文件更新方式）。不得静默降级、不得只改本地 `node_modules`、不得污染全局环境。若用户不授权依赖变更，前端验证保持 blocked/unverified，并记录原因。

### 后端：同步仓库本地 Python 3.12 环境

后端必须使用 `backend/.venv` 的 Python 3.12。Task 4 只运行过 `uv add --directory backend --no-sync` 来更新依赖和 lock，从未同步环境；因此后续 agent 在运行 Task 4 及以后检查前先执行：

```bash
uv sync --directory backend --python .venv/bin/python --group dev
backend/.venv/bin/python --version
```

确认输出为 Python 3.12.x。只同步仓库本地 `.venv`，不要安装全局 Python 包。若 sync 失败，先诊断 lock、平台或解释器根因，不要跳过 Task 4 直接跑后续测试。

## 执行规则

1. 先做只读 scope/diff 审查，确认没有密钥、数据库、`.venv`、`dist`、生成包或无关格式化进入范围。
2. 每个阶段按顺序运行；阶段失败立即停止。使用 `superpowers:systematic-debugging`，先建立可复现失败和根因，再做最小修复并复跑当前阶段，不要继续堆叠后续失败。
3. 修复范围超出当前设计/计划或需要改依赖时先取得用户确认，不静默扩大功能。
4. 记录每条命令的工作目录、实际输出摘要、退出码、修复 diff 和复跑结果。没有运行的检查必须明确标为 unverified。
5. 不 stage、commit、push、merge 或创建 PR，除非用户另行明确授权。

建议的初始只读检查：

```bash
git status --short
git diff --stat
git diff -- backend/pyproject.toml backend/uv.lock backend/migrations backend/src backend/tests frontend/src frontend/package.json frontend/package-lock.json README.md docs
rg -n "AgentOrchestrator|AgentTools|ProposalCard" backend/src backend/tests frontend/src
```

最后一条用于复核 Task 11/13 的旧文件删除和引用清理；命中历史注释或新组件名称时要逐项判断，不能只看命令退出码。

## 分阶段最小验证命令

以下 Python 命令均从仓库根目录运行，并在上述 `uv sync` 成功后执行。

### Phase 1 — Task 4 checkpoint store

```bash
backend/.venv/bin/python -m pytest backend/tests/test_agent_checkpoints.py -v
```

重点记录 LangGraph/SQLite import、严格 serializer、thread 创建、close/reopen、恢复和精确删除行为。

### Phase 2 — Task 5 apply workflow

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_apply_graph.py backend/tests/test_proposal_batch_service.py backend/tests/test_agent_checkpoints.py -v
```

重点记录 interrupt/resume、确认前无 task 写入、partial retry、terminal idempotency、superseded 拒绝、重开 SQLite checkpoint 和结果核验。

### Phase 3 — Tasks 6–10 agent planning and turn graph

先按任务边界运行，便于定位首个根因：

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_ark_client.py -v
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py -v
backend/.venv/bin/python -m pytest backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py -v
backend/.venv/bin/python -m pytest backend/tests/test_assistant_proposals.py backend/tests/test_assistant_planning.py backend/tests/test_proposal_batch_service.py -v
backend/.venv/bin/python -m pytest backend/tests/test_assistant_turn_graph.py backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py backend/tests/test_assistant_proposals.py backend/tests/test_assistant_apply_graph.py -v
```

重点记录 Ark `tool_choice`/thinking fallback、完整 Pydantic tool schema、显式动作策略、中英文 target resolution、完整卡片 overlay/copy-forward、stable UUID、repair 次数、附件重建、checkpoint 异常后重入、无真实 task 写入的规划边界和初始化 review 的重试。

### Phase 4 — Task 11 service and API integration

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_service.py backend/tests/test_assistant_api.py -v
```

重点记录 stable `turnId`/fingerprint、同会话 active 冲突、同 turn 进程内互斥、failed retry、terminal replay、进程关闭/重开、checkpoint cleanup ownership、batch confirm/reject、partial errors、legacy single-item compatibility、nullable wire 字段、上传/设置/转写和 lifespan close。

随后运行完整 assistant 后端切片：

```bash
backend/.venv/bin/python -m pytest backend/tests/test_assistant_ark_client.py backend/tests/test_assistant_planning.py backend/tests/test_assistant_task_resolution.py backend/tests/test_assistant_proposals.py backend/tests/test_assistant_turn_graph.py backend/tests/test_assistant_apply_graph.py backend/tests/test_assistant_service.py backend/tests/test_assistant_api.py backend/tests/test_agent_checkpoints.py backend/tests/test_proposal_batch_service.py backend/tests/test_proposal_batches_repository.py backend/tests/test_assistant_conversations.py -v
```

### Phase 5 — Tasks 12–13 frontend focused checks

只在 Node 18 兼容依赖方案得到用户确认、manifest/lock 调整完成且本地 Node 18 环境明确后运行：

```bash
npm --prefix frontend test -- src/shared/api/__tests__/assistant-client.test.ts
npm --prefix frontend test -- src/features/assistant/__tests__/useAssistant.test.ts
npm --prefix frontend test -- src/features/assistant/__tests__/proposal-cards.test.tsx src/features/assistant/__tests__/assistant-components.test.tsx src/features/assistant/__tests__/useAssistant.test.ts src/features/i18n/__tests__/translations.test.ts src/app/__tests__/App.test.tsx
```

重点记录 `crypto.randomUUID`、stable retry ID、failed-send refresh 顺序、同 render 重复点击、server-owned batch replacement、编辑确认、whole-batch reject、accepted history lock、partial retry、superseded/null legacy、delete snapshot、错误码本地化、无 confirmation chat send 和逐项 task-list 更新。

### Phase 6 — full backend, static and frontend gates

前述阶段全部通过后运行：

```bash
backend/.venv/bin/python -m pytest backend/tests --ignore=backend/tests/test_packaging_smoke.py -v
backend/.venv/bin/ruff check backend/src backend/tests
backend/.venv/bin/pyright --project backend/pyproject.toml --pythonpath backend/.venv/bin/python
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
while IFS= read -r file; do
  output=$(git diff --no-index --check -- /dev/null "$file" 2>&1 || true)
  if [ -n "$output" ]; then
    print -r -- "$output"
    exit 1
  fi
done < <(git ls-files --others --exclude-standard)
```

`test_packaging_smoke.py` 在这里被明确排除，因为 packaging/PyInstaller 不属于本交接。其他任何 skipped/xfail/warning 都要逐项解释；不得把“0 failed”简写成所有行为已覆盖。frontend full test/build 仍受 Node 18 依赖决策约束。

## 必须显式覆盖的已知风险

以下来自 Task 4–13 报告，不能因 focused tests 通过而省略：

- **LangGraph runtime/type/reopen/resume**：锁定版本的 runtime/API 与严格类型尚未验证；SQLite saver 的 close/reopen、interrupt snapshot 路由、异常后重入、apply 二次 review、turn 的 restart/resume 和 checkpoint thread 精确删除均只写了测试代码。
- **Task 4 环境**：依赖 lock 由 `uv add --no-sync` 更新，本地 `.venv` 尚无保证；先 `uv sync`。
- **Ark/OpenAI 边界**：OpenAI SDK 参数兼容性、强制 `submit_plan`、thinking unsupported 时仅一次 fallback、能力缓存、异常不重试、完整 Pydantic JSON Schema 被真实 Ark 接受均未运行验证。
- **规划/解析/提议**：中英文动作正则、否定/疑问策略、`SequenceMatcher` 边界、target 阈值、partial/full overlay、时间保留、pending reference 兼容矩阵、copy-forward、delete 隔离、supersede 归属、stable UUID、九类 proposal verification code 和 Task 5/7/8/9/10 组合未验证。
- **Task 10 graph**：`initialize_reviews` 抛错后的 checkpoint retry/re-entry、repository SQL、attachment reconstruction、最多两次 repair、确定性终止和 terminal retry 去重未验证。
- **Task 11 吞异常分类风险**：`AssistantTurnWorkflow.run()` 当前在内部捕获 graph-node exception 并返回 failed stored response。service 只能分类越过 workflow 边界的异常，无法区分内部被吞掉的 Ark failure 与其他 graph failure；必须写/运行针对性回归，不能仅依赖 HTTP happy path，也不能未经确认扩展 Task 10 行为。
- **并发与幂等**：数据库 one-active-turn、进程内 same-turn exclusion、相同 ID/相同 fingerprint replay、不同 payload 冲突、重复 confirm 不重复创建/删除、并发 batch click、partial retry 和 terminal replay 均需验证实际事务行为。
- **前后端 wire/null/partial/superseded**：`turnId` nullable legacy history、`proposalBatches` 所有权、完整六字段 payload、accepted create/update 的非 null payload/task、delete `beforeSnapshot` 与 `targetTaskId`、per-item null/error、partial pending retry、superseded history、legacy null snapshot 和稳定 HTTP/item error code 必须端到端对照。
- **刷新与状态同步**：failed send 后 detail/list refresh 顺序、server response replacement、`submittingBatchIds` 去重及 accepted items 回写 App task list 未运行。
- **旧文件删除**：Task 11 删除 `agent/orchestrator.py`、`agent/tools.py` 及对应测试；Task 13 删除旧 `ProposalCard.tsx`。仅做过文本引用搜索，没有 import/type/build/runtime 验证，动态或非源码消费者仍可能遗漏。
- **前端 UI/runtime**：TypeScript/JSX、布局响应式、键盘 focus、disabled/submitting 状态、translation 完整性及浏览器事件均未验证；当前 Vite/Vitest/jsdom 又与 Node 18 不兼容。
- **静态与整仓集成**：Tasks 4–13 从未运行 Ruff/Pyright/import/full pytest/full frontend；Task 3 当年的 whole-services Pyright 失败也必须由当前全量 Pyright 重新裁决。

## 手工验收（自动检查后，且仅在另行授权凭据时）

不要把 API Key 写入命令、文档或日志。通过现有设置 UI 配置后，最少确认：同标题 create 仍生成卡；真实任务 update 展示目标和 before/after；“刚才那个”修正会 supersede 旧 pending 卡；两项编辑后一次确认且不产生聊天回复；一项失败形成 partial success 且仅失败项可重试；重复确认不重复写；重启后未确认卡可恢复；thinking 不支持时只 fallback 一次；确认过程没有 Ark 网络调用。证据中不要记录消息/任务正文、附件内容或凭据。

## 明确不在本交接范围

Packaging/PyInstaller、sidecar binary、`backend/todo-backend.spec`、`backend/tests/test_packaging_smoke.py`、Tauri 打包、签名和安装包 smoke test 全部 **out of scope**。不要运行 PyInstaller，不要生成或替换任何包；只有用户另行明确授权后才能创建独立 packaging 任务。

Commits: none (not authorized)
