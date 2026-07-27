# Agent 智能修复 — 意图理解、分类推断、记忆系统、前后端缺陷

日期：2026-07-25

分支：`dev-agent`

---

## 版本概览

本日志记录对 AI 助手 agent 的全链路修复，涵盖 **code review 发现的 8 个缺陷** + **5 个智能增强** + **2 个前端交互优化**。涉及文件：planning.py、turn_graph.py、proposal_batches.py、assistant.py、useAssistant.ts、client.ts、MessageList.tsx、assistant.css。

---

## 一、Code Review 发现的 8 个缺陷修复

### 正确性修复（6 项）

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `useAssistant.ts` + `client.ts` | SSE 流 HTTP 错误时 `sendAssistantMessageStream` 不抛异常，`streamSucceeded=true` 被错误设置，跳过了非流式 fallback | `streamSucceeded` 移到 `'done'` 事件回调内设置；HTTP 错误改为 throw |
| 2 | `proposal_batches.py` | 数据库中 create 类 proposal 的 payload 若 `text:null`，`ProposalCardFields.model_validate()` 抛 `ValidationError` 导致整个会话不可读 | 加 `try/except ValidationError`，fallback 为 `text="(corrupted)"` 占位 |
| 3 | `turn_graph.py:76` | `_MUTATION_COMPLETION_CLAIM` 正则 `\b(?:created\|added\|...)\b` 匹配到合法查询响应如 "You created 2 tasks yesterday" | 英文交替改为 `\bI(?:\s*'ve\|\s+have)?\s+(?:created\|...)` 要求第一人称主语 |
| 4 | `useAssistant.ts` | 流式响应完成时 `setMessages` 未检查 `activeId` 是否已切换，用户快速切换会话会看到错误的消息列表 | 增加 `sendActiveId` 捕获 + 写入前校验 `activeId === sendActiveId` |
| 5 | `assistant.py` | `asyncio.Queue` 从 `run_in_executor` 线程调用 `put_nowait`，Python 文档明确标注非线程安全 | 改为 `loop.call_soon_threadsafe(_safe_put, event)`，所有队列写入回到 event loop 线程 |
| 6 | `turn_graph.py:268` | `run()` 的 `except Exception` 处理完后继续 emit `"done"` 事件，与前面的 `"error"` 事件矛盾 | 加 `turn_errored` 标志，异常后跳过 `"done"` 和记忆保存 |

### 简化修复（2 项）

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 7 | `assistant.py` | 5 处 `try/except QueueFull` 为死代码——`asyncio.Queue()` 默认 maxsize=0（无界），永不 raise | 随 #5 一并移除，改为 `call_soon_threadsafe` 调用 |
| 8 | `turn_graph.py:1093` | `_finalize_error` 将 LLM 多行反馈原文（如 `_reflect` 的 "Reflect found issues:\nItem 0: ..."）直接写入 DB 的 `error_code` 列 | `str(raw_error).split("\n")[0][:200]` 截断为首行 200 字符 |

---

## 二、Agent 智能增强（5 项）

### 1. 分类推断 — CATEGORY 规则

**文件**：`planning.py:_PLANNER_SYSTEM_PROMPT`

**问题**：模型完全不理解四个分类（work/study/life/other）的含义，遇「英语课」分到「其他」。

**修复**：在 planner prompt 中新增 CATEGORY 规则块，明确定义四分类，附中英文关键词和示例映射：

```
- "work":    工作 上班 开会 项目 报告 客户 出差 面试 加班 合同 预算
- "study":   学习 上课 作业 考试 读书 课程 培训 论文 笔记 英语课 数学
- "life":    购物 买菜 健身 家务 看病 聚会 旅行 电影 做饭 缴费 搬家
- "other":   only when genuinely does not fit

Examples: "英语课" → study, "项目周会" → work, "买菜" → life
```

### 2. 闲聊意图 — chat 路由

**文件**：`planning.py`（AnalysisResult + ANALYZE_PROMPT）、`turn_graph.py`（_build_graph + _chat_response + _CHAT_SYSTEM_PROMPT）

**问题**：「你是什么模型」等离题消息被分析为 `query`，走计划→查询流水线，既不合适也容易失败。

**修复**：
- `AnalysisResult.intent` 新增 `"chat"` 字面量
- `ANALYZE_PROMPT` 增加 `chat` 意图定义（问候、闲聊、询问助手本身、离题问题）
- 新增 `_CHAT_SYSTEM_PROMPT`：要求模型像真人聊天，回答后自然带出 TodoList 功能引导
- 新增 `_chat_response` 节点：直接调 LLM，失败有降级话术
- 图路由：`analyze_intent → "chat" → chat_response → finalize`

### 3. Query 意图路由修复

**文件**：`turn_graph.py:_build_graph`

**问题**：`analyze_intent → "query"` 直接路由到 `execute_read`，但 `execute_read` 需要 `state["plan"]` 中的有效 `IntentPlan`，而 `plan` 只在 `plan_intent` 中生成。所有 query 意图的消息都会因 `IntentPlan.model_validate({})` 失败。

**修复**：
```
- "query": "execute_read",
+ "query": "plan_intent",
```
让 `query` 和 `mutations` 都先经过 `plan_intent`，由 `_intent_route` 根据 plan.kind 分别路由。

### 4. 确认词识别 + 记忆标记

**文件**：`planning.py:ANALYZE_PROMPT`、`turn_graph.py`（_analyze_intent 记忆注入、_plan_intent 记忆注入、_reflect 记忆格式、_clarify_response）

**问题**：用户说「确认」时，文本管道无法确认提议卡。分析当成 mutations，planner 没有 confirm 动作，只能重复创建。

**修复**：
- `ANALYZE_PROMPT` 新增确认词规则：「确认/好的/行/ok/yes」+ pending proposals → `clarify`，引导用户点击卡片按钮
- 变异回合记忆新增 `"status": "pending_confirmation"` 标记
- 分析和规划的记忆注入增加 ⚠️ 提示：有未确认卡时不要重复创建

### 5. 对话式追问 — 像人一样澄清

**文件**：`planning.py:ANALYZE_PROMPT`、`turn_graph.py`（_clarify_response 记忆、分析/规划记忆注入）

**问题**：澄清话术生硬（"请提供更多信息"），追问后下一回合丢失上下文。

**修复**：
- `ANALYZE_PROMPT` 增加澄清话术指引：BAD vs GOOD 示例，要求像真人一样问一个具体问题
- 新增 FOLLOW-UP RESPONSES 规则：检测到上一回合刚追问过 → 结合原始请求+回答重新评估，信息够了直接走 mutations
- `_clarify_response` 新增 `"status": "awaiting_clarification"` 记忆记录
- 记忆注入新增 💬 提示：助理刚追问，用户当前消息很可能是回答

---

## 三、前端交互优化

### 1. 发送后自动滚动到底部

**文件**：`MessageList.tsx`

- 添加 `useRef<HTMLDivElement>` 指向消息列表容器
- 添加 `useEffect`，`messages`/`sending`/`proposalBatches` 变化时自动 `scrollTop = scrollHeight`

### 2. 助手面板头部图标调整

**文件**：`assistant.css`

- 头部按钮 SVG 从全局 20px 增大到 21px
- ✦ logo 容器对齐 `icon-btn`（36×36px），字号 1.5rem（和 SVG 视觉等重），「AI 助手」文字垂直居中

---

## 涉及文件清单

| 文件 | 改动类型 |
|------|---------|
| `backend/src/todo_backend/agent/planning.py` | CATEGORY 规则、chat 意图、确认词规则、对话式追问 |
| `backend/src/todo_backend/agent/turn_graph.py` | Query 路由修复、chat_response 节点、_CHAT_SYSTEM_PROMPT、记忆系统增强（pending/clarify 标记 + 注入提示）、_verify_answer 正则修复、run() done/error 修复、_finalize_error 截断 |
| `backend/src/todo_backend/repositories/proposal_batches.py` | create payload 反崩溃 |
| `backend/src/todo_backend/services/assistant.py` | asyncio.Queue 线程安全 + QueueFull 死代码清理 |
| `frontend/src/features/assistant/hooks/useAssistant.ts` | SSE streamSucceeded 修复 + 导航竞态防护 |
| `frontend/src/shared/api/client.ts` | sendAssistantMessageStream HTTP 错误 throw |
| `frontend/src/features/assistant/components/MessageList.tsx` | 发送后自动滚底 |
| `frontend/src/features/assistant/styles/assistant.css` | 头部图标尺寸 + ✦ logo 对齐 |
