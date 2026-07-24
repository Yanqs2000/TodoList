# 2026-07-22 — Agent 回复超时修复

## 状态

- 分支：`dev-agent`
- 发布状态：未发布；已生成本地 macOS arm64 测试包
- 故障范围：AI 助手规划阶段、失败重试和桌面打包验证
- 结果：根因已修复，并使用原失败 turn 的安全数据库快照完成包内真实请求验证

## 用户可见症状

用户向 AI 助手发送消息后，助手消息显示“这条回复失败了，可以重试”。点击重试仍得到相同结果。

接口保持既有幂等设计：同一 `turnId` 的失败重试复用原 turn，不重复插入用户消息；失败信息通过 `message.status = "failed"` 和 turn 的稳定错误码记录。因此界面上的通用失败提示不能直接区分错误分类修复与真正的上游请求恢复。

## 第一轮修复为什么无效

第一轮修改只让 `ArkUnavailableError` 穿过 LangGraph 工作流，并把 turn 的 `last_error` 从通用的 `TURN_GRAPH_FAILED` 正确记录为 `ASSISTANT_UNAVAILABLE`。

这项修改改善了错误分类，但没有改变 Ark 请求本身。用户再次重试时仍然失败，因此不能视为完成了故障修复。

核查安装包、运行进程和 PyInstaller 字节码后，确认当时运行的确实是包含错误分类修改的新 sidecar；故障并非由“仍在运行旧二进制”造成。

## 根因

规划请求原先采用以下策略：

1. 以 `thinking: {"type": "enabled"}` 发起非流式 `submit_plan` Function Calling 请求。
2. 只有请求返回 OpenAI SDK `BadRequestError` 时，才关闭 thinking 并重试一次。
3. 客户端总超时为 60 秒，`max_retries=0`。

真实请求没有返回 400，而是在深度思考期间触发以下异常链：

```text
ArkUnavailableError
└── APITimeoutError
    └── ReadTimeout
        └── ReadTimeout
```

由于超时不是 `BadRequestError`，原有 disabled-thinking fallback 永远不会执行。异常随后被转换为 `ASSISTANT_UNAVAILABLE`，最终表现为回复失败。

这不是模型不支持 thinking，而是同步、非流式、60 秒交互式请求与深度思考的延迟特性不匹配。方舟的 [Function Calling 文档](https://www.volcengine.com/docs/82379/1262342?lang=zh) 建议工具调用场景关闭 thinking 以提高效率；[深度思考文档](https://www.volcengine.com/docs/82379/1449737?lang=zh) 也提示非流式深度思考需要流式输出或显著更长的超时。

## 根因实验

实验使用真实数据库和 LangGraph checkpoint 的只读一致性快照。未输出 API Key、消息正文、回复正文或完整模型载荷，未修改生产数据库；临时快照在验证后删除。

### 对照一：保持 thinking enabled

- 使用与失败 turn 完全相同的规划消息和工具 schema。
- 结果：60.210 秒后失败。
- 底层错误：`APITimeoutError` / `ReadTimeout`。

### 对照二：只关闭 thinking

- 除 `thinking=disabled` 外，请求上下文保持不变。
- 首次模型响应耗时 3.248 秒。
- 首次计划存在 schema 错误，由既有 plan-repair 流程处理；证明请求已越过原来的网络超时点。

### 对照三：完整工作流

- 使用正常 `ArkClient` 和修复后的源码，在新的数据库/checkpoint 快照上执行同一 turn。
- 结果：turn 与 assistant message 均进入 `done`，`last_error` 清空。
- 源码工作流验证耗时 3.550 秒。

## 修复方案

`ArkClient.plan()` 现在对结构化规划请求直接发送：

```json
{
  "thinking": {
    "type": "disabled"
  }
}
```

同时保留以下边界：

- 继续使用 object 形式的 `tool_choice` 强制调用 `submit_plan`。
- 单次 `ArkClient.plan()` 只发起一次 Ark 请求；不增加隐式网络重试。
- 计划 schema 不合法时，仍由既有 LangGraph plan-repair 流程重新规划。
- 删除 `planning_thinking_supported` 能力状态、`BadRequestError` fallback、对应日志事件及失效测试。
- Ark 服务不可用时，仍保存稳定错误码 `ASSISTANT_UNAVAILABLE`。

禁用范围针对当前低延迟交互路径，不代表项目永久禁止深度思考。未来若要在复杂只读分析中重新开启 thinking，应同时设计流式输出、取消机制、独立超时预算和端到端回归测试；结构化 CRUD 规划仍应保持 disabled。

## 回归测试

新增或调整的关键断言包括：

- `ArkClient.plan()` 必须发送 `thinking=disabled`。
- `tool_choice` 必须强制指定 `submit_plan`。
- Ark 通用异常只产生一次 provider 调用，不触发旧 fallback。
- 同一服务跨 turn 仍复用 Ark client，但不再依赖 thinking 能力缓存。
- `ArkUnavailableError` 在工作流中保持为 `ASSISTANT_UNAVAILABLE`。

## 验证结果

### 自动化验证

- 后端完整测试：`304 passed, 1 skipped`。
- Ruff：`All checks passed!`。
- 前端 Vitest：`178 passed`。
- Rust 桌面端：`14 passed`。
- 包内 sidecar smoke test：`1 passed`。
- `git diff --check`：通过。

### 构建与包验证

- Node：本机 `/opt/homebrew/bin/node`，`v26.3.0`。
- `npm --prefix desktop run build`：成功生成 `.app` 和 `.dmg`。
- `npm --prefix desktop run sign:macos`：成功。
- `.app` 与 `.dmg` 的 `codesign --verify`：通过。
- `hdiutil verify`：DMG 校验通过。
- 主程序和 Python sidecar：均为 macOS arm64 Mach-O。

### 包内真实请求验证

使用新 `.app` 内嵌的 `todo-backend` 启动隔离 sidecar，并在临时数据库/checkpoint 快照上重试原失败 turn：

```text
HTTP status:       200
Elapsed:           11.291 seconds
Message status:    done
Turn status:       done
Last error:        null
Proposal batches:  1
```

该验证直接覆盖了用户报告的“发送或重试后回复失败”症状，而不只是单元测试或源码级调用。

## 构建产物

- `.app`：`desktop/src-tauri/target/release/bundle/macos/Todo List.app`
- `.dmg`：`desktop/src-tauri/target/release/bundle/dmg/Todo List_1.0.0_aarch64.dmg`
- 新包 sidecar SHA-256：`c4c43f343825079108fd71fee2a3d76a423bb8c2db7ca883cd4aabee6dadd3de`

构建产物不会自动覆盖 `/Applications/Todo List.app`。复测前必须完全退出已安装应用并用新 DMG 覆盖安装；否则仍会启动旧 sidecar，并继续复现旧故障。

## 文档兼容说明

`docs/superpowers/plans/2026-07-22-langgraph-agent-redesign.md` 是实施时的历史计划，其中“先 enabled、仅在 BadRequest 时 fallback、跨 turn 缓存能力”的设计已被本次真实故障证伪。后续开发应以当前实现和本日志为准，不应从历史计划恢复该逻辑。
