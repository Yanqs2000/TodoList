# Python SQLite 后端设计

- 日期：2026-07-12
- 状态：已确认
- 目标平台：macOS Apple Silicon

## 1. 背景与目标

当前 Todo List 是 React + Tauri 桌面应用，任务、主题、静音、成就、提醒去重和快捷键偏好保存在 `localStorage`。本次改造为应用增加随桌面程序运行的 Python 本地后端，并用普通 SQLite 数据库替代全部应用自有的持久化数据。

本次设计的目标是：

- 以 Python FastAPI sidecar 提供本机后端 API。
- 使用 Python 标准库 `sqlite3` 访问 SQLite。
- 使用 `uv` 管理 Python 版本、依赖、锁文件和开发命令。
- 将 React 前端、Python 后端、Tauri 桌面层的代码和文档明确分开。
- 最终用户安装 `.app` 后无需另行安装 Python 或 `uv`。
- 保持现有任务、设置、提醒、成就和界面行为不变。
- 数据库或后端不可用时阻止用户继续产生无法保存的修改。

## 2. 范围与非目标

### 2.1 范围

- 任务 CRUD、完成状态、备注、分类、优先级、时间与手动顺序。
- 主题、静音和全局快捷键偏好。
- 成就进度与已解锁成就。
- 提醒领取和跨重启去重。
- Python sidecar 的启动、健康检查、监控、重试和退出。
- SQLite schema 版本与后续迁移机制。
- macOS arm64 的 sidecar 和 Tauri 打包流程。

### 2.2 非目标

- 用户、账号、登录和权限系统。
- 云端服务、多设备同步或远程访问。
- 旧 `localStorage` 数据迁移；改造后的首次启动视为全新安装。
- 备份、恢复、数据库路径选择或数据库管理界面。
- Windows、Linux 或 Intel Mac 支持。
- 服务端分页、复杂搜索或统计查询。
- 与数据库改造无关的界面重构或新任务功能。

## 3. 总体架构

系统分为三个运行层：

```text
React 前端
   |  localhost HTTP + 临时 Bearer Token
   v
Python FastAPI sidecar
   |
   v
SQLite

Tauri 桌面层负责启动、监控和关闭 Python sidecar，
并继续提供窗口、托盘、全局快捷键和开机自启动等系统能力。
```

职责边界如下：

- React 前端负责界面、临时视图状态、筛选、搜索、时间视图和用户反馈。
- Python 后端负责 API 校验、持久化业务操作、事务、SQLite 访问和 schema 迁移。
- Tauri 桌面层负责原生应用生命周期、sidecar 生命周期和操作系统集成，不承担数据库业务。
- React 组件不直接调用 `fetch`；统一通过 TypeScript API client 访问后端。
- 普通浏览器运行时不提供存储降级，只显示“请通过桌面应用运行”。

## 4. 项目目录

目标目录结构：

```text
frontend/
  src/
  package.json
  vite.config.ts
  vitest.config.ts
  tsconfig.json

backend/
  pyproject.toml
  uv.lock
  src/todo_backend/
  migrations/
  tests/

desktop/
  package.json
  src-tauri/
    Cargo.toml
    tauri.conf.json
    src/

docs/
  frontend/
  backend/
  architecture/
  development-logs/
```

根目录保留 `README.md` 和 `AGENTS.md` 作为项目入口。现有历史开发日志继续保留其历史事实；当前说明文档按职责移动到对应目录。桌面层使用独立的 Node 包承载 Tauri CLI，使 `desktop/src-tauri` 保持 Tauri 的标准结构，并通过 Tauri 配置调用 `frontend` 的开发和构建命令。

## 5. Python 环境与代码边界

后端采用 FastAPI、Uvicorn、Pydantic、标准库 `sqlite3` 和 PyInstaller。`uv` 负责：

- 固定 Python 版本和依赖声明。
- 生成并校验 `uv.lock`。
- 创建开发环境。
- 运行测试、静态检查、类型检查和 PyInstaller。

后端内部按职责分为：

- `api`：路由、请求与响应模型、认证依赖和错误映射。
- `services`：任务完成、成就计算、提醒领取和设置等用例。
- `repositories`：明确的 SQL 查询和行数据转换。
- `database`：连接、事务、PRAGMA 和迁移执行。
- `main`：读取受控启动参数并启动仅监听回环地址的 HTTP 服务。

API 的 Pydantic 模型与数据库行模型分开，避免把表结构直接暴露给前端。

## 6. Sidecar 启动与生命周期

应用采用单实例运行。首次实例的启动流程为：

1. Tauri 获取应用数据目录并确定 SQLite 文件绝对路径。
2. Tauri 生成仅本次运行有效的随机访问令牌。
3. Tauri 选择可用的 `127.0.0.1` 端口。
4. Tauri 向 sidecar 传入数据库路径、端口和令牌。
5. Tauri 启动 PyInstaller 生成的后端可执行文件。
6. Tauri 使用带令牌的健康检查等待后端就绪。
7. React 通过受限的 Tauri command 获取本次后端地址和令牌。
8. React 调用 bootstrap API，成功后才显示主界面。

端口发生竞争时，Tauri 更换端口并有限次数重试。sidecar 启动具有明确超时。关闭窗口到托盘时 sidecar 保持运行；真正退出应用时，Tauri 正常终止 sidecar。Python 捕获终止信号，停止接受新请求并关闭数据库连接。

Tauri 监控子进程退出事件。sidecar 意外退出时，前端进入阻断错误页；用户点击重试后，由 Tauri 重启后端、重新执行健康检查，并由 React 重新获取完整数据快照。

## 7. SQLite 数据模型

数据库不包含用户表或 `user_id`。主要表如下。

### 7.1 `tasks`

| 字段 | 类型 | 约束与说明 |
| --- | --- | --- |
| `id` | TEXT | 主键 |
| `text` | TEXT | 非空 |
| `completed` | INTEGER | 非空，限定为 0 或 1 |
| `priority` | TEXT | 非空，限定为 low、medium、high |
| `created_at` | INTEGER | 非空，Unix 毫秒时间戳 |
| `time_start` | TEXT | 可空，本地 ISO 日期时间 |
| `time_end` | TEXT | 可空，本地 ISO 日期时间 |
| `category` | TEXT | 非空，默认为 other，限定为现有分类 |
| `notes` | TEXT | 可空 |
| `position` | INTEGER | 非空，手动排序位置 |

为 `position` 建立索引。新增、删除和重排在事务中维护位置，不使用唯一约束，以避免批量换位过程产生暂时冲突。

### 7.2 `achievement_state`

固定单行，保存连续完成天数、最后活跃日期、今日完成数量和今日日期。

### 7.3 `achievement_unlocks`

每行保存一个已解锁成就 ID。成就名称、图标和说明仍由前端展示定义维护，不复制到数据库。

### 7.4 `task_reminders`

保存 `task_id`、`scheduled_start` 和 `claimed_at`。`(task_id, scheduled_start)` 为复合主键，`task_id` 外键关联任务并级联删除。任务重新安排时间后可以再次提醒。

### 7.5 `app_settings`

固定单行，保存主题、静音状态和全局快捷键。开机自启动以 macOS/Tauri autostart 插件的系统真实状态为准，不重复写入 SQLite。

### 7.6 连接与迁移

每个连接启用：

- `PRAGMA foreign_keys = ON`
- WAL 日志模式
- 有界的 `busy_timeout`

`backend/migrations/` 保存按顺序编号的 SQL 文件，`PRAGMA user_version` 记录当前版本。迁移在事务内执行；任一步失败即回滚并保留原版本。数据库版本高于当前后端支持版本时拒绝启动。应用不会自动删除、覆盖或重建损坏的数据库。

## 8. API 设计

API 使用 `/api/v1` 前缀。初始接口为：

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/v1/health` | Tauri 就绪检查 |
| `POST /api/v1/bootstrap` | 初始化数据库并返回完整应用快照 |
| `POST /api/v1/tasks` | 新增任务 |
| `PATCH /api/v1/tasks/{id}` | 编辑任务 |
| `DELETE /api/v1/tasks/{id}` | 删除任务 |
| `PUT /api/v1/tasks/order` | 事务性保存手动顺序 |
| `PUT /api/v1/tasks/{id}/completion` | 事务性更新完成状态和成就 |
| `POST /api/v1/reminders/claim` | 原子领取提醒 |
| `PATCH /api/v1/settings` | 保存应用设置 |

bootstrap 请求携带当前系统明暗偏好。仅当数据库尚无设置记录时，后端据此建立初始主题；其余默认值沿用现有应用行为。bootstrap 响应包含任务、设置和成就快照，提醒记录由后端内部管理，无需完整暴露给前端。

筛选、搜索和时间视图仍在前端基于完整任务列表计算。本次不增加服务端分页。

## 9. 数据一致性

所有写操作采用数据库优先策略：

- API 事务成功后，前端才更新内存状态。
- 写入失败时不保留乐观更新。
- 完成任务的接口在同一事务中更新任务状态和成就进度，并返回新的成就状态与新解锁成就。
- 将已完成任务恢复为未完成时不回退成就进度，保持现有规则。
- 排序接口在一个事务中更新全部受影响的位置。
- 提醒接口使用 `INSERT OR IGNORE` 原子领取；只有首次领取成功时前端才播放声音并发送系统通知。
- 修改任务时间时清理该任务旧时间对应的提醒记录；删除任务时依靠外键级联清理。

全局快捷键需要跨越操作系统和数据库两个边界。Tauri 先注册新快捷键，成功后由后端保存设置；若保存失败，Tauri 恢复先前快捷键，并向前端报告失败。

## 10. 错误处理与恢复

### 10.1 业务错误

无效输入、任务不存在和快捷键格式错误等返回稳定的 4xx 错误代码。前端保持原状态并显示简短提示，不退出主界面。

### 10.2 数据库错误

数据库打开、迁移、查询或事务提交失败时，后端返回稳定的基础设施错误代码。前端立即停止后续数据操作并进入阻断式数据库错误页。

### 10.3 Sidecar 错误

启动超时、进程崩溃或健康检查失败由 Tauri 转换为稳定错误状态，前端进入后端不可用页面。

阻断错误页只提供重试，不回退到内存或 `localStorage`。恢复成功后，React 使用新的 bootstrap 快照整体替换旧状态，不继续使用可能过期的内存数据。

底层异常写入后端或 Tauri 日志。前端不显示 SQL、数据库路径、令牌或 Python traceback。

## 11. 安全边界

- 后端只监听 `127.0.0.1`，不监听局域网接口。
- 每次启动生成高强度随机 Bearer Token，所有 API 请求均验证令牌。
- 令牌只保存在当前进程内存中，不写入磁盘或日志。
- CORS 仅允许生产 Tauri 来源和明确的 Vite 开发来源。
- 日志不记录令牌、完整请求正文或用户任务内容。
- 请求模型限制文本长度并拒绝未知或非法枚举值。
- Tauri 仅向主窗口暴露读取当前后端连接信息和重试后端所需的最小 command。

该令牌用于隔离本机其他普通进程的偶然访问，不等同于用户账号或远程认证系统。

## 12. 测试策略

### 12.1 Python 后端

通过 `uv run pytest` 使用临时目录中的真实 SQLite 文件，覆盖：

- 首次建库、默认值、重复启动和 schema 迁移。
- API 令牌验证和 CORS 配置。
- 任务 CRUD、排序、字段约束和行转换。
- 任务完成与成就更新的原子事务。
- 提醒领取、去重、改期和删除清理。
- 设置读写。
- 事务失败回滚。
- 数据库版本过高和损坏场景。
- FastAPI 错误响应不泄露内部信息。

后端同时运行 Ruff 和 Pyright。

### 12.2 React 前端

Vitest 使用可替换的 API client 测试替身，覆盖：

- 启动加载、成功、阻断错误和重试。
- 非 Tauri 环境的不支持页面。
- API 成功后才更新状态。
- 写入失败时保持原状态。
- 完成任务后的成就、声音和礼花触发时机。
- 现有筛选、搜索、排序和组件行为。

### 12.3 Tauri 桌面层

Rust 自动化测试覆盖端口与令牌生成、sidecar 生命周期状态和错误映射。打包后执行人工冒烟测试：

1. 启动内置后端。
2. 新增、编辑、排序和完成任务。
3. 修改主题、静音和快捷键。
4. 触发或验证提醒去重。
5. 退出并重启应用。
6. 确认全部持久化状态正确恢复。

## 13. 构建与发布

构建顺序为：

1. `uv sync --frozen` 安装锁定的后端依赖。
2. 通过 `uv run` 执行测试、Ruff 和 Pyright。
3. 通过 `uv run pyinstaller` 生成 macOS arm64 后端可执行文件。
4. 将产物复制为 Tauri external sidecar 要求的 target 名称。
5. 构建 React 前端并执行 TypeScript 与 Vitest 检查。
6. 构建 Tauri `.app` 和 `.dmg`。
7. 签名主程序、框架、动态库和内嵌 Python sidecar。
8. 对最终 `.app` 执行启动与重启持久化冒烟测试。

构建产物为自包含桌面应用，最终用户无需安装 Python、`uv` 或单独启动后端。

## 14. 文档职责

- `docs/frontend/`：React 架构、组件、状态管理和前端测试。
- `docs/backend/`：uv 环境、API、SQLite schema、迁移、后端测试和故障排查。
- `docs/architecture/`：跨层进程关系、启动流程、错误恢复、安全和打包设计。
- `docs/development-logs/`：保留按版本记录的历史事实。

根 README 提供整体入口和各层文档链接，不复制各层的详细操作说明。

## 15. 验收标准

- 项目中不再使用 `localStorage` 持久化任务、成就、提醒、主题、静音或快捷键。
- 数据库为空时不导入任何旧 `localStorage` 数据。
- 普通浏览器不提供功能性存储降级。
- 重启桌面应用后，任务、顺序、成就、提醒去重状态和设置正确恢复。
- 数据库或 sidecar 不可用时无法进入或继续操作主界面。
- 最终用户无需安装 Python 或 `uv`。
- Python、React 和 Rust 自动化检查全部通过。
- 打包后的 macOS arm64 `.app` 能启动内置 sidecar，并通过重启持久化冒烟测试。
- 不引入账号、云同步、备份恢复或与本次存储改造无关的功能。
