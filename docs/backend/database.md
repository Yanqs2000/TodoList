# SQLite 数据库

TodoList 使用 Python 标准库 `sqlite3`。macOS 正常运行时数据库位于：

```text
~/Library/Application Support/com.todo-app.desktop/todo.sqlite3
```

具体目录由 Tauri `app_data_dir` 决定。数据库启用 foreign keys、WAL 和 5 秒 busy timeout。

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

## 事务

写事务使用 `BEGIN IMMEDIATE`。任务完成和成就更新原子提交；提醒 claim 在同一 SQL 操作中核对任务时间及完成状态；设置 patch 和任务排序也在事务中完成。

## 备份与恢复

完全退出 TodoList 后复制 `todo.sqlite3` 即可备份。应用运行时处于 WAL 模式，不要只复制主文件而忽略可能存在的 `-wal` 文件。

恢复前先退出应用，再替换数据库文件。若恢复文件的 `user_version` 高于当前应用支持版本，应用会进入阻断错误页而不会降级或覆盖数据。

删除数据库会丢失全部任务、设置、成就和提醒 claim；下次启动会创建空库。
