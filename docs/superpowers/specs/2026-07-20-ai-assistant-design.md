# TodoList AI 助手（Agent）设计

日期：2026-07-20
分支：dev-agent

## 1. 目标

为 TodoList 增加一个 AI 分析助手。用户通过文字、语音或上传文件（图片、文档、音频）输入信息，助手（agent）调用火山方舟多模态模型分析内容，在多轮对话中理解意图，把待办事项以**提议卡片**形式呈现，用户确认后才写入任务列表。助手同时可以查询和提议修改、删除现有任务。

## 2. 已确认约束

- 云端模型：火山引擎方舟（`https://ark.cn-beijing.volces.com/api/v3`），Bearer API key 认证，接口兼容 OpenAI SDK。
- 语音两条路径：录音 → 转文字（可编辑再发送）；录音 → 直接发送（音频理解模型分析）。
- 文件类型：图片（jpg/png/webp）、文档（pdf/docx/txt/md）、音频（mp3/wav/m4a）。
- agent 分析出的任务一律先提议，用户点击「接受」才写入真实任务。
- 交互深度：多轮对话 + 读写现有任务（读直接生效，写只生成提议）。
- 会话与消息持久化到 SQLite，重启后可继续。
- 界面形态：主界面右侧抽屉。
- 全程中英文界面，文案走现有 i18n 体系。

## 3. 火山方舟接入事实（已核实，2026-07-20）

来源：火山方舟官方文档（[文本生成](https://docs.volcengine.com/docs/82379/1399009)、[Function Calling](https://docs.volcengine.com/docs/82379/1262342)、[图片理解](https://docs.volcengine.com/docs/82379/1362931)、[音频理解](https://docs.volcengine.com/docs/82379/2377589)、[文档理解](https://docs.volcengine.com/docs/82379/1902647)）。

- Chat Completions：`POST /api/v3/chat/completions`，OpenAI 兼容；Python 使用 `volcengine-python-sdk[ark]` 或 openai SDK 覆盖 `base_url`。
- Function Calling 与 OpenAI 格式一致：`tools` 参数、`tool_calls` 返回、`finish_reason="tool_calls"`、assistant→tool→assistant 消息严格交替；工具调用场景建议 `thinking: {"type": "disabled"}`。
- 图片输入（Chat API）：`{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`，单张 ≤10MB。
- 音频输入（Chat API）：`{"type": "input_audio", "input_audio": {"data": "<base64>", "format": "wav"}}`，≤25MB、≤120 分钟；支持 mp3/wav/aac/m4a 等；需音频理解模型。
- 文档：模型原生仅支持 PDF 且仅 Responses API；docx/txt/md 无模型原生支持。
- 推荐主模型 `doubao-seed-2-1-pro-260628`，音频理解模型示例 `doubao-seed-2-0-lite-260428`。两者均为**可配置项**，不写死。

## 4. 方案选择与取舍

采用**后端编排 agent 循环**：Python 后端拥有完整循环（接收消息 → 调方舟 → 执行工具 → 循环 → 返回回复与提议）。

未采用的方案：

- 前端驱动 agent 循环：API key 会暴露到前端，工具执行绕开后端校验，难测试。
- 单轮解析无工具循环：模型修改现有任务只能靠模糊文本指令，不可靠，满足不了「读写现有任务」。

已确认的取舍：

- **语音「直接发送」内部采用级联**：音频附件先进音频理解模型转写，转写文本作为该消息的文本内容进入主 agent 循环（带工具）；音频原件保留在消息附件中可回看。原因：音频模型的 function calling 能力未经证实，级联路径确定、可测。可观察行为与「音频直发主模型」一致（说话 → 出提议），仅损失语气等副语言信息。若方舟后续提供「音频 + 工具调用」双能力模型，可去掉级联。
- **文档不做 OCR**：PDF 用 pypdf 提取文本，扫描件提取为空时明确报错提示用户；不接 Responses API 的 `input_file`，保持单一 API 形态与单一工具循环。
- **前端录音定 WAV**：方舟不支持浏览器 MediaRecorder 默认的 webm/opus；用 Web Audio API 录 PCM 编码 WAV（16kHz 单声道，语音 1 分钟约 2MB），格式零兼容风险。
- **不做流式输出**：首版请求/响应 + 「正在思考」指示，工具循环下的流式状态机复杂度不值得。
- 不做视频、不做多 provider 抽象、不做联网搜索工具、不做会话分支/分享。

## 5. 后端设计

新增 `backend/src/todo_backend/agent/` 与相关模块：

```
agent/
  ark_client.py      # 唯一出网口：chat completions（文本/图片/音频/工具）、转写调用
  tools.py           # 工具 JSON Schema 定义 + 执行器（映射到现有 service 层）
  orchestrator.py    # agent 循环：历史组装 → 调模型 → 执行工具 → 循环（上限 8 次）→ 最终回复
repositories/
  conversations.py   # 会话、消息、提议三张表的 SQL
services/
  assistant.py       # 事务边界：消息持久化、编排器调用、提议 accept/reject
  documents.py       # 文档文本提取（pypdf / python-docx / 纯文本）
```

职责边界：

- `ark_client.py` 是唯一调用火山引擎的模块，测试中全部 mock，其余测试不打真实网络。
- 工具执行器只调用现有 service 层（任务查询走任务 service），不直接写 SQL。
- `propose_*` 工具只写提议表，不触碰任务表；只有 `accept` 端点经现有任务 service 真正写入。

### 工具集（agent 能力边界）

| 工具 | 说明 |
| --- | --- |
| `list_tasks(status?, due_before?, due_after?, search?)` | 查询任务摘要（id、标题、截止时间、优先级、分类、完成态） |
| `get_task(task_id)` | 读取单个任务完整字段 |
| `propose_create_tasks(items[])` | 提议新建任务（标题、时间、提醒、优先级、分类、备注） |
| `propose_update_task(task_id, changes)` | 提议修改现有任务字段 |
| `propose_delete_task(task_id)` | 提议删除现有任务 |

### 数据库迁移（新编号迁移，不改旧迁移）

```sql
CREATE TABLE assistant_conversations (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE assistant_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                 -- user | assistant
  content TEXT NOT NULL,              -- 可见文本（语音消息为转写文本）
  attachments TEXT,                   -- JSON: [{file_id, kind, name, mime}]，可空
  tool_trace TEXT,                    -- JSON: 本轮工具调用轨迹，仅审计用，可空
  status TEXT NOT NULL DEFAULT 'done',-- done | failed
  created_at TEXT NOT NULL
);

CREATE TABLE assistant_proposals (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES assistant_messages(id),
  action TEXT NOT NULL,               -- create | update | delete
  task_id TEXT,                       -- update/delete 的目标任务
  payload TEXT NOT NULL,              -- JSON: 任务字段
  status TEXT NOT NULL DEFAULT 'pending', -- pending | accepted | rejected
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
```

设置表新增键：`assistant.api_key`（读取一律打码）、`assistant.chat_model`、`assistant.audio_model`。

附件存储：应用数据目录下 `assistant_uploads/`（与 `todo.sqlite3` 同级），file_id 为 uuid + 原始扩展名；删除会话时清理其附件。

### API 路由（`/assistant/*`，沿用现有 Bearer 认证）

| 路由 | 说明 |
| --- | --- |
| `POST /assistant/conversations` | 创建会话（前端在发送首条消息前调用，标题取首条消息截断） |
| `GET /assistant/conversations` | 会话列表（最近在前） |
| `GET /assistant/conversations/{id}` | 会话详情 + 消息 + 提议 |
| `DELETE /assistant/conversations/{id}` | 删除会话并清理附件 |
| `POST /assistant/conversations/{id}/messages` | 发消息（文本 + 附件引用），跑 agent 循环，返回助手消息 + 新提议 |
| `POST /assistant/uploads` | multipart 上传，类型白名单 + 大小上限，返回 `{file_id, kind, name}` |
| `POST /assistant/transcribe` | `{file_id}` → 音频模型转写 → `{text}` |
| `POST /assistant/proposals/{id}/accept` | 按 action 经现有任务 service 创建/修改/删除真实任务，幂等 |
| `POST /assistant/proposals/{id}/reject` | 提议标记已拒绝，留档 |
| `GET /assistant/settings` | `{has_api_key, chat_model, audio_model}`，key 不回传 |
| `PUT /assistant/settings` | 保存 key / 模型 ID |

### agent 循环细节

- 系统提示注入：当前本地时间（后端与用户同机）、界面语言、工具纪律（创建/修改/删除一律走 propose 工具，不口头承诺）。
- 历史重建：每轮用 user/assistant 可见消息重建对话；`tool_trace` 不回放。会话中 pending 提议的摘要随系统提示注入，支撑「改成四点」这类指代修正。
- 循环上限 8 次；超限返回兜底文案并保留已产生的提议。
- 附件进模型的方式：图片 base64 → `image_url`；音频 base64 → 先经音频模型转写；文档 → `documents.py` 提取文本后作为文本内容。

## 6. 前端设计

新增 `frontend/src/features/assistant/`：

- `AssistantDrawer.tsx`：右侧抽屉容器；header 操作区加助手按钮打开。
- `MessageList.tsx` / `MessageBubble.tsx`：消息流，语音消息显示转写文本 + 音频附件标识。
- `Composer.tsx`：输入框 + 麦克风按钮（按住/点击录音）+ 附件按钮 + 发送；录音后可选「转文字」或「直接发送」。
- `ProposalCard.tsx`：提议卡片，展示任务字段，接受/拒绝按钮；接受后任务列表经现有状态流刷新。
- `AssistantSettings.tsx`：API key（打码显示已保存状态）+ 两个模型 ID 配置。
- `wavRecorder.ts`：AudioContext 采集 PCM → 编码 WAV。
- `useAssistant.ts`：会话状态、发送中禁用、错误重试。
- `shared/api` 增加 assistant 端点封装；i18n 词典增加中英文文案键。

## 7. 数据流

以「发一张图 + 一句话」为例：

1. 抽屉中输入「把这张图里的会议安排加进任务」并附截图。
2. 前端 `POST /assistant/uploads` 传图 → `file_id`；再 `POST .../messages`（文本 + 附件引用）。
3. 后端落库用户消息 → 编排器加载历史 → 组装方舟请求（图片 base64 + 工具定义）。
4. 模型连续调用工具：`list_tasks` → 后端执行回填 → `propose_create_tasks` → 写提议表 → 模型输出「整理出 3 条任务，请确认」。
5. 响应返回助手消息 + 提议，前端渲染消息与提议卡片。
6. 用户点「接受」→ `POST /assistant/proposals/{id}/accept` → 现有任务 service 创建任务 → 列表刷新；「拒绝」→ 标记留档。

语音转文字：录音 WAV → uploads → transcribe → 文本进输入框（可编辑）→ 走同样流程。
语音直接发送：录音 WAV 作为附件随消息发送，后端内部级联转写后进 agent 循环。

## 8. 错误处理

- 未配置 API key：抽屉显示配置引导，不发请求。
- 方舟超时/限流/5xx：助手消息标记失败态 + 重试按钮；会话与已落库提议不受影响。
- 工具执行失败：错误作为 tool result 回填模型，让其解释或调整；配合 8 次循环上限防失控。
- 上传校验：类型白名单（jpg/png/webp、pdf/docx/txt/md、mp3/wav/m4a）；图片/文档 ≤10MB、音频 ≤25MB，超限前端拦截。
- 扫描件 PDF 提取为空：返回明确错误提示。
- 并发：同一会话消息串行处理，发送中禁用输入。

## 9. 安全

- API key 只存后端 SQLite 设置表，读取接口打码（`sk-...****`），永不进日志。
- 日志不写消息正文（沿用现有「日志不含任务内容」约定）。
- 附件存本机数据目录；服务仍只监听 127.0.0.1 + Bearer token。
- 前端不直接接触方舟凭证，不获得 shell 执行权限（现有桌面约束不变）。

## 10. 测试策略

后端（pytest）：

- 编排器：mock `ArkClient` 构造多轮 tool_calls 序列，验证循环、上限、失败回填。
- 工具执行器：真实 service + 临时库，验证查询过滤、`propose_*` 只写提议表、字段校验。
- 提议流转：accept 写入真实任务、reject 留档、重复 accept 幂等拒绝。
- API：认证 401、上传校验、串行约束、key 打码不泄露。
- 迁移：升级/回滚/幂等（对齐现有迁移测试模式）。
- 文档提取：正常提取、扫描件明确报错。

前端（vitest）：

- 抽屉渲染、消息列表、发送中禁用。
- 提议卡片接受/拒绝调用与状态切换。
- WAV 编码器单测；麦克风权限拒绝的降级提示。
- 上传校验前端拦截。
- i18n 新增键中英文齐备。

手动验收（真实方舟 key）：文字提问 → 语音转文字 → 语音直发 → 图片分析 → 文档分析 → 提议接受落库 → 多轮修正 → 重启后会话仍在。
