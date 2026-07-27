# SQLite 数据库

TodoList 使用 Python 标准库 `sqlite3`。macOS 正常运行时数据库位于：

```text
~/Library/Application Support/com.todo-app.desktop/todo.sqlite3
```

具体目录由 Tauri `app_data_dir` 决定。数据库启用 foreign keys、WAL 和 5 秒 busy timeout。

AI 助手另在同一目录使用独立的 LangGraph checkpoint 数据库：

```text
~/Library/Application Support/com.todo-app.desktop/assistant_graph.sqlite3
```

`todo.sqlite3` 是业务事实和审计记录的所有者；`assistant_graph.sqlite3` 只保存工作流恢复状态，不受应用的编号 SQL 迁移管理。

## Schema

初始迁移 `backend/migrations/001_initial.sql` 创建：

| 表 | 用途 |
| --- | --- |
| `tasks` | 任务内容、完成状态、优先级、时间、分类、备注和 position |
| `achievement_state` | 单行 streak、当天日期和完成数 |
| `achievement_unlocks` | 已解锁成就 ID |
| `task_reminders` | `(task_id, scheduled_start)` 唯一 claim |
| `app_settings` | 单行 theme、muted、shortcut、language |

`task_reminders.task_id` 使用外键并在任务删除时级联清理。任务顺序由唯一的整数 `position` 表示。

## 迁移

- 文件命名：`NNN_description.sql`。
- 启动时按编号排序，只执行高于 `PRAGMA user_version` 的迁移。
- 每个迁移与 `user_version` 更新在一个事务中执行。
- 数据库版本高于程序支持的最新版本时拒绝启动并返回稳定 503。
- 已发布迁移保持不变；schema 变化新增下一个编号文件。
- `002_add_language_setting.sql` 增加 `language`，允许 `zh-CN | en`，现有数据库默认升级为 `zh-CN`。
- `003_add_assistant.sql` 增加会话、消息、旧版提议表及 assistant 模型配置。
- `004_add_assistant_base_url.sql` 增加可配置的 Ark Base URL。
- `005_redesign_assistant_agent.sql` 将 schema 升到 version 5：为消息增加 nullable `turn_id`，新增 `assistant_turns` 和 `assistant_proposal_batches`，并重建扩展后的 `assistant_proposals`。

## 事务

写事务使用 `BEGIN IMMEDIATE`。任务完成和成就更新原子提交；提醒 claim 在同一 SQL 操作中核对任务时间及完成状态；设置 patch 和任务排序也在事务中完成。

## 备份与恢复

完全退出 TodoList 后复制 `todo.sqlite3` 可以备份业务事实。若还要保留未完成 LangGraph 工作流的恢复状态和上传附件，需要按下文同时备份 `assistant_graph.sqlite3` 与 `assistant_uploads/`。应用运行时 `todo.sqlite3` 处于 WAL 模式，不要只复制主文件而忽略可能存在的 `-wal` 文件。

恢复前先退出应用，再替换数据库文件。若恢复文件的 `user_version` 高于当前应用支持版本，应用会进入阻断错误页而不会降级或覆盖数据。

删除 `todo.sqlite3` 会丢失全部任务、设置、成就、提醒 claim 和 AI 助手业务记录；下次启动会创建空库。独立 checkpoint 和上传文件不会随手工删除该文件而自动清理。

## AI 助手业务表

### assistant_conversations / assistant_messages

- `assistant_conversations`：`id` 主键，`title`，`created_at` / `updated_at`（毫秒时间戳）。
- `assistant_messages`：`id` 主键，`conversation_id` 外键（级联删除），`role`（user/assistant），`content`，`attachments`（JSON），`tool_trace`（JSON，仅审计），`status`（pending/done/failed），`created_at`，以及 migration 005 新增的 nullable `turn_id`。新 turn 的 user/assistant 消息共享稳定 `turn_id`；旧历史允许为 null。

### assistant_turns

`assistant_turns` 保存稳定 turn 的业务生命周期：`id`、`conversation_id`、user/assistant message 外键、`request_fingerprint`、`status`（active/done/failed）、nullable `last_error` 及时间戳。partial unique index `idx_assistant_turns_one_active` 保证每个会话最多一个 active turn。

状态转换为：新请求建立 `active`；成功完成落为 `done`，失败落为 `failed`；相同请求重试可将 `failed` 重新置为 `active`。`done` turn 按相同 fingerprint 幂等返回已存储消息和批次，不能用同一 `turn_id` 替换请求正文或附件顺序。

### assistant_proposal_batches / assistant_proposals

- `assistant_proposal_batches`：`id`、conversation/message 外键、`status`（pending/partially_applied/accepted/rejected/superseded）、nullable `supersedes_batch_id`、`created_at` / nullable `resolved_at`。
- `assistant_proposals`：`id`、conversation/message/batch 外键、`action`（create/update/delete）、nullable `target_task_id`、nullable `before_snapshot`、nullable 完整六字段 `payload`、nullable `result_task_id`、`status`（pending/accepted/rejected/superseded）、nullable `last_error` 和时间戳。

新 create/update 提议持久化完整卡片 payload；update/delete 保存目标的 `before_snapshot`，用于确认时检测真实任务是否已变化。用户编辑后的完整 payload 会作为审计值持久化。每项独立事务允许 accepted 项与仍 pending 的失败项共存；此时批次为 `partially_applied`。全 accepted / 全 rejected / 全 superseded 分别计算为对应 terminal 状态；批次没有 pending 项时设置 `resolved_at`。后续修正批次只把旧批次中仍 pending 的项目置为 `superseded`，已 accepted 的审计历史保留。

migration 005 把每个旧 proposal 包装为同 ID 的单项 batch 并保留原状态。旧 update/delete 尽可能从当前 task 补 `before_snapshot`；目标已不存在时保留 nullable snapshot/payload，pending 行记录 `TASK_TARGET_NOT_FOUND`，从而可以展示历史但不会误删任务。旧版单项 API 依赖这种兼容形态，多项批次必须使用 batch API。

迁移 `003_add_assistant.sql` 向 `app_settings` 增加 `assistant_api_key`、`assistant_chat_model`、`assistant_audio_model` 三列；migration 004 增加 `assistant_base_url`。API key 只存于该列，任何接口不回传。

上传的文件保存在数据库同级的 `assistant_uploads/` 目录，删除会话时同步清理。

## LangGraph checkpoint 与清理所有权

`assistant_graph.sqlite3` 同时承载两个 thread namespace：对话规划工作流使用 `turn:{turnId}`，批次应用工作流使用 `proposal:{batchId}`。checkpoint 只存 JSON-safe 状态；任务、消息、turn、批次和提议的权威状态始终从 `todo.sqlite3` 读取。

清理责任严格归属服务层：

1. 删除会话的事务先收集其 turn ID、batch ID 和上传 file ID，再删除 `todo.sqlite3` 中的会话；外键级联删除消息、turn、batch 和 proposal。
2. 主事务成功后，`AssistantService` 精确删除相应 `turn:{turnId}` 与 `proposal:{batchId}` checkpoint thread，再删除该会话的上传文件。
3. 正常进程关闭由 FastAPI lifespan 调用 `AssistantService.close()`，只关闭 checkpoint SQLite 连接；terminal turn/batch 不会在关闭时被批量清空。
4. migration 005 不创建、迁移或清理 `assistant_graph.sqlite3`；repository 也不拥有 checkpoint 生命周期。

完整备份应先完全退出应用，再同时复制 `todo.sqlite3`、`assistant_graph.sqlite3` 和需要保留的 `assistant_uploads/`。只删除 `todo.sqlite3` 会丢失业务数据，但不会自动删除独立 checkpoint 文件或上传目录；如要做完整本地重置，应在应用退出后明确处理三者。
