# 本地 HTTP API

Base URL 由 Tauri 动态生成，格式为 `http://127.0.0.1:<port>/api/v1`。端口和 Bearer token 每次 sidecar 启动都可能变化，不写入磁盘。

所有路由都需要 `Authorization: Bearer <token>`。JSON 的公共字段通常使用 camelCase；提议卡 `payload` 的六个字段按既定契约保留 snake_case。未知字段和错误类型会被严格拒绝。

## 路由

| 方法 | 路径 | 请求 | 成功响应 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | `{ "status": "ok" }` |
| POST | `/bootstrap` | `{ preferredTheme }` | tasks、settings、achievementState 完整快照 |
| POST | `/tasks` | 任务创建字段 | `{ task }`，201 |
| PATCH | `/tasks/{id}` | 可变任务字段 | `{ task }` |
| DELETE | `/tasks/{id}` | 无 | 204 |
| PUT | `/tasks/order` | `{ taskIds }` | `{ tasks }` |
| PUT | `/tasks/{id}/completion` | `{ completed, localDate }` | task、achievementState、newlyUnlocked |
| POST | `/reminders/claim` | `{ taskId, scheduledStart }` | `{ claimed }` |
| PATCH | `/settings` | theme、muted、shortcut 或 language | `{ settings }` |

## 主要字段

任务：

```json
{
  "id": "...",
  "text": "整理会议记录",
  "completed": false,
  "priority": "medium",
  "createdAt": 1710000000000,
  "time": { "start": "2026-07-13T09:30", "end": "2026-07-13T10:00" },
  "category": "work",
  "notes": "可选备注"
}
```

- `priority`: `low | medium | high`
- `category`: `work | study | life | other`
- 时间为本地分钟格式 `YYYY-MM-DDTHH:mm`；没有时区转换。
- theme 为 `workspace | mint | paper` 与 `light | dark` 的六种组合。
- language 为 `zh-CN | en`，默认 `zh-CN`。

完成响应中的 `achievementState` 是权威完整状态，前端不自行重算。提醒 claim 只有在任务仍未完成且 `scheduledStart` 等于任务当前开始时间时才能返回 `true`。

## 错误

所有公开错误使用：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Invalid request"
  }
}
```

常见 code：

| HTTP | code | 含义 |
| --- | --- | --- |
| 400 | `INVALID_TASK_ORDER` | 顺序不是当前任务 ID 的完整排列 |
| 401 | `UNAUTHORIZED` | token 缺失或不匹配 |
| 404 | `TASK_NOT_FOUND` | 任务不存在 |
| 422 | `INVALID_REQUEST` | JSON 或字段校验失败 |
| 503 | `DATABASE_UNAVAILABLE` | 数据库或迁移不可用 |
| 500 | `INTERNAL_ERROR` | 其他内部错误 |

错误正文不会包含 token、路径、SQL、任务内容或 traceback。

## AI 助手

所有路由同样需要 Bearer token；统一挂载在 `/api/v1/assistant/` 下。

| 方法与路径 | 说明 |
| --- | --- |
| `POST /assistant/conversations` | 创建会话，返回 `{id, title, createdAt, updatedAt}` |
| `GET /assistant/conversations` | 返回 `{conversations: [...]}`（按 `updatedAt` 倒序） |
| `GET /assistant/conversations/{id}` | 返回 `{conversation, messages, proposalBatches}` |
| `DELETE /assistant/conversations/{id}` | 删除会话并清理其上传附件，204 |
| `POST /assistant/conversations/{id}/messages` | 发送稳定 turn，返回 `{message, proposalBatches}` |
| `POST /assistant/uploads` | multipart 上传（字段名 `file`），返回 `{fileId, kind, name, mime}` |
| `POST /assistant/transcribe` | `{fileId}` -> `{text}`（音频模型转写） |
| `POST /assistant/proposal-batches/{id}/confirm` | 提交 pending 项及编辑后的完整卡片字段，返回批次和逐项结果 |
| `POST /assistant/proposal-batches/{id}/reject` | 无请求正文；拒绝批次中仍 pending 的全部项目 |
| `POST /assistant/proposals/{id}/accept` | 旧版兼容路由；仅接受单项批次，返回 `{proposal, task?}` |
| `POST /assistant/proposals/{id}/reject` | 旧版兼容路由；仅拒绝单项批次，返回 `{proposal}` |
| `GET /assistant/settings` | 返回 `{hasApiKey, chatModel, audioModel}`（key 不回传） |
| `PUT /assistant/settings` | 保存 `{apiKey?, chatModel?, audioModel?}` |

上传限制：图片 jpg/jpeg/png/webp ≤10MB；文档 pdf/docx/txt/md ≤10MB；音频 mp3/wav/m4a ≤25MB。

### 稳定 turn 与批次响应

发送消息时客户端生成一个 8–100 字符的 `turnId`，并在同一次发送的重试中保持不变：

```json
POST /api/v1/assistant/conversations/c1/messages
{
  "turnId": "7dcf5632-6e40-41a2-8e9e-8cf122b65c70",
  "content": "新建一个明天下午四点的团队会议",
  "attachments": []
}
```

响应为 `{ "message": ..., "proposalBatches": [...] }`。新消息的 user/assistant 两行都携带同一个 `turnId`；migration 005 以前的历史消息允许 `turnId: null`。同一个 `turnId` 与相同正文、相同附件顺序重试时，已完成 turn 返回已存储结果而不重复建提议；复用该 ID 但改变请求内容返回 `ASSISTANT_TURN_PAYLOAD_MISMATCH`。同一会话同时只允许一个 active turn。

`proposalBatches` 中每个批次包含 `id`、`messageId`、`status`、nullable `supersedesBatchId`、`proposals`、`createdAt` 和 nullable `resolvedAt`。每个 proposal 包含 `batchId`、`action`、nullable `targetTaskId` / `beforeSnapshot` / `payload` / `resultTaskId` / `lastError` 及状态。`payload` 是卡片当前的完整六字段值：`text`、`priority`、`category`、`time_start`、`time_end`、`notes`；JSON 仍使用这六个既定 snake_case 卡片字段。

### 可编辑批次确认与拒绝

创建/更新卡片提交 pending 项的 proposal ID 和编辑后的完整 payload。请求示例：

```json
POST /api/v1/assistant/proposal-batches/b1/confirm
{
  "items": [
    {
      "proposalId": "p1",
      "payload": {
        "text": "团队会议",
        "priority": "high",
        "category": "work",
        "time_start": "2026-07-22T16:00",
        "time_end": "2026-07-22T17:00",
        "notes": null
      }
    }
  ]
}
```

删除卡片不可编辑，确认时仍传原 proposal ID，但 `payload` 为 `null`；后端使用已存储的目标和快照。确认不会调用 Ark，也不会创建新的聊天消息。拒绝路由没有请求正文，会把批次中仍 pending 的项目整体拒绝；accepted 历史不回退。

确认响应顶层为 `{ "batch": <完整批次>, "items": [<逐项结果>...] }`。每个逐项结果包含完整 `proposal`、nullable `task` 和 nullable `error`；`batch.proposals` 同时返回该批次的完整项目状态，不只是本次提交的项目。

每个项目使用独立事务。成功项提交为 `accepted`，create/update 的 `task` 返回权威任务，delete 的 `task` 为 `null`；业务校验失败的项目保持 `pending`，在 `error` / `proposal.lastError` 返回稳定码并保留可编辑 payload。因而同一批可以部分成功，批次状态为 `partially_applied`，随后只重提仍 pending 的失败项。重复确认 terminal 批次返回已存储结果，不重复写任务；`superseded` 批次不可再确认。

旧版 `/assistant/proposals/{id}/accept|reject` 路由不接收编辑 payload，只对单项批次有效；多项批次返回 `PROPOSAL_BATCH_REQUIRED`，调用方必须改用批次路由。

### AI 助手错误码

公开 HTTP 错误除通用 `INVALID_REQUEST` 外包括：

| HTTP | code | 含义 |
| --- | --- | --- |
| 404 | `CONVERSATION_NOT_FOUND` / `PROPOSAL_NOT_FOUND` / `PROPOSAL_BATCH_NOT_FOUND` / `UPLOAD_NOT_FOUND` | 指定资源不存在 |
| 409 | `ASSISTANT_NOT_CONFIGURED` | 尚未配置 Ark API Key |
| 409 | `ASSISTANT_TURN_ACTIVE` | 会话已有 active turn，或相同 turn 正在本进程执行 |
| 409 | `ASSISTANT_TURN_PAYLOAD_MISMATCH` | 相同 `turnId` 被用于不同请求 |
| 409 | `PROPOSAL_BATCH_NOT_CONFIRMABLE` | 批次已 superseded，不能确认或拒绝 |
| 409 | `PROPOSAL_BATCH_REQUIRED` | 多项批次错误使用了旧版单项路由 |
| 413 | `UPLOAD_TOO_LARGE` | 上传超过对应类型限制 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 不支持的上传类型 |
| 422 | `INVALID_CONFIRMATION_PAYLOAD` | 批次确认项含重复 proposal ID，或 proposal 不属于该批次 |
| 422 | `DOCUMENT_NOT_READABLE` | 文档没有可提取文本 |
| 503 | `ASSISTANT_UNAVAILABLE` | Ark 或助手服务不可用 |

逐项确认失败使用 `error` 和 `proposal.lastError`，稳定码包括 `PROPOSAL_NOT_CONFIRMABLE`、`TASK_TARGET_NOT_FOUND`、`TASK_CHANGED_SINCE_PROPOSAL`、`INVALID_PROPOSAL_PAYLOAD`、`CREATE_TITLE_REQUIRED`、`TIME_END_REQUIRES_START`、`TIME_END_BEFORE_START`、`UPDATE_HAS_NO_CHANGES` 和 `RESULT_VERIFICATION_FAILED`。这些是批次响应内的项目结果，不替代上表的 HTTP 错误 envelope。
