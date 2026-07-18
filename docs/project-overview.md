# TodoList 项目总览

TodoList 是一个无需账号的本地桌面待办应用。React 负责交互与展示，Python 后端负责业务数据和 SQLite 持久化，Tauri 负责桌面生命周期及两者之间的安全连接。

## 技术栈

| 层 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | React 19、TypeScript 5.8、Vite 7、Plain CSS | UI、筛选搜索、视觉效果、提醒扫描 |
| 后端 | Python 3.12、FastAPI、Pydantic、标准库 `sqlite3` | 校验、CRUD、成就事务、提醒 claim、设置 |
| 桌面 | Tauri 2、Rust | sidecar 监督、托盘、快捷键、自启动、打包 |
| 数据 | SQLite WAL | 本机单文件持久化和迁移 |
| 测试 | Vitest、Testing Library、pytest、Rust tests | 前端、API、数据库和进程监督验证 |

Python 环境由 `uv` 管理。后端通过 PyInstaller 打成 Tauri external binary，用户无需单独安装 Python。

当前稳定版本为 **v1.0.0**。该版本首次把 Python/SQLite 后端作为正式桌面发行架构，并提供可持久化的中英文界面切换。

## 数据流

1. Tauri 在应用数据目录选择 `todo.sqlite3`，生成随机端口和 256-bit token。
2. Python sidecar 只监听 `127.0.0.1`，执行迁移并开放 `/api/v1`。
3. React 通过 Tauri command 获取连接信息，再调用 bootstrap 读取完整快照。
4. mutation 只有在后端成功后才更新 React state；基础设施错误会切换到阻断恢复页。
5. 用户显式重试时，Tauri 停止旧 sidecar、生成新连接，React 用新的 bootstrap 快照整体替换内存状态。

详见 [运行架构](architecture/runtime.md)。

## 数据所有权

SQLite 保存：

- 任务内容、顺序、分类、优先级和时间
- 界面语言、主题、静音和全局快捷键
- 成就状态与已解锁徽章
- 已 claim 的提醒时间

React 只保留当前筛选、搜索、弹窗、pending 控件和动画计时等临时 UI 状态。生产代码没有 `localStorage` 持久化，也没有账号或云同步。

## 目录

```text
backend/
├── migrations/                 SQL 迁移
├── src/todo_backend/           API、service、repository、sidecar
└── tests/                      pytest
frontend/
├── src/app/                    bootstrap gate 与应用编排
├── src/features/               业务功能
└── src/shared/api/             typed API client/contracts
desktop/
├── scripts/                    sidecar 构建与 macOS 签名
└── src-tauri/                  Rust 桌面壳和配置
docs/
├── architecture/               运行、安装、设计与计划
├── backend/                    开发、API、数据库
├── frontend/                   前端测试
└── development-logs/           历史版本记录
```

## 核心行为

- 任务 CRUD、完成和排序采用数据库优先更新。
- 完成任务与成就状态在同一 SQLite 事务中提交。
- 提醒 claim 会原子核对任务当前时间和完成状态，避免重复或陈旧通知。
- 快捷键注册与 SQLite 设置更新由 Rust 事务式编排，失败时回滚旧快捷键。
- sidecar 意外退出后不自动静默重启；主界面阻断，只有显式重试才启动新的 backend wave。
- 浏览器直接打开前端时显示不支持页，避免形成第二套数据语义。
- 首页语言按钮以数据库优先方式保存 `zh-CN` 或 `en`；所有第一方界面文案、日期、通知与错误随语言切换，任务标题和备注不翻译。

## 常用命令

```bash
uv sync --directory backend --frozen
uv run --directory backend pytest
uv run --directory backend ruff check .
uv run --directory backend pyright

npm --prefix frontend test
npm --prefix frontend run build

bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
npm --prefix desktop run build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
```

## 历史版本

v0.1.0 至 v1.0.0 的开发事实保留在 [development-logs](development-logs/) 中。旧日志可能提到当时的单目录、浏览器运行或 `localStorage`，不应作为当前操作指南；当前说明以本页和分类文档为准。
