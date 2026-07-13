# 本地 HTTP API

Base URL 由 Tauri 动态生成，格式为 `http://127.0.0.1:<port>/api/v1`。端口和 Bearer token 每次 sidecar 启动都可能变化，不写入磁盘。

所有路由都需要 `Authorization: Bearer <token>`。JSON 使用 camelCase；未知字段和错误类型会被严格拒绝。

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
| PATCH | `/settings` | theme、muted 或 shortcut | `{ settings }` |

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
