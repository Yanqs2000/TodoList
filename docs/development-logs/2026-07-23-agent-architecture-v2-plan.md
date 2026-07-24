# Agent Architecture v2 — Think→Plan→Act→Verify 重构计划

日期：2026-07-23

版本：v2（基于当前 dev-agent 分支的 LangGraph 工作流演进）

---

## 1. 现状诊断

当前 `AssistantTurnWorkflow`（`agent/turn_graph.py`）的问题：

| 问题 | 根因 | 影响 |
|---|---|---|
| 模型在 plan_intent 节点内"闭卷考试" | prompt 固定，无分析阶段 | 不确定时瞎猜而非 CL |
| 正则 `explicit_actions` 与模型判断打架 | `_QUERY_LIKE`/`_IMPERATIVE`/`_ACTION_MARKERS` 四个正则做语义判断 | EXPLICIT_ACTION_MISMATCH 持续困扰 |
| 执行结果不回传模型 | plan 提交后系统自行 resolve/build/verify，模型不知道结果 | 无法自我纠错 |
| repair 仅传 error code | `validation_code="EXPLICIT_ACTION_MISMATCH"` 不带上下文 | 模型"蒙眼重试" |
| 跨轮无结构化记忆 | 仅 pending 批次注入 | 被纠正过的错误下一轮仍犯 |

## 2. 目标架构

```
用户输入
  │
  ▼
┌─────────────┐     clarification    ┌──────────┐
│  [analyze]  │─────────────────────→│ [respond] │──→ 回复用户（CL）
│  意图分析    │                      └──────────┘
│  完整性检查  │
│  歧义识别    │
└──────┬───────┘
       │ mutation
       ▼
┌─────────────┐
│  [plan]     │  生成结构化计划（现有 submit_plan，不变）
└──────┬──────┘
       │
       ▼
┌──────────────┐    失败 + 重试 < 2    ┌──────────┐
│  [validate]  │──────────────────────→│ [repair] │──→ 回到 plan
│  模型自校验   │                       │ 传完整    │
│  plan 合理性 │                       │ 失败上下文 │
└──────┬───────┘                       └──────────┘
       │ 通过
       ▼
┌──────────────┐
│  [execute]   │  resolve → build → verify（现有逻辑合并）
└──────┬───────┘
       │
       ▼
┌──────────────┐    失败               ┌──────────┐
│  [reflect]   │──────────────────────→│ [repair] │──→ 回到 plan
│  检查执行结果 │                       └──────────┘
│  自我评估    │
└──────┬───────┘
       │ 成功
       ▼
┌──────────────┐
│ [finalize]   │  persist + reply
└──────────────┘
```

## 3. 分阶段实施

### Phase 1: 拆除正则，引入 analyze 节点（核心改动）

**改什么**：`agent/turn_graph.py`、`agent/planning.py`

**改动**：
- 新增 `_analyze_intent` 节点：模型先分析意图，输出结构化的 `AnalysisResult`（kind: query/clarify/mutation，reasoning，missing_info，ambiguous_parts）
- `clarify` → 直接 `finalize`（回复用户，不生成卡片）
- `query` → 走现有的 `execute_read` 路径
- `mutation` → 走 `plan` → `validate` → ...
- **删除** `explicit_actions`、`_ACTION_MARKERS`、`_NEGATED_ACTION`、`_QUERY_LIKE`、`_IMPERATIVE` 五个正则——分析全部交给模型

**验收**：
- 现有 326 个单元测试不回归
- TIM-008（过去时间）正确 CL
- S2-002（模糊数量）正确 CL
- S2-005（不可能日期）正确 CL
- CRT-001（基础创建）正常生成卡片

### Phase 2: 增强 repair 上下文

**改什么**：`_planning_failure` 方法、`_repair_plan` 节点

**改动**：
- 替换 `validation_code` 从单一字符串改为结构化上下文：
  ```json
  {
    "code": "TASK_TARGET_NOT_FOUND",
    "detail": "标题'火星会议'未匹配任何任务；现有任务：地球会议、项目评审",
    "suggestion": "请确认目标标题，或使用 reference 指向 pending proposal"
  }
  ```
- 让模型在 repair 时能看到"为什么失败"而不只是"失败了"

**验收**：DEL-005（火星会议→地球会议误指向）修复后不回归

### Phase 3: 新增 reflect 节点

**改什么**：`agent/turn_graph.py`

**改动**：
- 在 execute 之后插入 `_reflect` 节点
- 把 build/verify 的结果传给模型："已为 2 个任务生成卡片，命名分别是 X 和 Y。是否有问题？"
- 模型判断是否合格 → 不合格则返回 repair（带具体问题描述）
- 合格则进入 finalize

**验收**：复合指令（S0-003 r3, S0-004 r3/r4）不再优雅降级崩溃，而是通过 reflect→repair→replan 恢复

### Phase 4: 结构化跨轮记忆

**改什么**：`agent/turn_graph.py` 的 state 定义

**改动**：
- State 新增字段 `turn_memory: list[dict]`（本轮学到了什么）
- 每次 reflect 通过后，模型可以追加 memory（"用户偏好中文任务名，不喜欢英文"）
- 下轮 analyze 时注入上一轮的 memory

**验收**：S7-001（偏好学习）观察模型是否在 3 轮后开始自动推断 `work` 分类

## 4. 不改的部分

- `submit_plan` tool schema 不变（模型仍然通过 plan→items 提交计划）
- `resolve_targets` 逻辑不变（D4/D6 修复保留）
- `_overlay` / `build_batch_drafts` 不变（D1/D5 修复保留）
- prompt 文本（D2/D7/D8 修复保留，analyze 节点用新的 prompt）
- API 契约不变（request/response 格式不变）
- DB schema 不变

## 5. 验收用例（10 条核心）

以下用例必须在每个 Phase 后全部通过：

| ID | 场景 | 验证点 |
|---|---|---|
| CRT-001 | 基础创建 | 正常生成卡片 |
| CRT-003 | 相对日期 | 明天下午3点→日期正确 |
| TIM-001 | 相对时间 | 明天早上7点→时间正确 |
| TIM-008 | 过去时间 | 今晚7点(已过)→正确CL |
| UPD-006 | 清空备注 | notes=null |
| DEL-001 | 删除payload | payload=null |
| DEL-005 | 不存在目标 | CL而非误指向 |
| CRT-016 | 午夜歧义 | CL而非静默 |
| UPD-013 | 能力边界 | CL说明限制 |
| S2-002 | 模糊数量 | CL询问数量 |

## 6. 执行方式

- Phase 1 改动最大（新增节点 + 删正则），用 **1 个 subagent** 执行，TDD
- Phase 2-4 改动较小，各用 **1 个 subagent**，并行或顺序执行
- 每个 Phase 完成后跑全量 pytest + ruff + 10 条验收用例
