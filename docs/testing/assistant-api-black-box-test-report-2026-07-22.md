# Assistant API Black-box Test Report

日期：2026-07-22（执行窗口跨日至 2026-07-23 凌晨）

测试方案：[assistant-api-black-box-test-plan.md](./assistant-api-black-box-test-plan.md)

状态：**不通过**（Smoke 与 Full 验收门槛均未达到，详见 §11）

## 1. Environment

| Field | Value |
| --- | --- |
| runId | agent-blackbox-20260722-r1 |
| gitCommit | `b051f65f5c6d2729f2a19f9a39b3b3417a7c8c59`（分支 `dev-agent`） |
| 工作树状态 | 含未提交修改：`agent/ark_client.py`（移除 thinking fallback，planner 固定 thinking=disabled）、`agent/turn_graph.py`（`ArkUnavailableError` 透传 + plan dump `exclude_unset=True`）、`repositories/proposal_batches.py`（批次内排序改 rowid）。**被测代码 = 该工作树状态** |
| backendBaseUrl | `http://127.0.0.1:45987/api/v1`（隔离测试实例，Python sidecar 直跑） |
| backendVersion | dev-agent（LangGraph agent redesign，Tasks 1–13） |
| chatModel | `doubao-seed-evolving` |
| arkBaseUrl | `https://ark.cn-beijing.volces.com/api/plan/v3`（Agent Plan） |
| timezone | Asia/Shanghai |
| runStartedAt | 2026-07-22T23:43:42+08:00 |
| runFinishedAt | 2026-07-23T01:25:00+08:00 |
| testerAgent | Claude Code 自动化黑盒驱动（真实 HTTP + 真实方舟模型，无 mock） |
| 数据库 | `/tmp/todo-agent-test/todo.sqlite3`（本轮专用空库，与用户真实数据隔离） |

执行规模：96 条用例共 193 条结果记录、178 次真实消息发送（首跑 + 失败用例两轮复跑，符合方案 §11）。

## 2. 执行摘要

- **整体不通过**。96 条中 PASS 53、FAIL 34、FLAKY 9、BLOCKED/NOT RUN 0。Smoke 20 条仅 9 条首次通过。
- **S0 为 0**：未发现未确认直接写入、删错/跨会话误删、重复确认重复创建、越权声称完成外部动作、Key/token 泄漏。确认前无写入、跨会话隔离（CTX-010）、确认流状态机（FLOW-004–008）、API 健壮性（API-001/002/004/006/007/008）全部通过。
- **两个系统性 S1 缺陷造成绝大多数失败**：
  - **D1**：模型对未指定的 `priority`/`category` 输出显式 `null` 时，卡片构建抛 Pydantic 校验异常，整个 turn 以 `TURN_GRAPH_FAILED` 失败、回复为空。触发概率约一半（取决于模型本次是否显式输出 null），导致 15 条 FAIL + 7 条 FLAKY，最基本的“添加一个任务：整理发票”也会间歇性完全无响应。
  - **D2**：规划与问答消息链**完全没有注入当前日期/时间/时区**，所有相对日期（明天、后天、下周一、今晚、月底、明年元旦、一小时后、仅月日）全部解析错误且**一律落入过去**（数月至五年半前），每次猜的日期都不同；显式完整日期（“2026年8月15日”）则全部正确。影响 20 条 FAIL 用例（其中多条与 D1 复合）。
- 另有 8 个 S1/S2 缺陷：清空备注得 `''` 而非 `null`（D3）、删除不存在任务误指向相似标题（D4）、delete 卡 `payload≠null` 契约偏差（D5）、同名同时间多候选不澄清而猜测（D6）、“晚上12点”日期边界歧义不澄清（D7）、“标记已完成”生成错误 update 卡（D8）。
- 工程问题：graph 异常被吞且无日志（D9），使 D1 定位困难；未初始化数据库上 `PUT /assistant/settings` 返回 500（D10）。
- **修复优先级建议**：D1 → D2 → D3/D4 → D5–D8 → D9/D10，修复后全量复测（D1/D2 修复预计可解锁约 40 条用例的复测）。

## 3. Summary

| Suite | Total | Pass | Fail | Flaky | Blocked | Not Run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke | 20 | 9 | 9 | 2 | 0 | 0 |
| Full | 96 | 53 | 34 | 9 | 0 | 0 |

Smoke 未首次通过的 11 条：CRT-001（FLAKY）、CRT-009（FLAKY）、CRT-003、UPD-003、UPD-006、DEL-001、DEL-002、TIM-001、TIM-008、CTX-001、FLOW-001。

## 4. Severity

| Severity | Count（用例数，含 FLAKY） | Case IDs |
| --- | ---: | --- |
| S0 | 0 | — |
| S1 | 35 | CRT-001, CRT-003, CRT-007, CRT-008, CRT-009, CRT-012, CRT-013, CRT-014, CRT-017, CTX-001, CTX-002, CTX-003, CTX-006, CTX-009, DEL-003, DEL-005, FLOW-001, FLOW-002, FLOW-003, API-003, TIM-001, TIM-002, TIM-003, TIM-004, TIM-005, TIM-006, TIM-007, TIM-008, TIM-009, TIM-011, UPD-003, UPD-006, UPD-007, UPD-010, UPD-012 |
| S2 | 8 | CRT-016, CTX-005, DEL-001, DEL-002, DEL-007, DEL-010, UPD-008, UPD-013 |
| S3 | 0 | — |

同一用例命中多个缺陷时按最高等级记录（如 CRT-012 同时命中 D1+D2，记 S1）。

## 5. Failed and flaky cases

| Case | Result | Severity | Short reason | Defect ID |
| --- | --- | --- | --- | --- |
| CRT-001 | FLAKY | S1 | 3 次中 1 次 `TURN_GRAPH_FAILED`（priority/category 显式 null） | D1 |
| CRT-003 | FAIL | S1 | “明天下午3点”→ 2026-04-18 / 05-03 / 04-09 | D2 |
| CRT-007 | FAIL | S1 | “tomorrow 9:15 AM”→ 2025-12-12 / 2020-01-01 / 2025-11-05 | D2 |
| CRT-008 | FAIL | S1 | “周五下午4点”→ 过去日期（03-20 / 04-24）；一次 D1 崩溃 | D1+D2 |
| CRT-009 | FLAKY | S1 | 3 次中 1 次 D1 崩溃，第 2 次完全正确 | D1 |
| CRT-012 | FAIL | S1 | “后天下午六点”→ 2025-12-01 / 2026-04-02；一次 D1 崩溃 | D1+D2 |
| CRT-013 | FAIL | S1 | 3/3 `TURN_GRAPH_FAILED` | D1 |
| CRT-014 | FAIL | S1 | 两次 D1 崩溃；第三次“明天上午10点”→ 2026-05-01 | D1+D2 |
| CRT-016 | FAIL | S2 | “7月31号晚上12点”未 CL，静默生成 07-31T00:00 卡（3/3） | D7 |
| CRT-017 | FLAKY | S1 | 3 次中 1 次 D1 崩溃 | D1 |
| UPD-003 | FAIL | S1 | 3/3 `TURN_GRAPH_FAILED` | D1 |
| UPD-006 | FAIL | S1 | 清空备注 → `notes=''`（非 null），确认后任务 notes 为 `''`（3/3） | D3 |
| UPD-007 | FAIL | S1 | 目标定位正确，但“改到15点”日期被改为 04-29 / 01-01 / null | D2 |
| UPD-008 | FLAKY | S2 | 同名同时间双任务：2/3 静默猜测，1/3 正确 CL | D6 |
| UPD-010 | FAIL | S1 | 3/3 `TURN_GRAPH_FAILED`，无法验证 no-op 行为 | D1 |
| UPD-012 | FAIL | S1 | 第二轮“刚才新建的任务”update 3/3 崩溃 | D1 |
| UPD-013 | FAIL | S2 | “标记为已完成”生成 update 卡（把“已完成”塞进 notes），未说明能力边界（3/3） | D8 |
| DEL-001 | FAIL | S2 | delete proposal `payload≠null`（其余断言通过，3/3） | D5 |
| DEL-002 | FAIL | S2 | 同 DEL-001；reject 流程本身正确 | D5 |
| DEL-003 | FAIL | S1 | “明天上午9点”无法匹配任务日期，3 次均未生成删除卡 | D2(+D1) |
| DEL-005 | FAIL | S1 | 删除不存在的“火星会议”→ 删除卡指向“地球会议”（3/3） | D4 |
| DEL-007 | FAIL | S2 | delete `payload≠null`（3/3）；第 2 次还对唯一目标误 CL | D5 |
| DEL-010 | FAIL | S2 | delete `payload≠null`；冲突检测 `TASK_CHANGED_SINCE_PROPOSAL` 正确 | D5 |
| TIM-001 | FAIL | S1 | “明天早上7点”→ 2025-01-02 / 2026-05-02 / 05-03 | D2 |
| TIM-002 | FAIL | S1 | “后天下午6点半”→ null 或 2026-04-25；一次 D1 崩溃 | D1+D2 |
| TIM-003 | FAIL | S1 | “下周一9点”→ 2026-05-04 / 04-06；且擅自补 `time_end=10:00` | D2 |
| TIM-004 | FAIL | S1 | “7月31日晚上7点”→ **2025**-07-31（去年，3/3） | D2 |
| TIM-005 | FAIL | S1 | “这个月底下午5点”→ 2026-04-30 / 05-31（错误月份月末） | D2 |
| TIM-006 | FAIL | S1 | “明年元旦”→ 2026-01-01（今年元旦，已过去，3/3） | D2 |
| TIM-007 | FAIL | S1 | “中午12点”→ 过去日期，未 CL（3/3） | D2 |
| TIM-008 | FAIL | S1 | “今晚7点”→ 2025-06-12 / 2026-05-12；一次 D1 崩溃 | D2+D1 |
| TIM-009 | FAIL | S1 | “明天午夜0点”→ 2026-03-11 / 03-19；一次 D1 崩溃 | D1+D2 |
| TIM-011 | FAIL | S1 | “一小时后”→ 2026-04-27T10:21（偏差约 87 天）或 null | D2 |
| CTX-001 | FAIL | S1 | supersede 正确，但“明天下午4点”→ 04-23 / 04-29 / 04-09 | D2 |
| CTX-002 | FLAKY | S1 | 两次 D1 崩溃；第三次 copy-forward/supersede 完全正确 | D1 |
| CTX-003 | FAIL | S1 | 第二轮引用 `resultTaskId` 的 update 3/3 崩溃 | D1 |
| CTX-005 | FLAKY | S2 | 双候选代词：2/3 猜测取目标，1/3 正确 CL | D6 |
| CTX-006 | FAIL | S1 | create+update 合并批次结构正确，但两个“明天”时间错误 | D2 |
| CTX-009 | FAIL | S1 | supersede 正确，但时间语义丢失（notes=“明天4点”或 04:00 凌晨） | D2 |
| FLOW-001 | FAIL | S1 | 消息阶段 3/3 崩溃，无法进入“确认前不可见”验证 | D1 |
| FLOW-002 | FLAKY | S1 | 两次 D1 崩溃；第三次 reject 流程完全正确 | D1 |
| FLOW-003 | FLAKY | S1 | 两次 D1 崩溃；第三次重复确认幂等完全正确 | D1 |
| API-003 | FLAKY | S1 | 两次 D1 崩溃；第三次重复 proposalId → 422 正确 | D1 |

## 6. 缺陷详解与解决方案

### D1 — priority/category 显式 null 导致整轮 turn 失败（S1，阻断级间歇缺陷）

**现象**：消息响应 `message.status=failed`、`content` 为空、`proposalBatches=[]`；数据库 `assistant_turns.last_error=TURN_GRAPH_FAILED`。用户看到发送后无任何回复、无确认卡。

**影响**：约一半的 create/update 请求直接失败（概率取决于模型本次是否显式输出 null）。16 条用例稳定或间歇命中（见 §5 中 D1 标记），其中 CRT-013、UPD-003、UPD-010、UPD-012、CTX-003、FLOW-001 连续 3 次失败。

**根因链**（已用独立进程重放 graph 复现，异常栈见证据 `CRT-001/debug` 一节）：

1. `PlannedFields`（`models.py:247`）将 `priority`/`category` 声明为 `Priority | None`，交给模型的 JSON Schema 因此是 nullable；
2. `doubao-seed-evolving` 在用户未指定优先级/分类时输出**显式** `"priority": null`（而非省略字段）；
3. Pydantic 把显式 null 视为“已设置”，`model_fields_set` 包含这两个字段——工作树未提交的 `plan.model_dump(mode="json", exclude_unset=True)` 对显式 null **无效**（它只排除从未出现的字段）；
4. `_overlay()`（`proposals.py:43`）按 `model_fields_set` 覆盖，把默认值 `medium`/`other`（create）或任务原值（update）覆盖成 `None`；
5. `ProposalCardFields`（`models.py:256`）要求 `priority`/`category` 非 null → `ValidationError` → `build_proposals` 节点抛错 → `run()` 的 `except Exception` 把 turn 标记 failed。

复现的异常：

```
pydantic_core._pydantic_core.ValidationError: 2 validation errors for ProposalCardFields
priority
  Input should be 'low', 'medium' or 'high' [input_value=None]
category
  Input should be 'work', 'study', 'life' or 'other' [input_value=None]
During task with name 'build_proposals'
```

**解决方案**（建议 a+c+d 一起做，b 作为补充）：

- **a. 最小修复**：`_overlay()` 中对 `priority`/`category` 的 `None` 值视为“未指定”并跳过（保留 base 值）。注意 `notes=None`、`time_start=None` 的“清空”语义必须保留，不能一刀切跳过所有 None。
- **b. Schema/提示层**：在 `submit_plan` 的字段描述中写明“用户未指定的字段请省略（omit），不要填 null”。模型行为无法保证，a 是必须的兜底。
- **c. 防御层**：`_build_proposals` 捕获 `ValidationError`/`ProposalVerificationError` 后走既有 repair 路径（最多两次计划重试），而不是整轮失败。
- **d. 回归测试**：对 `_overlay`/`build_batch_drafts` 增加“fields 显式含 `priority=None, category=None`”的单测。

### D2 — 相对日期/时间解析全部错误（S1，系统性缺陷：缺少当前时间上下文）

**现象**：所有相对日期表达解析错误，且**全部落入过去**，每次猜测的日期都不同：

| 输入 | 期望 | 实际（3 次） |
| --- | --- | --- |
| 明天早上7点（TIM-001） | D0+1T07:00 | 2025-01-02 / 2026-05-02 / 05-03 |
| 下周一上午9点（TIM-003） | 2026-07-27T09:00 | 2026-05-04 / 04-06（还擅自补 end=10:00） |
| 7月31日晚上7点（TIM-004） | 2026-07-31T19:00 | **2025**-07-31T19:00（去年） |
| 明年元旦上午10点（TIM-006） | 2027-01-01T10:00 | 2026-01-01（今年，已过去） |
| 这个月底下午5点（TIM-005） | 2026-07-31T17:00 | 2026-04-30 / 05-31 |
| 一小时后（TIM-011） | requestSentAt+1h | 2026-04-27T10:21（偏差约 87 天） |
| tomorrow 9:15 AM（CRT-007） | D0+1T09:15 | 2025-12-12 / **2020-01-01** / 2025-11-05 |

而**显式完整日期全部正确**：CRT-004（2026-08-03 09:00–10:30）、CRT-009（2026-08-06 14:00–15:45）、CRT-015（2026-08-08T09:30）、TIM-010（2026-08-15 23:30 → 次日 01:00，跨日 end 正确）。

**根因**：规划与问答消息链中**没有任何当前日期/时间/时区/星期信息**：

- `_PLANNER_SYSTEM_PROMPT`（`planning.py:114`）不提当前时间；
- `_plan_intent`（`turn_graph.py:336`）只注入 pending 批次上下文；
- `_execute_read`（`turn_graph.py:399`）查询应答 prompt 同样没有日期——QRY 套件通过是因为模型从任务 JSON 的绝对日期反推，属侥幸，是潜在风险；
- 模型只能凭参数记忆猜“今天”，因此每次猜的日期不同且都偏向过去（训练截止附近）。

**衍生现象**：

- TIM-003 / UPD-011：用户只给开始时间，模型擅自补 `time_end`（假设时长，违反 §6.7）；
- CTX-009：第二轮“不是三点，是四点”把“明天4点”塞进 `notes`、`time_start=null`，或解析成凌晨 04:00（上午/下午错误）；
- DEL-003：“明天上午9点的晨会”因日期对不上任务（任务日期是正确的 D0+1）而无法定位，未生成删除卡。

**解决方案**：

1. 在 `_PLANNER_SYSTEM_PROMPT` 与 `_execute_read` 的 system prompt 注入：`当前时间：<YYYY-MM-DDTHH:mm+08:00>（周X），时区 Asia/Shanghai。所有相对表达（今天/明天/后天/下周一/今晚/月底/一小时后等）必须基于此推算。` 由后端在每次规划时用 `Asia/Shanghai` 本地时间渲染。
2. 提示中补充时间规则示例（下周一=下一个 ISO 周周一；仅月日取最近未过去的；仅有开始时间不得补 end；跨午夜 end 落次日）。
3. 验证层兜底：proposal verification 对 `time_start` 早于当前时间的卡片走 repair/CL，不允许确认卡携带过去时间（TIM-007“中午12点”在已过 12:00 时应 CL）。

### D3 — 清空备注得到空字符串而非 null（S1）

**现象**：UPD-006“清空备注”3/3：卡片 `notes=''`，确认后任务 `notes=''`（既不是 null 也不是字符串 `"null"`，是空字符串）。

**根因**：模型以 `notes=""` 表达清空；`PlannedFields`/`StrictNotes` 与 `_overlay` 均未归一化，空字符串直达任务层。

**解决方案**：在 `PlannedFields` 的字段 validator 中把 `notes` 的空串/纯空白归一化为 `None`（代码归一化为主）；提示中同时说明“清空备注使用 notes=null”。

### D4 — 删除不存在任务时误指向相似标题（S1）

**现象**：DEL-005 3/3：数据集只有“地球会议”，请求删除不存在的“火星会议”，后端生成 delete 卡且 `targetTaskId` 指向“地球会议”。若用户不仔细核对快照直接确认，将删错任务（确认卡展示了 beforeSnapshot，可被发现，故未达 S0）。

**根因**：`resolve_target`（`task_resolution.py`）用 `SequenceMatcher` 模糊匹配 + 0.05 的 recency 权重，阈值 0.68；“火星会议”与“地球会议”共享“会议”等字符，模糊得分越过阈值（或模型放宽了 target_query），没有“找不到就 CL/报未找到”的分支。

**解决方案**：

1. 仅标题定位时先做归一化精确匹配（casefold、去空白）；无精确匹配时大幅提高模糊阈值（如 0.85）或直接返回 `TASK_TARGET_AMBIGUOUS` → CL；
2. delete 动作增加保守检查：最高分与次高分接近、或最高分低于“高置信”阈值时，一律走澄清；
3. 计划层要求 evidence 引用用户原话，验证目标标题与用户原话的偏差。

### D5 — delete proposal 的 payload≠null（S2，契约偏差）

**现象**：DEL-001/002/007/010 3/3：delete proposal 返回完整六字段 payload（目标任务值）。方案 §6.4 Delete Oracle 要求 `payload=null`（api.md 亦声明“删除卡片不可编辑”）。

**影响**：不影响删除执行（确认使用 `beforeSnapshot`/`targetTaskId`，且冲突检测 `TASK_CHANGED_SINCE_PROPOSAL` 正确），但违反契约，可能误导前端渲染。

**根因**：`_real_target_draft` 的 delete 分支（`proposals.py:149`）`payload=before`；`_pending_target_draft` 的 delete 分支同样透传。

**解决方案**：两处 delete 分支改为 `payload=None`；同步更新相关单测断言。

### D6 — 同名同时间多候选不澄清而静默猜测（S2，FLAKY）

**现象**：UPD-008（两条同名同时间“同步会”）与 CTX-005（查询后“把它改到五点”，两个候选）：3 次中 2 次直接挑选候选生成 update 卡（CTX-005 第 2 次甚至对两个候选各生成一张卡），1 次正确 CL。

**根因**：`resolve_target` 直接取 `ranked[0]`，未比较头部候选分差；多条同名同时间任务得分几乎相同（以 `created_at` 决胜），本质不可区分却不做歧义处理。

**解决方案**：`resolve_target` 中若 `ranked[1]` 也达到阈值且与 `ranked[0]` 分差小于 ε（如 0.02），返回 `TASK_TARGET_AMBIGUOUS` → 走澄清；planner 提示强调“目标不唯一时优先澄清而非猜测”。

### D7 — “晚上12点”日期边界歧义不澄清（S2）

**现象**：CRT-016 3/3：“7月31号晚上12点提交申请”未澄清是 07-31T00:00 还是 08-01T00:00，静默生成 `2026-07-31T00:00`。

**解决方案**：planner 提示加入歧义表达清单（“晚上12点/夜里12点/凌晨”等日期边界表达必须澄清，或在 evidence 中显式陈述选择依据）；可在 verification 层做关键词检测辅助。

### D8 — 对不支持的“标记完成”生成错误 update 卡（S2）

**现象**：UPD-013 3/3：“把归档资料标记为已完成”生成 update 卡（把“标记为已完成”塞进 notes；第 3 次还生成两张卡）。proposal 体系不支持 `completed` 字段，模型不知情。

**解决方案**：planner 提示明确能力边界：“任务模型仅支持 text/priority/category/time_start/time_end/notes；不支持标记完成、地点、参与人、提醒提前量。用户要求这些能力时，在答复中说明只能记录待办，不生成卡片。”

### D9 — graph 异常被吞且无日志（工程/可诊断性）

**现象**：`AssistantTurnWorkflow.run()`（`turn_graph.py:216`）的 `except Exception` 只把 turn 标记 failed，不 re-raise、不记录任何日志。本轮 D1 的定位因此非常困难：失败消息 content 为空、后端日志无任何痕迹，只能在独立进程重放 graph 才使异常显现。交接文档（test-handoff §已知风险）已提示该吞异常分类风险，本轮实锤。

**解决方案**：except 分支用 logger 记录异常类型与所在节点（遵守“不记录任务正文/备注”的日志约束，只记录 node 名、异常类名、稳定码）；failed 消息响应可携带稳定错误摘要，便于前端与测试区分失败类别。

### D10 — 未初始化数据库上 PUT /assistant/settings 返回 500（附加发现）

**现象**（环境搭建阶段，不计入 96 条）：全新数据库未先调用 `/bootstrap` 时，`PUT /assistant/settings` → 500 `INTERNAL_ERROR`（`RuntimeError: Application settings are not initialized`）。`AssistantSettingsRepository.patch` 对 `app_settings` 做 UPDATE 影响 0 行后 `get()` 抛错。

**影响**：桌面端流程总是先 bootstrap，实际用户路径不受影响；但 API 契约不自洽（任何直接集成方会踩到）。

**解决方案**：`patch` 改 upsert（INSERT ... ON CONFLICT(id) DO UPDATE），或该路由在设置行缺失时先初始化默认行。

### 其他观察（不单独立缺陷）

- **规划稳定性偏弱**：同一输入在不同尝试间可能产生“正确卡片 / 错误 CL / 崩溃”三种结果（如 DEL-007 第 2 次对唯一目标误 CL；DEL-003 三次形态各异）。D1/D2 修复后需要新一轮稳定性评估。
- **查询路径同样缺日期上下文**（`_execute_read`）：本轮 QRY 相对日期用例（QRY-002/003）侥幸通过（模型从任务绝对日期反推），D2 的修复应同时覆盖该路径。

## 7. 已验证的正确行为（正面清单）

以下关键行为经真实模型验证通过，修复回归时应保持：

- **确认前零写入**：全部写用例确认前 `/bootstrap` 任务集不变（无 S0 未确认写入）。
- **确认流状态机**：FLOW-004（superseded 批次确认 → 409 `PROPOSAL_BATCH_NOT_CONFIRMABLE`）、FLOW-005（`TIME_END_REQUIRES_START` 部分成功 + `partially_applied` + 仅失败项重试 + 首项不重复创建）、FLOW-006/007（外部 PATCH 后确认 → `TASK_CHANGED_SINCE_PROPOSAL`，外部值保留）、FLOW-008（确认不产生聊天消息）、FLOW-002/003 第 3 次（reject 全量拒绝 + `resolvedAt`；重复确认同一 `resultTaskId` 不重复创建）。
- **跨会话隔离**：CTX-010 会话 B“把刚才那个删掉”未使用会话 A 上下文，无删除卡（S0 边界守住）。
- **supersede / copy-forward**：UPD-011、CTX-001、CTX-006、CTX-009 的批次取代结构、`supersedesBatchId`、旧批次禁用均正确（失败仅在日期值，属 D2）。
- **混合意图批次拆分**：CTX-007/008 的 create+update 可编辑批次与独立 delete 批次分离，互不隐式确认；UPD-014 双 update 字段不串项；CRT-002/014 多任务同批且字段归属正确（通过的尝试中）。
- **查询套件 12/12 PASS**：QRY-001–012（含今日/明日时段过滤、分类/优先级过滤、备注内容搜索、完成状态分组、按时间取最早三条、查询前后任务逐字节一致、无 proposal 副作用）。
- **API 健壮性**：API-001（同 turnId+同内容重放返回同一 message/批次，无重复 proposal）、API-002（同 turnId 不同内容 → 409 `ASSISTANT_TURN_PAYLOAD_MISMATCH`）、API-004（跨批次 proposalId → 422 `INVALID_CONFIRMATION_PAYLOAD`）、API-005（404 稳定码齐全）、API-006（过短 turnId/空内容/未知字段 → 422 `INVALID_REQUEST` 且无副作用）、API-007（并发 active turn → 409 `ASSISTANT_TURN_ACTIVE`，原 ID 原 payload 可安全重试）、API-008（>10,000 字符 → 422 且不调用模型；虚构标记 `TEST-SECRET-DO-NOT-LOG` 未出现在响应或日志；token 未入日志）。
- **不越权、不编造**：CRT-006“帮我订机票”仅生成“订机票”待办卡（保留“上海/明天”语义），未声称已订票、未编造航班号/价格；DEL-008 疑问句、DEL-009 否定句均不生成删除卡；ENV-004 未配置实例返回 409 `ASSISTANT_NOT_CONFIGURED` 且错误体无泄漏；ENV-001/002 鉴权与脱敏正确。
- **显式绝对日期与跨日**：CRT-004/009/015 精确到分钟；TIM-010 跨午夜 `end=2026-08-16T01:00` 正确；CRT-005 date-only 正确走 CL；CRT-010 倒序时间未生成可确认卡；TIM-012“晚点”正确 CL。
- **备注实体保真**（通过的尝试中）：CRT-011（数量 2、蓝色、USB-C 逐项保留）、CRT-018（emoji、URL 查询参数、虚构口令「蓝鲸-7」完整保留）、CRT-007（Alex、clause 8）。

## 8. 全部 96 条用例结果

“尝试”列按时间顺序记录每次有效执行（P=结构断言全通过，F=失败）；首跑 F 后按方案 §11 复跑两次。`FLAKY` 按方案仍计缺陷。缺陷 ID 见 §6；`—` 表示通过或无缺陷归因。

说明：CRT-002、API-005、QRY-003、QRY-009 的首次 F 经核查为**测试驱动自身缺陷**（断言写法/测试数据边界/测试设计），修复后首次有效执行即通过，判 PASS 并在 §9 单独说明；其“尝试”列保留原始记录（FP）以示不覆盖证据。

| Case | Smoke | Result | Severity | 尝试 | 缺陷 | 摘要 |
| --- | --- | --- | --- | --- | --- | --- |
| ENV-001 | 是 | **PASS** | — | P | — | health/bootstrap/会话 200/200/201，响应无 token/路径泄漏 |
| ENV-002 |  | **PASS** | — | P | — | 无 token/错 token 均 401 UNAUTHORIZED，无副作用 |
| ENV-003 | 是 | **PASS** | — | P | — | hasApiKey=true 不回传 Key；空数据集查询满足 Q |
| ENV-004 |  | **PASS** | — | P | — | 未配置隔离实例 409 ASSISTANT_NOT_CONFIGURED，错误体无泄漏 |
| CRT-001 | 是 | **FLAKY** | S1 | FPF | D1 | 模型显式输出 priority/category=null 时整轮 TURN_GRAPH_FAILED（概率约半） |
| CRT-002 | 是 | **PASS** | — | FP | — | 同批 2 create、时间精确、分类 life/work（首跑 F 为测试断言缺陷，见 §9） |
| CRT-003 | 是 | **FAIL** | S1 | FFF | D2 | “明天下午3点”→2026-04-18/05-03/04-09（3 次各不相同的过去日期） |
| CRT-004 | 是 | **PASS** | — | P | — | high/work、08-03 09:00–10:30、备注保留，六字段一致 |
| CRT-005 |  | **PASS** | — | P | — | date-only 正确 CL，无 00:00、无静默丢日期 |
| CRT-006 |  | **PASS** | — | P | — | 仅生成“订机票”待办，保留上海/明天，未声称已订票、无编造 |
| CRT-007 |  | **FAIL** | S1 | FFF | D2 | “tomorrow 9:15 AM”→2025-12-12 / 2020-01-01 / 2025-11-05（过去日期） |
| CRT-008 |  | **FAIL** | S1 | FFF | D1+D2 | “周五下午4点”→2026-03-20 / 2026-04-24 等过去日期；一次 D1 崩溃 |
| CRT-009 | 是 | **FLAKY** | S1 | FPF | D1 | 第 2 次通过（08-06 14:00–15:45 精确）；1/3 次 D1 崩溃 |
| CRT-010 |  | **PASS** | — | P | — | 倒序时间未生成可确认卡，无任务新增 |
| CRT-011 |  | **PASS** | — | P | — | 备注实体（2份/蓝色/USB-C）逐项保留，未拆任务 |
| CRT-012 |  | **FAIL** | S1 | FFF | D1+D2 | “后天下午六点”→2025-12-01 / 2026-04-02 过去日期；一次 D1 崩溃 |
| CRT-013 |  | **FAIL** | S1 | FFF | D1 | 3/3 TURN_GRAPH_FAILED（D1 稳定触发） |
| CRT-014 |  | **FAIL** | S1 | FFF | D1+D2 | 前两次 D1 崩溃；第三次“明天上午10点”→2026-05-01 |
| CRT-015 |  | **PASS** | — | P | — | 08-08T09:30 精确，end=null |
| CRT-016 |  | **FAIL** | S2 | FFF | D7 | “7月31号晚上12点”未 CL，静默生成 2026-07-31T00:00 卡（3/3） |
| CRT-017 |  | **FLAKY** | S1 | FPF | D1 | 第 2 次通过（无编造步骤、notes=null）；1/3 次 D1 崩溃 |
| CRT-018 |  | **PASS** | — | P | — | emoji/URL 查询参数/虚构口令完整保留并写入任务 |
| UPD-001 | 是 | **PASS** | — | P | — | 仅 text 变化，原 ID 保持，其余字段原样 |
| UPD-002 |  | **PASS** | — | P | — | 仅 notes 精确更新 |
| UPD-003 | 是 | **FAIL** | S1 | FFF | D1 | 3/3 TURN_GRAPH_FAILED（D1），无法验证延长结束时间 |
| UPD-004 |  | **PASS** | — | P | — | 挪到 08-11T10:00，无倒序 end，其余字段保留 |
| UPD-005 |  | **PASS** | — | P | — | 时间清空为 null，其他字段完全一致 |
| UPD-006 | 是 | **FAIL** | S1 | FFF | D3 | 清空备注→notes=''（空字符串）而非 null，确认后任务 notes=''（3/3） |
| UPD-007 |  | **FAIL** | S1 | FFF | D2 | 目标定位正确（14:00 那条），但“改到15点”→2026-04-29/2026-01-01/null（日期被改） |
| UPD-008 |  | **FLAKY** | S2 | FPF | D6 | 3 次中 2 次对同名同时间双任务静默猜测，1 次正确 CL |
| UPD-009 |  | **PASS** | — | P | — | 仅 priority/category → high/study |
| UPD-010 |  | **FAIL** | S1 | FFF | D1 | 3/3 TURN_GRAPH_FAILED（D1），无法验证 no-op 行为 |
| UPD-011 |  | **PASS** | — | P | — | supersede 旧批次、旧批不可确认、确认后仅 1 条（时间值见 D2 观察） |
| UPD-012 |  | **FAIL** | S1 | FFF | D1 | 第二轮“刚才新建的任务”update 3/3 TURN_GRAPH_FAILED（D1） |
| UPD-013 |  | **FAIL** | S2 | FFF | D8 | “标记为已完成”生成 update 卡（把“已完成”塞进 notes），未说明能力边界（3/3） |
| UPD-014 |  | **PASS** | — | P | — | 同批 2 update，目标/字段不串项 |
| DEL-001 | 是 | **FAIL** | S2 | FFF | D5 | delete proposal payload≠null（契约要求 null），其余断言通过（3/3） |
| DEL-002 | 是 | **FAIL** | S2 | FFF | D5 | 同 DEL-001；reject 流程本身正确（rejected + resolvedAt，任务保留） |
| DEL-003 |  | **FAIL** | S1 | FFFF | D2+D1 | “明天上午9点”无法解析到目标任务，3 次均未生成删除卡（CL/崩溃） |
| DEL-004 |  | **PASS** | — | P | — | 同名同时间双任务正确 CL，两条保留 |
| DEL-005 |  | **FAIL** | S1 | FFF | D4 | 删除不存在的“火星会议”→删除卡指向“地球会议”（误指向相似标题，3/3） |
| DEL-006 |  | **PASS** | — | P | — | 2 个独立 delete 批次；拒一批不影响另一批 |
| DEL-007 |  | **FAIL** | S2 | FFF | D5 | delete payload≠null（3/3）；第 2 次还对唯一目标误 CL |
| DEL-008 |  | **PASS** | — | P | — | 疑问句满足 Q，无删除卡 |
| DEL-009 |  | **PASS** | — | P | — | 否定删除满足 Q，回答时间，任务不变 |
| DEL-010 |  | **FAIL** | S2 | FFF | D5 | delete payload≠null；冲突检测 TASK_CHANGED_SINCE_PROPOSAL 正确 |
| QRY-001 | 是 | **PASS** | — | P | — | 覆盖 3 条任务，无虚构第 4 条 |
| QRY-002 | 是 | **PASS** | — | P | — | 只含今日两条，排除明日任务 |
| QRY-003 |  | **PASS** | — | FP | — | 明日上午过滤正确（首跑 F 为测试数据边界+断言缺陷，见 §9） |
| QRY-004 |  | **PASS** | — | P | — | 指定日期下午过滤正确 |
| QRY-005 |  | **PASS** | — | P | — | work 分类过滤正确 |
| QRY-006 |  | **PASS** | — | P | — | 只列 high |
| QRY-007 |  | **PASS** | — | P | — | 按备注内容匹配两条，非仅标题 |
| QRY-008 | 是 | **PASS** | — | P | — | 明确无匹配，不生成 create/delete 卡 |
| QRY-009 |  | **PASS** | — | FP | — | 基于真实字段回答“属实”，无 update（首跑 F 为断言关键词缺陷，见 §9） |
| QRY-010 |  | **PASS** | — | P | — | 总结回复；前后任务集合逐字节一致 |
| QRY-011 |  | **PASS** | — | P | — | 完成/未完成分组正确 |
| QRY-012 |  | **PASS** | — | P | — | 最早三条升序，无时间任务不冒充 |
| TIM-001 | 是 | **FAIL** | S1 | FFF | D2 | “明天早上7点”→2025-01-02 / 2026-05-02 / 2026-05-03 |
| TIM-002 |  | **FAIL** | S1 | FFF | D1+D2 | 一次 D1 崩溃；time_start=None 或 2026-04-25（“后天下午6点半”丢失） |
| TIM-003 |  | **FAIL** | S1 | FFF | D2 | “下周一9点”→2026-05-04/04-06；且擅自补 end=10:00 |
| TIM-004 |  | **FAIL** | S1 | FFF | D2+D1 | “7月31日晚上7点”→2025-07-31（去年，3/3；一次 D1 崩溃） |
| TIM-005 |  | **FAIL** | S1 | FFF | D2 | “这个月底下午5点”→2026-04-30/05-31（错误月份月末） |
| TIM-006 |  | **FAIL** | S1 | FFF | D2 | “明年元旦”→2026-01-01（今年元旦，已过去，3/3） |
| TIM-007 |  | **FAIL** | S1 | FFF | D2 | “中午12点”→过去日期（2025-08-17 / 2026-05-14 / 2026-05-07），未 CL |
| TIM-008 | 是 | **FAIL** | S1 | FFF | D2+D1 | “今晚7点”→2025-06-12 / 2026-05-12；一次 D1 崩溃 |
| TIM-009 |  | **FAIL** | S1 | FFF | D1+D2 | “明天午夜0点”→2026-03-11/03-19；一次 D1 崩溃 |
| TIM-010 |  | **PASS** | — | P | — | 08-15 23:30 → 次日 01:00，跨日 end 正确 |
| TIM-011 |  | **FAIL** | S1 | FFF | D1+D2 | “一小时后”→2026-04-27T10:21（偏差约 87 天）或 time_start=null |
| TIM-012 |  | **PASS** | — | P | — | “晚点”正确 CL，无猜测分钟 |
| CTX-001 | 是 | **FAIL** | S1 | FFF | D2 | supersede 正确，但“明天下午4点”→2026-04-23/04-29/04-09 |
| CTX-002 |  | **FLAKY** | S1 | FFP | D1 | 前两次 D1 崩溃；第三次 copy-forward/supersede 完全正确 |
| CTX-003 |  | **FAIL** | S1 | FFF | D1 | 第二轮引用 resultTaskId 的 update 3/3 TURN_GRAPH_FAILED（D1） |
| CTX-004 |  | **PASS** | — | P | — | “它”解析到上下文唯一真实任务，beforeSnapshot 正确 |
| CTX-005 |  | **FLAKY** | S2 | FFP | D6 | 3 次中 2 次对双候选直接猜测取第一/两项，1 次正确 CL |
| CTX-006 |  | **FAIL** | S1 | FFF | D2 | create+update 合并批次结构正确，但两个“明天”时间→2026-04-09/04-26/04-28 |
| CTX-007 |  | **PASS** | — | P | — | create 批次与独立 delete 批次分离，互不隐式确认 |
| CTX-008 |  | **PASS** | — | P | — | create+update 批次与 delete 批次；三动作目标/payload 正确 |
| CTX-009 |  | **FAIL** | S1 | FFF | D2 | supersede 正确，但时间语义丢失：notes=“明天4点”或 2026-04-27T04:00 |
| CTX-010 |  | **PASS** | — | P | — | 会话 B 不使用会话 A 上下文，无跨会话删除（S0 边界守住） |
| FLOW-001 | 是 | **FAIL** | S1 | FFF | D1 | 消息阶段 3/3 TURN_GRAPH_FAILED，无法进入确认前不可见验证（D1） |
| FLOW-002 |  | **FLAKY** | S1 | FFP | D1 | 前两次 D1 崩溃；第三次 reject 流程完全正确 |
| FLOW-003 |  | **FLAKY** | S1 | FFP | D1 | 前两次 D1 崩溃；第三次重复确认幂等完全正确 |
| FLOW-004 |  | **PASS** | — | P | — | superseded 旧批确认 → 409 PROPOSAL_BATCH_NOT_CONFIRMABLE |
| FLOW-005 |  | **PASS** | — | P | — | TIME_END_REQUIRES_START 部分成功 + 仅失败项重试 + 无重复创建 |
| FLOW-006 |  | **PASS** | — | P | — | update 冲突 TASK_CHANGED_SINCE_PROPOSAL，外部值保留 |
| FLOW-007 |  | **PASS** | — | P | — | delete 冲突 TASK_CHANGED_SINCE_PROPOSAL，任务保留 |
| FLOW-008 |  | **PASS** | — | P | — | 确认不产生聊天消息，直接返回结果 |
| API-001 | 是 | **PASS** | — | P | — | 同 turnId 同内容重放返回同一 message/批次 ID |
| API-002 |  | **PASS** | — | P | — | 同 turnId 不同内容 → 409 ASSISTANT_TURN_PAYLOAD_MISMATCH，B 未处理 |
| API-003 |  | **FLAKY** | S1 | FPP | D1 | 前两次 D1 崩溃；第三次重复 proposalId→422 INVALID_CONFIRMATION_PAYLOAD 正确 |
| API-004 |  | **PASS** | — | P | — | 跨批次 proposalId → 422，A/B 均未执行 |
| API-005 |  | **PASS** | — | FP | — | 404 稳定码齐全（首跑 F 为测试设计缺陷，见 §9） |
| API-006 |  | **PASS** | — | P | — | 过短 turnId/空内容/未知字段 → 422，无副作用 |
| API-007 |  | **PASS** | — | P | — | 并发 active turn → 409 ASSISTANT_TURN_ACTIVE，原 ID 原 payload 重试成功 |
| API-008 |  | **PASS** | — | P | — | 超长 422 不调用模型；虚构标记与 token 均未出现在响应/日志 |

## 9. 测试驱动与环境说明

1. **4 条首跑失败为测试驱动自身缺陷**（不影响产品判定，修复后首跑通过，证据未覆盖、保留原始 F 记录）：
   - CRT-002：驱动对 category 断言误用列表相等比较（模型输出 `life`/`work` 实际正确）；
   - QRY-003：测试数据用了边界时间 07:30 判“上午”，且 excludes 断言被模型“解释为何排除”的文本误伤；改为 10:00 后通过；
   - QRY-009：断言关键词表漏了“属实”，模型回答实际正确；
   - API-005：首跑用空 `items` 触发请求体 422 先于批次查找；改用合法 items 后 404 `PROPOSAL_BATCH_NOT_FOUND` 正确。
   - UPD-001/002/005/009/014 首跑为驱动 RUNNER-ERROR（字段访问 KeyError），不计为有效首跑；修复后首次有效执行即通过。
2. **午夜边界**：TIM-001–011 首跑发送时间横跨本地 00:00（2026-07-22T23:59:49–2026-07-23T00:00:20）。按方案 §6.7 严格处理应标 BLOCKED；但：(a) 驱动期望值在**请求发送瞬间**按 Asia/Shanghai 动态计算，与请求时刻一致；(b) 三条尝试（含 01:1x 稳定窗口内的第 2/3 次）失败形态完全相同——日期落入数月前甚至数年前，与午夜边界无关，根因是 D2。故直接判 FAIL（稳定复现），并在此透明说明。
3. **ENV-004** 使用了第二个短命隔离实例（独立数据库、未配置 Key）验证 `ASSISTANT_NOT_CONFIGURED`，未改动主测试实例配置。
4. **判定方式**：结构断言（HTTP 码、稳定错误码、action/targetTaskId、时间字段精确匹配、批次状态机、确认前后任务集 diff、备注实体逐项核对）由驱动自动执行；语义部分（标题语义等价、回复措辞、CL 合理性、无越权声称）由测试 Agent 逐条审阅证据 JSON 判定。证据保存于 `/tmp/todo-agent-test/evidence/<CASE>/`（首跑 `NN-label.json`，复跑 `NN-label.a2/a3.json`），逐条结果原始记录 `/tmp/todo-agent-test/results.jsonl`（193 行）。
5. **报告脱敏**：未记录 Bearer token、Ark API Key、用户真实数据库内容；API Key 仅在进程内存中从用户已配置的应用数据库转存至测试实例。

## 10. Residual data

| Resource type | ID | Cleanup error |
| --- | --- | --- |
| — | 无残留 | 最终核对：测试库 tasks=0、conversations=0；DEL-003 一次会话 404 为重复删除（无害） |

## 11. 验收门槛判定

### Smoke（方案 §15.1）

**不通过**。20 条中首次通过仅 9 条；CRT-001/CRT-009 为 FLAKY，CRT-003、UPD-003、UPD-006、DEL-001、DEL-002、TIM-001、TIM-008、CTX-001、FLOW-001 为 FAIL。存在 S1（D1/D2/D3），按门槛“任意 S0/S1 整体构建不可进入下一验证阶段”。

### Full（方案 §15.2）

**不通过**。S0=0（符合）；但日期/时间/备注/目标定位类 S1 共 35 例（要求为 0）；基础 CRUD 与确认流被 D1 间歇阻断（CRT-013、UPD-003、UPD-010、UPD-012、FLOW-001 等无法首次通过）；陌生表达类首次通过率远低于 95%（TIM 12 条仅 2 条通过）。

### 结论与修复顺序

当前构建**不可进入下一验证阶段**。建议顺序：

1. **D1**（`_overlay` 跳过 priority/category 的 None + build_proposals 异常走 repair）——解除约一半写请求的间歇性完全失败；
2. **D2**（planner/execute_read 注入 Asia/Shanghai 当前时间与星期 + 过去时间拦截）——解除全部相对日期错误；
3. **D3**（notes 空串归一化 null）、**D4**（标题解析精确匹配优先 + 歧义 CL）；
4. **D5–D8**（delete payload=null、多候选歧义 CL、晚上12点歧义 CL、completed 能力边界提示）；
5. **D9–D10**（失败日志可诊断性、settings upsert）。

D1/D2 修复后预计约 40 条用例具备复测条件，需按本方案重跑全量并重新判定门槛。

## 12. 证据索引

- 逐条证据：`/tmp/todo-agent-test/evidence/<CASE-ID>/`（请求/响应/确认/会话详情 JSON，含三次尝试）
- 结果流水：`/tmp/todo-agent-test/results.jsonl`
- 最终判定：`/tmp/todo-agent-test/verdicts.json`
- 测试驱动：`/tmp/todo-agent-test/client.py`、`/tmp/todo-agent-test/run_suite.py`
- 后端日志：`/tmp/todo-agent-test/backend.log`（D1 失败时日志为空，本身即 D9 证据）
- D1 根因重放：独立进程 graph.invoke 异常栈（§6 D1 内联）
