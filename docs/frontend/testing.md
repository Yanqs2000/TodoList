# 前端测试指南

前端位于 `frontend/`，使用 Vitest 和 Testing Library。测试以 typed API fake、deferred Promise 和组件交互验证数据库优先更新、pending 控件及失败恢复；不会启动真实 Python sidecar。

## 安装与运行

```bash
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build
```

开发时可只跑一个文件：

```bash
npm --prefix frontend test -- src/features/tasks/hooks/__tests__/useTodos.test.ts
```

其他脚本：

```bash
npm --prefix frontend run test:watch
npm --prefix frontend run test:coverage
npm --prefix frontend run dev
```

直接运行 Vite 只适合 UI 开发；普通浏览器会显示“不支持”启动页，不提供持久化数据。完整交互应使用 `npm --prefix desktop run dev`。

## 测试分布

- `src/shared/api/__tests__/`：Bearer header、超时、错误分类和 API 路由
- `src/app/**/__tests__/`：bootstrap、重试、阻断门禁和 App 接线
- `src/features/tasks/`：数据库优先 mutation、并发与局部 pending
- `src/features/achievements/`：服务端成就快照与 toast
- `src/features/reminders/`：到期扫描和 atomic claim
- `src/features/theme/`、`sound/`、`desktop/`：设置提交与 Tauri bridge

## 编写原则

- 行为变更先写一条能失败的最小测试，再实现。
- mutation 测试应确认 API resolve 前 state 不变，成功后使用服务端响应，失败后保持最后确认状态。
- 基础设施错误应进入 blocker；业务错误只做局部反馈。
- 测异步状态时使用 deferred Promise 和 `act`，不要依赖真实时间或网络。
- 不重复覆盖 Rust 已保证的 sidecar/快捷键事务内部细节。

Node 可能打印 experimental `localStorage` warning；它来自 jsdom/测试环境，生产前端没有 `localStorage` 访问。
