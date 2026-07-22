# TodoList Agent 可靠性重构设计

日期：2026-07-22

分支：dev-agent

状态：已确认，可进入实施计划

## 1. 背景

当前助手没有使用 LangChain 或 LangGraph，而是基于 OpenAI SDK 兼容接口调用火山方舟，并在后端实现简化的 function-calling 循环：

```text
模型 → 工具调用 → 执行工具 → 回填结果 → 再调用模型
```

该循环没有独立计划阶段和最终验证阶段，模型扩展思考也被关闭。由此产生的主要问题是：

- 新建与修改主要由模型自由选择工具，缺少确定性的意图约束和写操作结果验证。
- 模型可能先在对话中询问一次，再生成确认卡，造成重复确认。
- 修改、删除卡片不能充分展示目标任务和前后差异，用户难以及时发现选错对象。
- pending 提议上下文不完整，无法稳定处理“把刚才那个改成四点”等修正。
- 单字段时间更新可能清空整段时间；无效工具参数可能让消息长期停留在处理中。
- 批量任务逐卡确认、失败重试可能生成重复消息或重复提议。

## 2. 目标与非目标

### 2.1 目标

1. 用显式的“计划—定位—生成提议—验证”和“确认—执行—验证”流程替代开放式工具循环。
2. 明确区分查询、新建、修改和删除；降低模型误选写操作及误选目标的概率。
3. 明确写操作只确认一次：模型不做口头预确认，用户直接在确认卡中检查或编辑，然后点击按钮执行。
4. 同一轮的新建和修改合并为一个确认批次；删除因风险更高，每个任务单独确认。
5. 确认后由后端直接校验并调用任务服务写入，不再经过第二次模型判断。
6. 支持多轮修正、批次取代、部分成功、幂等重试、并发冲突检测和服务重启续跑。
7. 提高可测试性，使自然语言行为、图节点、持久化恢复和最终数据库结果都可独立验证。

### 2.2 非目标

- 不取消写操作确认，不允许模型绕过确认直接修改真实任务。
- 不引入 LangChain 高层 Agent、通用自治任务系统或新的外部工具能力。
- 不改动任务领域模型中与本次 Agent 可靠性无关的功能。
- 不新增多 provider 抽象、联网搜索、会话分支或跨设备同步。
- 不在本次重构中改变现有附件、语音和文档能力的产品范围。

## 3. 已确认的产品规则

### 3.1 确认规则

- 清晰的新建或修改请求直接生成确认卡，不先回复“是否确认”。
- 同一轮产生的所有新建和修改项组成一个批次，只显示一个确认按钮。
- 每个删除项使用独立确认卡和独立确认按钮，不能与其他写操作合并确认。
- 新建和修改卡片允许编辑标题、优先级、分类、开始时间、结束时间和备注等受支持字段。
- 删除卡片只展示完整目标信息，不允许把删除操作编辑成其他目标或操作。
- 点击确认按钮后，前端将编辑后的完整字段提交给后端；后端直接写入，无需用户发送聊天回复，也不再次调用模型。

### 3.2 批量失败规则

- 批次内每个项目独立事务执行。
- 成功项立即生效并锁定为已接受；失败项保持待确认并展示安全、可修正的错误。
- 批次状态变为“部分成功”后，用户可编辑失败项，再点击“重新确认剩余项”。
- 重复点击或网络重试不得重复创建、重复修改或重复删除任务。

### 3.3 多轮修正规则

- 用户修正尚未确认的提议时，创建一个新批次，旧批次标记为 `superseded` 并保留审计关系。
- 若旧批次含多个 pending 项而用户只修正其中一项，新批次确定性带入其余未决项；修正项覆盖、未提及项原样延续，不能因取代整个旧批次而丢失 sibling proposal。
- 只有最新批次可以确认；被取代的批次折叠展示且确认按钮禁用。
- 新建提议接受后回填真实任务 ID，后续“修改刚才新建的任务”能够定位真实任务。

### 3.4 目标选择规则

- 明确出现“新建、添加、记一个”等新建表达时，即使存在同名任务，也按新建处理。
- 修改和删除必须先定位真实任务，不能只凭模型直接给出任务 ID。
- 多个候选任务同时匹配时，按标题相似度、时间、分类和最近上下文综合评分，自动选择最高分候选，并在卡片中完整展示目标。
- 最高分仍低于可靠阈值时，只询问定位所必需的信息，不生成可能指向错误任务的提议。

## 4. 总体架构

采用 LangGraph 构建两个职责隔离的状态图，同时保留现有 OpenAI SDK/火山方舟客户端，不采用 LangChain 高层 Agent：

```text
用户消息
  │
  ▼
AssistantTurnGraph
加载上下文 → 计划意图 → 定位任务 → 生成提议 → 验证 → 返回消息与确认卡
                                                    │
                                                    ▼
                                              用户编辑并确认
                                                    │
                                                    ▼
ProposalApplyGraph
加载批次 → 等待审核 → 后端校验 → 逐项执行 → 回读验证 → 返回执行结果
```

两张图的边界如下：

- `AssistantTurnGraph` 每条用户消息运行一次，负责理解、查询、目标定位、提议生成和提议验证，绝不写真实任务。
- `ProposalApplyGraph` 每个确认单元运行一次，负责暂停等待用户审核、接收卡片编辑结果、调用现有任务 service 写入并验证结果。
- `AssistantTurnGraph` 成功保存批次后启动对应的 `ProposalApplyGraph`，让它执行到 `interrupt_review` 并持久化暂停点，然后才把确认卡返回前端。
- Todo SQLite 继续作为业务数据唯一事实来源。
- 新增独立的 `assistant_graph.sqlite3` 保存 LangGraph checkpoint，避免图运行状态与任务表相互耦合。
- 对话轮次使用 `turn:{turn_id}` 作为 graph thread ID；确认批次使用 `proposal:{batch_id}`。

LangGraph 的 `StateGraph`、checkpointer、`thread_id`、`interrupt()` 和 `Command(resume=...)` 能直接覆盖上述持久化与人工审核流程。恢复时中断节点会从头重新执行，因此该节点在 `interrupt()` 前不得产生副作用，后续写操作也必须幂等。参考：[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[SQLite checkpointer](https://docs.langchain.com/oss/python/integrations/checkpointers/index)。

后端新增直接依赖：

- `langgraph`
- `langgraph-checkpoint-sqlite`

具体版本在实施时根据 Python 3.12 环境和锁文件解析结果固定，不在设计阶段预设未经验证的版本号。

## 5. AssistantTurnGraph 设计

### 5.1 状态

图状态至少包含：

- `conversation_id`、`turn_id`、用户消息 ID 和助手消息 ID。
- 当前消息、未决批次和最近接受/拒绝事件的业务记录 ID，以及有大小上限的结构化上下文摘要；需要完整正文的节点按 ID 从业务库读取。
- 结构化 `IntentPlan`。
- 候选任务、候选评分和最终选中目标。
- 待生成的 proposal drafts。
- 验证错误、修复次数和最终回复。

checkpoint 只存标识符、结构化计划和运行状态，不保存 API key、附件 base64 或可由业务库重新读取的大段内容。

### 5.2 节点与路由

```text
load_context
  → plan_intent
  → route_intent
      ├─ query
      │    → execute_read → verify_answer → finalize
      └─ mutation
           → resolve_targets
           → supersede_pending
           → build_proposals
           → verify_proposals
                ├─ ok → persist_batches → finalize
                ├─ repairable → repair_plan → verify_proposals
                └─ unrepairable → finalize_error
```

节点职责：

- `load_context`：从业务库重建消息、任务和完整 pending 批次上下文；接受、拒绝和取代事件均进入摘要。
- `plan_intent`：模型只能输出固定结构的 `IntentPlan`，不能直接调用写工具。
- `route_intent`：根据结构化 action 路由查询或变更分支。
- `execute_read`：通过现有任务 service 执行只读查询。
- `resolve_targets`：修改、删除时获取候选并确定性评分；新建时不尝试复用同名任务。
- `supersede_pending`：当前消息是在修正未决批次时，只在图状态中记录待取代关系；此时不改变旧批次。
- `build_proposals`：生成完整的可编辑目标状态和必要快照，不写真实任务。
- `verify_proposals`：检查动作与用户表达一致、修改/删除目标存在、时间字段合法、无空修改、卡片字段完整，并检测本轮重复 proposal。
- `repair_plan`：只针对可修复的结构化错误重新规划，最多两次，避免无限模型循环。
- `persist_batches`：在一个业务事务中保存助手消息、已验证的新批次和所有提议，并原子地把旧批次标记为 `superseded`；事务成功后初始化对应的确认图暂停点。
- `finalize`：生成简短说明；有确认卡时只提示用户检查卡片，不再口头询问是否确认。

### 5.3 结构化计划

模型通过固定的 `submit_plan` schema 输出：

```text
kind: query | mutations
evidence: 用户原文中支持该动作的证据
query: 查询类请求的规范化描述
items[]:
  action: create | update | delete
  target_query: 修改/删除真实任务时用于定位任务的条件
  fields: 用户明确要求的新值或新建字段
  reference: “刚才那个”等指代命中的 pending proposal ID
```

Pydantic 在进入后续节点前验证该结构。逐项 action 使同一轮的新建与修改可以共同进入一个批次；对未确认新建提议的“修改”通过 `reference` 生成取代旧卡的新建提议，不把 pending create 当成真实任务。非对象参数、未知 action、缺失目标条件或无有效修改字段都必须转为可控错误，不能让消息永久处于处理中。

### 5.4 模型思考配置

- 规划调用不携带自由工具列表，并优先开启模型扩展思考，以提升复杂指代和多条件请求的计划质量。
- 最终回复调用关闭扩展思考，降低延迟和成本。
- 若所配置方舟模型不支持规划阶段的扩展思考，客户端自动回退为关闭并记录一次不含敏感信息的能力事件。
- 系统可靠性主要来自结构化 schema、确定性定位和验证节点，不能依赖模型内部思考是否可见或可用。

## 6. ProposalApplyGraph 设计

### 6.1 流程

```text
load_batch
  → interrupt_review
  → validate_edited_payload
  → apply_items
  → verify_results
  → persist_results
```

- `load_batch` 读取当前批次和 proposal 状态，拒绝不存在、已拒绝或已被取代的批次。
- `interrupt_review` 返回确认卡所需的完整数据，并用 LangGraph `interrupt()` 暂停。该节点在暂停前不做任何业务写入。
- 用户点击确认后，API 使用 `Command(resume=edited_items)` 恢复同一 graph thread；不调用模型。
- `validate_edited_payload` 只允许修改白名单任务字段。action、proposal ID、`target_task_id` 和 `before_snapshot` 由服务端持有，不能被客户端替换。
- `apply_items` 对每个未完成项目分别调用现有任务 service；每项在一个独立事务中完成任务写入、主回读验证以及 proposal payload/status/`result_task_id` 原子回写。
- `verify_results` 在提交后从业务库再次读取结果，作为恢复审计校验，不重复执行任务写入。
- `persist_results` 汇总批次状态并持久化恢复校验错误；成功项的原子结果已经由 `apply_items` 保存。

为保证崩溃重试不会出现“任务已创建但 proposal 尚未记录 `result_task_id`”，单项目的任务写入、同事务回读验证和 proposal 成功状态必须原子提交；图中的 `verify_results` 是提交后的独立恢复校验，`persist_results` 汇总批次状态并持久化校验错误，不会重复执行任务写入。

### 6.2 幂等与冲突

- proposal ID 是执行幂等键；状态已是 `accepted` 时返回原结果，不再次执行。
- 新建成功后必须保存 `result_task_id`，网络重试据此返回同一任务。
- 修改和删除前比较当前任务与 `before_snapshot`。若任务在等待确认期间已变化，不执行覆盖或删除，proposal 保持 `pending` 并写入冲突错误。
- 修改使用用户确认的完整目标状态，因此只修改 `time_end` 时不会因缺少 `time_start` 清空整个时间段。
- 对用户编辑后仍无实际差异的修改，返回可理解的 no-op 错误并保持可处理状态，不生成“接受但什么都没做”的结果。

## 7. 数据模型与迁移

必须新增编号迁移，不修改任何已执行迁移。

### 7.1 新增批次表

`assistant_proposal_batches`：

| 字段 | 含义 |
| --- | --- |
| `id` | 批次 ID，也是确认图 thread 的业务标识 |
| `conversation_id` | 所属会话 |
| `message_id` | 产生该批次的助手消息 |
| `status` | `pending` / `partially_applied` / `accepted` / `rejected` / `superseded` |
| `supersedes_batch_id` | 被当前批次取代的旧批次，可空 |
| `created_at` | 创建时间 |
| `resolved_at` | 全部完成、拒绝或被取代的时间，可空 |

### 7.2 扩展 proposal 表

| 字段 | 含义 |
| --- | --- |
| `batch_id` | 所属确认批次 |
| `target_task_id` | 修改/删除的真实目标；新建为空 |
| `before_snapshot` | 修改/删除生成提议时的完整任务快照 |
| `payload` | 新建或修改后完整、可编辑的目标状态 |
| `result_task_id` | 新建成功后的真实任务 ID；其他动作可复用目标 ID |
| `status` | 在原状态基础上增加 `superseded` |
| `last_error` | 最近一次验证、冲突或执行错误，可空 |

数据约束：

- create 没有 `before_snapshot`，`payload` 包含完整待创建字段。
- update 同时保存 before 和 after；前端据此展示目标任务及前后差异。
- delete 保存完整 before，卡片据此展示不可编辑的删除目标。
- 批次中只要存在成功项和 pending 失败项，状态就是 `partially_applied`。
- 历史 proposal 在迁移时各自归入单项目批次，并保留原 action、payload、status 和时间信息。

### 7.3 图运行索引

业务库维护会话、turn、batch 与 graph thread ID 的映射，以便：

- 同一 `turn_id` 重试时恢复原 checkpoint，不重复插入消息或提议。
- 会话删除时找到并清理其精确的 checkpoint thread，避免按路径或模糊前缀删除。
- 应用启动后识别未完成运行并允许安全恢复。

## 8. API 设计

### 8.1 发送消息

`POST /assistant/conversations/{id}/messages`

- 前端为首次发送和 Retry 复用同一个 `turn_id`。
- 后端以 `(conversation_id, turn_id)` 保证幂等，并启动或恢复 `AssistantTurnGraph`。
- 响应返回助手消息以及 `proposal_batches`，不返回需要用户在聊天中再次确认的问句。
- 同一会话一次只允许一个 active turn；约束在后端业务库中实施，不能只依赖前端禁用按钮。

### 8.2 确认批次

`POST /assistant/proposal-batches/{id}/confirm`

请求包含每个 proposal ID 及其编辑后的完整白名单字段。响应逐项返回：

```text
proposal_id
status: accepted | pending
task: 成功后的真实任务，可空
error: 失败或冲突说明，可空
```

后端恢复 `ProposalApplyGraph`，直接校验并执行，不将确认内容再交给模型解释。

### 8.3 拒绝批次

`POST /assistant/proposal-batches/{id}/reject`

- 新建/修改批次一次拒绝全部剩余 pending 项。
- 删除批次天然只有一项。
- 已 accepted 项不会因拒绝剩余项而回滚。

### 8.4 兼容策略

- 现有单 proposal accept/reject 端点在迁移期保留，并在服务层转发到其单项目批次。
- 新前端只使用批次端点。
- 兼容端点与新端点共享同一幂等和冲突检查，不维护两套写入逻辑。

## 9. 前端交互

新增或重构 `ProposalBatchCard`：

- 卡片顶部展示批次状态、操作类型和项目数量。
- create/update 项允许编辑标题、优先级、分类、开始时间、结束时间和备注。
- update 项明确展示目标任务名称，并以 before/after 形式突出差异。
- 批次只有一个“确认”按钮，提交期间禁用，成功后刷新现有 Todo 列表，不自动发送聊天消息。
- 部分成功时锁定成功项，失败项保留编辑能力，按钮改为“重新确认剩余项”。
- `superseded` 批次折叠展示历史内容，不能确认。

独立的 `DeleteProposalCard`：

- 展示目标任务标题、时间、分类、优先级、备注和完成状态。
- 每张卡只对应一个任务，确认与拒绝按钮独立。
- 删除目标及 action 不可编辑，避免确认时替换对象。

前端请求处理：

- 发送按钮和 Retry 使用稳定的 `turn_id`。
- 确认按钮使用稳定的 batch/proposal ID，防抖只能改善体验，真正幂等由后端保证。
- 卡片错误按项目展示，不能把已成功项重新放回可提交 payload。
- 页面刷新或应用重启后，根据服务端批次状态恢复卡片，而不是依赖组件内存状态。

## 10. 错误、并发与安全

- 方舟超时、限流或 5xx：保存当前 checkpoint，助手消息标记为 failed；Retry 恢复同一 `turn_id`。
- 结构化计划解析失败：保存可诊断的非敏感错误，最多修复两次，然后正常结束为失败消息，不遗留永久 pending turn。
- 图节点发生未预期异常：事务回滚；active turn 状态在异常边界统一转为 failed。
- 业务库与 checkpoint 库不做跨库伪事务：先幂等保存业务批次，再按稳定 thread ID 初始化暂停点；初始化失败时不返回确认卡，Retry 复用已有批次并只补建缺失的 checkpoint。
- 同一会话并发发送：通过业务库中的唯一 active turn 约束拒绝或复用，不依赖单进程内锁。
- 重复确认：返回已保存结果，不再次执行副作用。
- checkpoint 不存 API key；日志不记录消息正文、任务正文、附件内容或完整模型 payload。
- 删除会话时同时清理其附件、图运行映射和对应 checkpoint；只按数据库记录的精确 ID 删除。
- `interrupt_review` 前不得写任务或写接受状态；所有可能重放的节点必须纯函数化或幂等化。

## 11. 测试策略

### 11.1 纯逻辑与图测试

- 意图策略：显式新建不会因同名任务变成修改；修改/删除必须包含可定位条件。
- 候选评分：标题、时间、分类和最近上下文组合可稳定选出预期目标；低分进入澄清。
- proposal verifier：拒绝空修改、非法时间、缺失目标、重复项和不完整卡片数据。
- 使用 LangGraph 内存 checkpointer 测试各分支、两次修复上限、interrupt/resume 和无模型确认路径。
- 非对象模型输出及无效 action 能结束为可恢复失败，不留下永久处理中消息。

### 11.2 持久化与服务测试

- 新迁移可从当前数据库升级；历史 proposal 转为单项目批次且状态保持一致。
- SQLite checkpoint 在进程重启后可以恢复 turn 和待确认批次。
- 同一 `turn_id` 重试不重复生成用户消息、助手消息、批次或 proposal。
- 创建成功回填 `result_task_id`；再次确认返回同一结果。
- 修改/删除前快照冲突阻止写入，状态与错误正确保存。
- 批次逐项事务允许部分成功；成功项不因其他项失败而回滚或重放。
- 会话删除只清理该会话关联的 checkpoint 和附件。

### 11.3 API 与前端测试

- 消息接口返回批次而非口头预确认，并强制同一会话单 active turn。
- 确认接口接受编辑后完整字段，禁止修改 action、目标 ID 和非白名单字段。
- 卡片一次确认整个 create/update 批次；删除保持逐项确认。
- 部分成功后只允许重提失败项；已成功项保持锁定。
- superseded 卡片不可确认；刷新后状态与服务端一致。
- 点击确认不会生成新的聊天消息或触发模型请求。

### 11.4 必测回归场景

1. “新建一个明天下午四点的会议”不会修改已有同名任务。
2. “把会议改到四点”选择评分最高的真实任务，并在卡片中显示目标和前后差异。
3. “把刚才那个改成四点”取代旧 pending 批次，不产生两组可确认卡片。
4. 只修改 `time_end` 不会清空 `time_start`。
5. 用户编辑多个新建/修改项后只确认一次；部分失败时成功项不重复写入。
6. 连续点击确认或网络重试不会重复创建任务。
7. 服务重启后可以继续确认原批次。
8. 无效或非对象计划不会让消息永久处于 pending。
9. 现有后端 127 个通过测试继续通过，并补充上述新行为测试。
10. 在隔离的 Python 3.12 uv 环境中运行后端测试、Ruff 和 Pyright；前端运行现有单测、类型检查和构建。

真实方舟验收单独执行，至少覆盖：明确新建、模糊修改、连续修正、批量确认、模型不支持扩展思考时的回退，以及确认阶段零模型调用。

## 12. 分阶段交付与完成标准

实施顺序应按风险从数据正确性到交互体验推进：

1. 先建立批次数据模型、完整快照、幂等执行和 partial-time 修复。
2. 实现 `ProposalApplyGraph` 和批次 API，确保卡片编辑后可直接、安全写入。
3. 实现 `AssistantTurnGraph` 的结构化计划、目标定位和验证。
4. 改造前端批次卡片、删除卡片、部分成功和 superseded 状态。
5. 补齐持久化恢复、并发约束、兼容端点和真实方舟验收。

本设计的完成标准：

- 所有写操作在执行前都有可见卡片确认；无校验错误或并发冲突的正常路径只确认一次，不存在口头预确认或模型二次确认。
- 确认卡清楚显示动作、目标、原值和新值，并允许在规定范围内编辑。
- 确认按钮直接触发后端写入，确认路径不调用模型。
- 新建、修改和删除的路由与目标选择均经过确定性校验。
- 批量部分失败、重复请求、并发变化和进程重启都不会造成重复写入或静默数据破坏。
- 自动测试覆盖已报告的全部回归场景，并保持现有测试通过。
