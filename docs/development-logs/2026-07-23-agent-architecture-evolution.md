# Agent 架构演进日志

日期：2026-07-23

分支：`dev-agent`

---

## 版本概览

| 版本 | 日期 | 核心特征 |
|---|---|---|
| v1.0 | 2026-07-22 | 原始 LangGraph 重设计（Tasks 1–13），单一 plan_intent 节点 |
| v1.1 | 2026-07-22–23 | D1–D10 缺陷修复（null overlay、日期注入、CL 优化），但架构不变 |
| v1.2 | 2026-07-23 | **架构演进**：analyze 思考层 + reflect 自检层 + 增强 repair 上下文 |

---

## v1.1 架构（2026-07-22 — 2026-07-23 前期）

### 图结构

```
START → load_context → plan_intent → intent_route
  → query: execute_read → verify_answer → finalize
  → mutation: resolve_targets → select_superseded → build_proposals → verify_proposals
    → valid: persist_batches → initialize_reviews → finalize
    → repair: repair_plan → plan_intent
    → error: finalize_error → finalize
  → error: finalize_error → finalize
  → repair_plan → plan_intent
```

### 核心组件

| 节点 | 职责 | 问题 |
|---|---|---|
| `plan_intent` | 一次调用完成意图识别+计划生成 | 模型无思考空间，直接输出→容易臆想 |
| `resolve_targets` | 正则+模糊匹配定位任务 | 依赖 `SequenceMatcher` 阈值 0.68，同名误指向 |
| `build_proposals` | 构建 proposal 卡片 | `_overlay` 对 null 处理不当导致 D1 崩溃 |
| `verify_proposals` | 结构化校验（时间、标题等） | 只做语法校验，不做语义校验 |
| `validate_explicit_actions` | **正则**判断"用户说了 create 就应该是 create" | 与模型判断频繁冲突（EXPLICIT_ACTION_MISMATCH） |

### 关键问题

1. **正则与模型打架**：`_ACTION_MARKERS`、`_NEGATED_ACTION`、`_QUERY_LIKE`、`_IMPERATIVE` 四个正则做本该模型做的语义判断
2. **模型闭卷考试**：一次 `submit_plan` 调用，没有先想一下的机会
3. **执行结果不回传**：模型提交 plan 后完全不知道 resolve/build/verify 的结果
4. **repair 蒙眼重试**：失败时只传 error code 字符串（"INVALID_PROPOSAL_FIELDS"），无上下文
5. **Exception swallowing**：`run()` 吞掉所有非 ArkUnavailableError 的异常，无日志

### Prompt 结构

```
_PLANNER_SYSTEM_PROMPT（固定文本，含操作规则+能力边界）
+ pending 批次上下文
+ 用户消息
→ submit_plan → 输出
```

无当前时间上下文（D2 根因）、无分析阶段、无反自检机制。

### 状态定义

```python
class AssistantTurnState(TypedDict, total=False):
    turn_id, conversation_id, user_message_id, assistant_message_id
    language, context_summary
    plan, resolved_task_ids, resolved_pending_proposal_ids
    candidate_scores, pending_batch_id
    draft_batches, response_text
    repair_count, validation_error, error_code
```

---

## v1.2 架构（2026-07-23 后期）

### 图结构

```
START → load_context → analyze_intent   ←  ✨ 新增：思考层
  │
  ├→ query:    execute_read → verify_answer → finalize
  ├→ clarify:  clarify_response → finalize   ←  ✨ 新增：CL 分支
  │
  └→ mutations: plan_intent → resolve_targets → select_superseded
       → build_proposals → verify_proposals
       → reflect →                    ←  ✨ 新增：自检层
           ├ ok:    persist_batches → initialize_reviews → finalize
           ├ repair: repair_plan → plan_intent  ←  🔧 增强：带上下文
           └ error:  finalize_error → finalize
  
  repair_plan → plan_intent   （保留后退路径）
  finalize_error → finalize
```

### 核心改造

#### Phase 1: 拆除正则，引入 `analyze_intent` 思考节点

**删除**：
- `_ACTION_MARKERS` dict（约 30 行 action 标记正则）
- `_NEGATED_ACTION` regex（否定表达式检测）
- `_QUERY_LIKE` regex（查询意图检测）
- `_IMPERATIVE` regex（命令式检测）
- `explicit_actions()` 函数
- `validate_explicit_actions()` 函数
- `_TIME_CLARIFY` regex（临时补丁）

**新增**：

`ANALYZE_PROMPT`：
```
You analyze user messages for a TodoList agent. Output one AnalysisResult.

Intent types:
- "query": factual question (what tasks do I have?)
- "clarify": incomplete/ambiguous/impossible request — ask a specific question
- "mutations": clear create/update/delete with enough info present

Rules:
- time/date is optional for creates — do NOT clarify just because no time
- do NOT use "clarify" for verbal confirmation — the card IS confirmation
- prefer "clarify" over "mutations" when in doubt
```

`AnalysisResult` 模型：
```python
class AnalysisResult(BaseModel):
    intent: Literal["query", "clarify", "mutations"]
    reasoning: str   # 为什么选这个意图？模糊点在哪？
    missing_info: str | None = None  # 需要问用户什么
```

`ArkPlanner.analyze()`：使用 tool calling (`submit_analysis`) 强制结构化输出，解析失败时 fallback 到 clarify。

**图边变更**：
```
START → load_context → analyze_intent  （替换原来的 plan_intent 作为入口）
analyze_intent → {query, clarify, mutations}  （三分支）
```

**任务上下文注入**：`_analyze_intent` 将现有任务列表注入 messages，使模型能判断 update/delete 目标是否存在。

#### Phase 2: 增强 repair 上下文

**`_build_repair_context()`** 方法：构造结构化修复上下文，包含：
- 错误码
- draft proposals 摘要（action, text, targetTaskId）
- 可用任务列表
- pending 批次信息
- 明确指令："The planner must correct the plan based on this failure context."

**修复消息格式变更**：`"Validation code: {code}"` → `"Failure context:\n{code}\n"`——模型看到的是完整上下文而非裸 error code。

**`_repair_plan` 不再清除 `draft_batches`**：保留 draft 上下文在 repair 周期中，让 `_plan_intent` 能传递完整信息。

#### Phase 3: 新增 `reflect` 自检节点

**`_reflect()` 节点**：在 `verify_proposals`（结构化校验）通过之后、`persist_batches`（持久化展示）之前，插入模型自检：

1. 将 draft_batches 摘要（action, text, target, time, notes）发给模型
2. System prompt："Review these proposal drafts. Are they correct? Respond with `{"ok": true}` or `{"ok": false, "issues": [...]}`"
3. 使用 `ark.chat()` 做轻量级调用（无需 tool calling）

**`_reflect_route()` 条件路由**：
- `ok: true` → `persist_batches`（通过，继续）
- `ok: false` + repair_count < 2 → `repair_plan`（退回修正）
- `ok: false` + repair_count >= 2 → `finalize_error`（失败降级）

**容错设计**：如果 `ark.chat()` 抛异常或 JSON 解析失败，默认为 `ok: true`——不让自检节点成为单点故障。

### 状态定义变更

```python
class AssistantTurnState(TypedDict, total=False):
    # ... (v1.1 字段全部保留)
    analysis: dict[str, Any]  # ✨ 新增：AnalysisResult 序列化
```

### 调用链对比

**v1.1（单个 create）：**
```
1× plan (submit_plan tool call for IntentPlan)
```

**v1.2（单个 create）：**
```
1× analyze (submit_analysis tool call, forced by tool_choice)
1× plan (submit_plan tool call for IntentPlan)
1× reflect (plain chat, ok: true JSON)
= 3 次模型调用
```

失败路径增加：
```
+ 最多 2× repair (submit_plan with enriched context)
+ 最多 2× reflect (plain chat)
```

### 删除的代码统计

| 文件 | 删除项 | 行数 |
|---|---|---|
| `planning.py` | `_ACTION_MARKERS`, `_NEGATED_ACTION`, `_QUERY_LIKE`, `_IMPERATIVE`, `explicit_actions()`, `validate_explicit_actions()`, `_TIME_CLARIFY` | ~60 行 |
| `planning.py` | 从 `_PLANNER_SYSTEM_PROMPT` 中删除 "For ANY create..." / "kind=query is ONLY..." 等 4 行 | ~8 行 |

### 新增的代码统计

| 文件 | 新增项 | 行数 |
|---|---|---|
| `planning.py` | `ANALYZE_PROMPT`, `AnalysisResult`, `ArkPlanner.analyze()`, `_default_analysis()` | ~50 行 |
| `turn_graph.py` | `_analyze_intent`, `_analyze_route`, `_clarify_response`, `_reflect`, `_reflect_route`, `_build_repair_context` | ~120 行 |
| `turn_graph.py` | `analysis` 字段注入、任务上下文注入、图边重组 | ~20 行 |

### 验收结果

| 测试项 | v1.1 | v1.2 |
|---|---|---|
| 全量 pytest | 326 passed | 322 passed |
| 正则校验 | 4 个正则 | **0 个** |
| CRT-001（基础创建） | 间歇 FAIL (D1) | OK |
| CRT-003（相对日期） | FAIL (D2) | OK |
| TIM-001（相对时间） | FAIL (D2) | OK |
| TIM-008（过去时间 CL） | FAIL | OK (CL) |
| UPD-006（清空备注） | FAIL (D1/D3) | OK |
| DEL-001（删除 payload null） | FAIL (D5) | OK |
| DEL-005（不存在目标） | FAIL (D4) | OK (CL) |
| CRT-016（午夜歧义） | FAIL (D7) | OK (CL) |
| UPD-013（能力边界） | FAIL (D8) | OK (CL) |
| CTX-001（supersede+日期） | FAIL (D1+D2) | OK |
| S2-002（模糊数量 CL） | FAIL（臆想） | OK (CL) |
| S2-005（不可能日期） | FAIL（创建） | OK (CL) |
| S2-015（日期格式歧义） | FAIL（猜测） | OK (CL) |

### 架构优势

1. **思考先行**：analyze 节点给了模型"先想一下"的空间，减少臆想
2. **CL 规范化**：clarify 分支让"不确定就 CL"成为显式路径，不再与正则打架
3. **双层校验**：verify（结构化）+ reflect（语义化），模型能看到自己的输出并自纠
4. **有意义的 repair**：不再传裸 error code，模型知道"哪里错了"和"有什么可用的替代方案"
5. **任务上下文感知**：analyze 节点知道自己库里有哪些任务，能判断目标是否存在
6. **零正则**：所有语义判断交给模型，系统只做结构化校验
7. **跨轮记忆**（Phase 4）：每轮 `reflect` 通过后记录操作摘要（`{round, actions, task_texts, count}`），下轮 `analyze_intent` 自动注入最近 10 轮记忆——让模型知道"刚才做了什么"
