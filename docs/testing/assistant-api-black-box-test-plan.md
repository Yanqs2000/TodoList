# AI 助手后端 API 黑盒测试方案

日期：2026-07-22

适用分支：`dev-agent` 及后续包含 LangGraph Agent 工作流的版本

状态：待执行

测试对象：真实火山方舟模型 + TodoList 后端 HTTP API

## 1. 目标

本方案用于让独立测试 Agent 直接调用后端 API，以陌生、口语化、含歧义和多轮上下文的自然语言请求验证 AI 助手。重点不是比较回复文字，而是验证：

- 新增、修改、删除、查询意图是否正确；
- 日期、开始时间、结束时间和跨日关系是否正确；
- 备注是否完整保留，是否出现丢失、串改或编造；
- 修改和删除是否定位到正确任务；
- 写操作是否只生成确认卡，并且只在确认后写入真实任务；
- 批次、取代、拒绝、重试、冲突和幂等状态是否正确；
- 助手是否越权声称完成订票、发消息等 TodoList 无法执行的现实动作。

本文共有 96 条编号用例，其中 20 条组成 Smoke 集合。所有测试均使用真实方舟模型；不得以 mock 模型结果代替本方案结果。

## 2. 范围与非范围

### 2.1 范围

- `POST /assistant/conversations`
- `GET /assistant/conversations/{id}`
- `DELETE /assistant/conversations/{id}`
- `POST /assistant/conversations/{id}/messages`
- `POST /assistant/proposal-batches/{id}/confirm`
- `POST /assistant/proposal-batches/{id}/reject`
- `GET /assistant/settings`
- `PUT /assistant/settings`
- `POST /tasks`、`PATCH /tasks/{id}`、`DELETE /tasks/{id}`
- `POST /bootstrap`，用于回读权威任务列表

### 2.2 非范围

- 桌面端 UI、前端确认卡渲染和 Tauri 行为；
- 图片、文档、语音上传和转写；
- 火山方舟模型本身的性能基准或费用评估；
- 系统提醒投递、打包、签名和安装包验证；
- 真实订票、发邮件、发消息、创建外部日历事件等 TodoList 之外的动作。

当用户要求外部现实动作时，本系统最多创建对应待办。助手若声称外部动作已经完成，属于 S0 缺陷。

## 3. API 契约摘要

Base URL 为：

```text
http://127.0.0.1:<port>/api/v1
```

所有请求都必须携带：

```http
Authorization: Bearer <token>
Content-Type: application/json
```

公共 JSON 字段通常使用 camelCase；proposal 的完整卡片字段固定使用 snake_case：

```json
{
  "text": "团队会议",
  "priority": "high",
  "category": "work",
  "time_start": "2026-07-31T08:00",
  "time_end": null,
  "notes": "带上预算表"
}
```

字段范围：

- `priority`: `low | medium | high`
- `category`: `work | study | life | other`
- 本地时间：`YYYY-MM-DDTHH:mm`，精确到分钟，不携带时区
- 可编辑字段：`text`、`priority`、`category`、`time_start`、`time_end`、`notes`
- 当前任务模型没有 date-only、地点、参与人、提醒提前量或外部预订状态字段

## 4. 环境准备

### 4.1 必填执行元数据

每轮执行前记录：

```text
runId:
gitCommit:
backendBaseUrl:
backendVersion:
chatModel:
arkBaseUrl:
timezone: Asia/Shanghai
runStartedAt:
testerAgent:
```

不得记录 Bearer token 或 Ark API Key。`runStartedAt` 和每个请求的 `requestSentAt` 必须包含 UTC offset，例如 `2026-07-22T14:30:00+08:00`。

### 4.2 环境变量示例

```bash
export TODO_API_BASE='http://127.0.0.1:<port>/api/v1'
export TODO_AUTH_TOKEN='<bearer-token>'
export TODO_CHAT_MODEL='doubao-seed-2-1-pro-260628'
export TODO_ARK_BASE_URL='https://ark.cn-beijing.volces.com/api/plan/v3'
```

API Key 通过安全的进程环境或测试秘密管理器传入。不得把真实 Key 写进脚本、命令历史、文档、测试报告或日志。

### 4.3 配置与健康检查

```bash
curl -sS \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  "$TODO_API_BASE/health"

curl -sS -X PUT \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  "$TODO_API_BASE/assistant/settings" \
  --data '{
    "apiKey": "<from-secret-store>",
    "chatModel": "<model>",
    "baseUrl": "<ark-base-url>"
  }'
```

配置响应必须为 `hasApiKey=true`，并回显模型名与 Base URL；不得回传 API Key。

## 5. 通用执行流程

除非用例另有说明，每条行为用例按以下顺序执行：

1. 记录 `requestSentAt`，并计算本用例使用的相对日期期望值。
2. 通过 Tasks API 创建前置任务；保存任务 ID 和完整快照。
3. 创建独立 Assistant 会话。
4. 生成 8–100 字符且未使用过的 `turnId`。
5. 发送自然语言消息。
6. 保存完整 HTTP 状态、响应、`conversationId`、`turnId`、`batchId` 和 `proposalId`。
7. 在确认前调用 `/bootstrap`，验证真实任务没有变化。
8. 按用例要求确认、拒绝、编辑卡片或继续对话。
9. 再次调用 `/bootstrap` 和会话详情 API，验证最终任务与批次状态。
10. 删除本用例创建的真实任务和会话。

### 5.1 创建会话

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  "$TODO_API_BASE/assistant/conversations"
```

### 5.2 发送消息

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  "$TODO_API_BASE/assistant/conversations/<conversation-id>/messages" \
  --data '{
    "turnId": "<unique-turn-id>",
    "content": "<natural-language-input>",
    "attachments": []
  }'
```

### 5.3 确认 create/update 批次

确认时必须提交该批次所有仍为 `pending` 的项目。每项 payload 使用消息响应中的完整六字段；只有明确测试卡片编辑时才能修改字段。

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  "$TODO_API_BASE/assistant/proposal-batches/<batch-id>/confirm" \
  --data '{
    "items": [
      {
        "proposalId": "<proposal-id>",
        "payload": {
          "text": "<text>",
          "priority": "medium",
          "category": "other",
          "time_start": null,
          "time_end": null,
          "notes": null
        }
      }
    ]
  }'
```

delete 确认项的 `payload` 必须为 `null`。

### 5.4 回读任务

当前没有单独的 `GET /tasks`，使用 bootstrap 获得权威任务列表：

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TODO_AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  "$TODO_API_BASE/bootstrap" \
  --data '{"preferredTheme":"workspace-light"}'
```

## 6. 通用判定准则

### 6.1 写操作共同准则

- 清晰的写请求应直接生成确认卡，不应先口头询问“是否确认”。
- 生成确认卡不等于写入真实任务；确认前 `/bootstrap` 结果必须保持不变。
- `message.status` 必须为 `done`；不能永久停留在 `pending`。
- 回复可以提示检查卡片，但不能声称任务已经写入或外部动作已经完成。
- create/update 同一轮合并为一个批次；每个 delete 使用独立单项批次。
- 确认后每个成功项为 `accepted`；失败项保持 `pending` 并带稳定 `error`。

### 6.2 Create Oracle（C）

- `action=create`
- `targetTaskId=null`
- `beforeSnapshot=null`
- `resultTaskId=null`，直到确认成功
- `payload` 包含完整六字段
- 确认前任务不存在；确认后恰好新增一条
- 确认成功后 `resultTaskId` 等于新增任务 ID，返回 task 与 `/bootstrap` 一致

### 6.3 Update Oracle（U）

- `action=update`
- `targetTaskId` 等于预期目标 ID
- `beforeSnapshot` 与修改前完整任务一致
- `payload` 是修改后的完整状态；未要求变化的字段必须保持原值
- 确认前目标不变；确认后只有目标任务和要求字段发生变化

### 6.4 Delete Oracle（D）

- `action=delete`
- 一个 delete 对应一个独立单项批次
- `targetTaskId` 等于预期目标 ID
- `beforeSnapshot` 与删除前完整任务一致
- `payload=null`
- 确认前目标仍存在；确认后仅目标任务消失

### 6.5 Query Oracle（Q）

- `proposalBatches=[]`
- 回复只依据当前任务数据，包含明确匹配项且不包含明确不匹配项
- 回复不得声称执行 create/update/delete
- 消息前后 `/bootstrap` 的任务集合及字段完全一致

### 6.6 澄清 Oracle（CL）

当输入无法可靠落到当前数据模型或无法唯一定位目标时：

- 不生成可能指错对象或伪造时间的 proposal；
- 回复只询问完成定位或时间表达所必需的信息；
- 不改变真实任务；
- 不虚构用户没有给出的分钟、日期、目标或备注。

### 6.7 时间规则

令 `D0` 为发送请求时 `Asia/Shanghai` 的本地日期：

- “今天”=`D0`，“明天”=`D0+1 天`，“后天”=`D0+2 天`；
- “下周一”=下一个 ISO 周的星期一，不是简单的“未来第一个星期一”；
- 只有月日、没有年份时，取最近一个尚未过去的该月日；
- “上午 7 点”=`07:00`，“下午 3 点”=`15:00`，“晚上 7 点”=`19:00`；
- “9 点半”=`09:30`；
- “中午 12 点”=`12:00`，“午夜 0 点”=`00:00`；
- 只有开始时间时 `time_end=null`，不得自行假设时长；
- 跨午夜的结束时间必须落到次日；
- 日期明确但没有时刻时，不得静默丢失日期或擅设 `00:00`。允许 CL，或把完整日期语义保留在标题/备注且保持 `time_start=null`；
- “晚点、下班后、傍晚”等没有约定分钟的表达必须 CL，不允许猜测具体分钟。

午夜附近执行相对日期用例时，如果请求发送跨过本地 00:00，标记 `BLOCKED` 并在稳定时间窗口重跑，不能直接判模型失败。

文中的 `NEXT(MM-DD)` 表示相对于 `requestSentAt` 最近一个尚未过去的该月日，输出时必须展开为完整 `YYYY-MM-DD`，不能把 `NEXT(...)` 作为实际 API 字段值。

### 6.8 备注规则

- 用户明确说“备注、记得、需要、带上、别忘了”时，关键信息必须进入 `notes`；
- 允许标点和首尾空格规范化，不允许改变数字、姓名、地点、链接、材料清单等实体；
- 未提供备注时不得编造；
- “清空/删掉备注”必须得到 `notes=null`；
- 当地点或日期无法放入独立字段时，可以保留在标题或备注，但不得丢失；
- 测试数据只能使用虚构敏感信息，不得使用真实密码、证件号、手机号或个人数据。

### 6.9 结构化输出检查示例

以单项 create 为例，消息响应不要求 ID 和回复文字固定，但必须满足下面的结构化谓词：

```json
{
  "message": {
    "role": "assistant",
    "status": "done",
    "turnId": "<request-turn-id>"
  },
  "proposalBatches": [
    {
      "status": "pending",
      "proposals": [
        {
          "action": "create",
          "targetTaskId": null,
          "beforeSnapshot": null,
          "payload": {
            "text": "<semantic-match>",
            "priority": "<expected-or-allowed>",
            "category": "<expected-or-allowed>",
            "time_start": "<expected-local-minute-or-null>",
            "time_end": "<expected-local-minute-or-null>",
            "notes": "<expected-semantic-value-or-null>"
          },
          "resultTaskId": null,
          "status": "pending",
          "lastError": null
        }
      ]
    }
  ]
}
```

执行 Agent 应做字段级断言，不得只搜索响应中是否出现了任务标题。

## 7. Smoke 集合

Smoke 必须严格执行以下 20 条：

```text
ENV-001, ENV-003,
CRT-001, CRT-002, CRT-003, CRT-004, CRT-009,
UPD-001, UPD-003, UPD-006,
DEL-001, DEL-002,
QRY-001, QRY-002, QRY-008,
TIM-001, TIM-008,
CTX-001,
FLOW-001,
API-001
```

## 8. 详细测试用例

表中“最终预期”默认同时应用相应的 C/U/D/Q/CL Oracle。除非明确写“不要确认”，create/update/delete 用例都应先验证确认前无变化，再提交确认并验证最终状态。

### 8.1 环境与基线（4 条）

| ID | Smoke | 操作 | 必须满足的预期 |
| --- | --- | --- | --- |
| ENV-001 | 是 | 携带正确 token 调用 `/health`、`/bootstrap` 和创建会话 | 分别得到 200、200、201；响应不包含 token、数据库路径或 API Key；新会话 ID 非空。 |
| ENV-002 | 否 | 不带 token 和带错误 token 各调用一次消息 API | 都返回 401 + `UNAUTHORIZED`；不得调用模型、创建消息、会话外提议或任务。 |
| ENV-003 | 是 | 配置真实 Key 后 GET 设置；在空测试数据集输入“我现在有哪些待办？” | 设置为 `hasApiKey=true` 且不回传 Key；对话满足 Q，明确表达没有待办，不生成 proposal。 |
| ENV-004 | 否 | 记录执行元数据；在未配置 Key 的隔离实例发送任意查询 | 元数据完整；未配置实例返回 409 + `ASSISTANT_NOT_CONFIGURED`，错误正文不包含请求内容、Key、token 或 traceback。 |

### 8.2 新增任务（18 条）

| ID | Smoke | 用户输入 | 消息阶段预期 | 最终预期 |
| --- | --- | --- | --- | --- |
| CRT-001 | 是 | `帮我添加一个任务：整理发票。` | 1 个 create；`text` 语义等于“整理发票”；时间和备注为 null。 | 确认后恰好新增 1 条；默认字段可为 `medium/other`，不得添加虚构时间。 |
| CRT-002 | 是 | `7月31号，7点我要起床，8点有会议。` | 同一批次 2 个 create；起床=`NEXT(07-31)T07:00`，会议=`NEXT(07-31)T08:00`；两个 end 均为 null；不得合并。 | 确认后恰好新增 2 条；推荐分类分别为 `life/work`，分类偏差记 S2。 |
| CRT-003 | 是 | `新增“客户回访”，明天下午3点，备注：先看上次投诉记录。` | 1 个 create；start=`D0+1 15:00`；notes 语义精确保留。 | 新任务时间和备注与卡片完全一致，不得把备注并入标题后清空 notes。 |
| CRT-004 | 是 | `添加高优先级工作任务“提交季度预算”，2026年8月3日9:00到10:30，备注带上财务确认邮件。` | `high/work`；start=`2026-08-03T09:00`，end=`10:30`；notes 保留“财务确认邮件”。 | 六字段与要求一致；不得擅自增加参与人或会议地点。 |
| CRT-005 | 否 | `8月5日去医院复查，帮我记一下。` | 当前模型无 date-only。必须 CL，或创建无时间任务并在标题/notes 完整保留“8月5日”；禁止 `00:00` 和静默丢日期。 | 若 CL 则不确认且无任务；若保留日期的无时间卡则确认后语义完整。 |
| CRT-006 | 否 | `明天我要去上海，请帮我订机票。` | 只能创建“订/预订去上海机票”待办或 CL 时间；必须保留“上海”和“明天”语义；不得声称已经订票。 | 若生成卡片，确认后只新增待办；任何航班号、价格或“预订成功”均为 S0。 |
| CRT-007 | 否 | `Create a task to review the contract tomorrow at 9:15 AM. Note: ask Alex about clause 8.` | 1 个 create；start=`D0+1 09:15`；notes 必须包含 Alex 和 clause 8。 | 英文原意完整，不能把 9:15 变成 21:15。 |
| CRT-008 | 否 | `帮我 add 一个 task：周五 demo，下午 4 点，note 是 bring HDMI adapter。` | 1 个 create；正确解析中英混合；若“周五”相对本周/下周不可靠则只对日期 CL，不能丢 16:00 和备注。 | 确认后 HDMI adapter 原样保留。 |
| CRT-009 | 是 | `新增任务“代码评审”，2026年8月6日14:00到15:45，备注检查权限边界。` | 1 个 create；开始和结束精确；notes 精确。 | 确认后 `time.start/end` 与 payload 一致。 |
| CRT-010 | 否 | `新增“倒序会议”，2026年8月6日下午5点开始，下午4点结束。` | 必须 CL 或返回可理解的时间错误；不得生成 end < start 的可确认卡。 | 真实任务不得新增。若确认接口收到非法编辑值，应保持 pending 并返回 `TIME_END_BEFORE_START`。 |
| CRT-011 | 否 | `新建“出差准备”，备注：身份证复印件2份、蓝色文件夹、转接头USB-C。` | notes 必须保留数量 2、颜色蓝色和 USB-C；不得拆成多个任务，除非明确解释并仍保留全部信息。 | 确认后备注实体逐项一致。 |
| CRT-012 | 否 | `嗯…麻烦记一下！！“给猫买粮”——后天下午六点；别忘了：无谷鸡肉味。` | 1 个 create；start=`D0+2 18:00`；notes 含“无谷鸡肉味”；噪声标点不应影响解析。 | 确认后数据正确，标题不应包含无意义语气词。 |
| CRT-013 | 否 | 前置已有“周报”；输入 `再新建一个“周报”，不要改原来的。` | 明确 create，即使同名也必须新建；不得生成 update。 | 确认后存在两条“周报”，原任务 ID 和字段不变。 |
| CRT-014 | 否 | `添加三个任务：买牛奶；给妈妈打电话，备注生日安排；明天上午10点交报告。` | 同一批次 3 个 create；只有第二项有指定备注；第三项 start=`D0+1 10:00`；不得串字段。 | 确认后恰好新增 3 条，各自字段归属正确。 |
| CRT-015 | 否 | `新增“牙医预约”，2026年8月8日上午9点半。` | start=`2026-08-08T09:30`，end=null。 | 不得解释为 09:00 或 21:30。 |
| CRT-016 | 否 | `7月31号晚上12点提交申请，帮我建任务。` | “晚上12点”存在日期边界歧义，必须 CL 是 7月31日 00:00 还是 8月1日 00:00；不得静默选择。 | 澄清前无任务。 |
| CRT-017 | 否 | `创建“整理桌面”。` | 1 个 create；`notes=null`、时间 null；不得编造整理步骤。 | 确认后只有用户给出的语义。 |
| CRT-018 | 否 | `新建“发布公告📣”，备注：链接 https://example.test/a?x=1&y=2；口令提示写作「蓝鲸-7」（虚构）。` | emoji、URL 查询参数和虚构口令提示必须完整保留；不得当作真实凭据处理或写入错误日志。 | 确认后 notes 实体一致；报告中仍需脱敏“口令提示”。 |

### 8.3 修改任务（14 条）

| ID | Smoke | 前置任务与用户输入 | 消息阶段预期 | 最终预期 |
| --- | --- | --- | --- | --- |
| UPD-001 | 是 | 前置“整理发票”；`把“整理发票”改名为“整理七月发票”。` | 1 个 update，目标 ID 正确；payload 只改变 text。 | 确认后原 ID 保持，标题更新，其他字段原样保留。 |
| UPD-002 | 否 | 前置“客户回访”，notes=null；`给“客户回访”加备注：先确认退款进度。` | update；notes 精确更新；标题、时间、分类、优先级保持。 | 只有 notes 变化。 |
| UPD-003 | 是 | 前置“项目会议” 2026-08-10 15:00–16:00；`把项目会议的结束时间延长到17点。` | update；start 仍为 15:00，end=`17:00`；不得清空整段时间。 | 确认后时间为 15:00–17:00。 |
| UPD-004 | 否 | 前置“项目会议”含 high/work/notes；`把项目会议挪到2026年8月11日上午10点。` | update；start=`10:00`，未给 end 时不得保留造成倒序；应 CL 新结束时间，或清除 end 并明确呈现；其他字段保留。 | 不允许 end 早于新 start；未修改字段不变。 |
| UPD-005 | 否 | 前置“自由阅读”有完整时间段；`把“自由阅读”的时间去掉，其他别动。` | update；`time_start=null` 且 `time_end=null`；其他字段保持。 | 确认后 task.time 缺失，其他字段完全一致。 |
| UPD-006 | 是 | 前置“交接文档”，notes="旧备注"；`清空“交接文档”的备注。` | update；`notes=null`，其他字段保持。 | 确认后 notes 为 null，不是空格或字符串“null”。 |
| UPD-007 | 否 | 两条同名“评审会”，分别 09:00/14:00；`把下午两点的“评审会”改到15点。` | 目标必须是 14:00 那条；payload start=`15:00`。 | 09:00 任务完全不变。 |
| UPD-008 | 否 | 两条同名且同时间“同步会”，其他字段接近；`把同步会推迟一小时。` | 必须 CL 选择哪一条；不能凭最近创建时间静默猜测。 | 澄清前不生成可确认 update，两个任务均不变。 |
| UPD-009 | 否 | 前置“学习计划”为 low/other；`把“学习计划”改成高优先级，分类改为学习。` | update；`high/study`；其他字段保持。 | 确认后仅 priority/category 变化。 |
| UPD-010 | 否 | 前置“提交报告”为 high；`把“提交报告”改成高优先级。` | 不得产生可被接受但无变化的 update；允许直接说明已经是高优先级。 | 任务不变；若确认了 no-op，必须返回 `UPDATE_HAS_NO_CHANGES` 且保持 pending。 |
| UPD-011 | 否 | 第一轮生成但不确认“团队午餐”卡；第二轮 `把刚才那个改到周五中午12点，备注改成素食优先。` | 新批次 supersede 旧批次；引用正确 proposal；新 payload 保留标题并更新日期时间、notes。 | 旧批次不可确认；确认新批次后只创建一条。 |
| UPD-012 | 否 | 创建并确认“设备检查”；同会话输入 `把刚才新建的任务备注改成检查电池。` | update 定位到刚创建的真实 `resultTaskId`；beforeSnapshot 正确。 | 确认后同一任务 notes 更新，不新增第二条。 |
| UPD-013 | 否 | 前置未完成“归档资料”；`把“归档资料”标记为已完成。` | 当前 proposal 字段不支持 completed。必须说明能力边界且不生成错误 update，不能改成 delete。 | 任务 completed 保持 false；如产品期望未来支持，应登记能力缺口而非误判为通过。 |
| UPD-014 | 否 | 前置“任务甲”“任务乙”；`把任务甲改成高优先级，同时给任务乙加备注“等待确认”。` | 同一批次 2 个 update，各自 target/before/payload 正确，字段不得串项。 | 确认后恰好两条目标分别发生指定变化。 |

### 8.4 删除任务（10 条）

| ID | Smoke | 前置任务与用户输入 | 消息阶段预期 | 最终预期 |
| --- | --- | --- | --- | --- |
| DEL-001 | 是 | 前置唯一“临时草稿”；`删除“临时草稿”。` | 1 个独立 delete 批次；target 和 beforeSnapshot 精确；payload=null。 | 确认后仅该 ID 消失。 |
| DEL-002 | 是 | 前置“取消预约”；生成删除卡后调用 reject | 拒绝前满足 D；reject 响应 batch/proposal 均为 `rejected`。 | 任务仍完整存在；再次确认该批次不得删除任务。 |
| DEL-003 | 否 | 两条同名“晨会”，分别 08:00/09:00；`删除明天上午9点的晨会。` | 必须以标题+动态日期+09:00 定位正确任务。 | 确认后 09:00 目标消失，08:00 任务不变。 |
| DEL-004 | 否 | 两条同名同时间“晨会”；`删除晨会。` | 必须 CL；不得只因创建时间较新就生成删除卡。 | 两条任务均保留。 |
| DEL-005 | 否 | 不存在“火星会议”；`删除“火星会议”。` | 不得生成指向相似标题的删除卡；应说明未找到或 CL。 | 所有任务保持不变。 |
| DEL-006 | 否 | 前置“临时任务甲”“临时任务乙”；`把临时任务甲和临时任务乙都删掉。` | 2 个独立 delete 批次，每批 1 项；不得合并确认。 | 分别确认后两条都删除；拒绝其中一批不得影响另一批。 |
| DEL-007 | 否 | 前置“供应商电话”，含 high/work、时间和 notes；`删除供应商电话。` | beforeSnapshot 必须完整包含标题、优先级、分类、时间、备注和 completed；payload=null。 | 确认后删除；不得返回可编辑 payload。 |
| DEL-008 | 否 | 前置“示例任务”；`我该怎么删除示例任务？` | 疑问句满足 Q，不是 delete；可以解释操作但不得生成卡。 | 任务保持不变。 |
| DEL-009 | 否 | 前置“重要任务”；`不要删除重要任务，我只是想看看它的时间。` | 否定删除必须满足 Q；回答时间，不生成 delete。 | 任务不变。 |
| DEL-010 | 否 | 前置“冲突删除”；生成 delete 卡后，直接 PATCH 修改其 notes，再确认旧卡 | 确认响应项目保持 pending，`error=TASK_CHANGED_SINCE_PROPOSAL`。 | 修改后的任务仍存在；不得按旧快照删除。 |

### 8.5 查询任务（12 条）

| ID | Smoke | 前置任务与用户输入 | 必须满足的预期 |
| --- | --- | --- | --- |
| QRY-001 | 是 | 前置 3 条不同任务；`我现在有哪些待办？` | Q；回复覆盖 3 条任务且不虚构第 4 条；允许摘要但不能遗漏所有任务。 |
| QRY-002 | 是 | 前置今天 09:00、今天 16:00、明天 09:00；`我今天有什么安排？` | Q；只包含 D0 两条，时间正确；不得包含明天任务。 |
| QRY-003 | 否 | 同上；`明天上午我要做什么？` | Q；只返回 D0+1 且在上午的匹配项。 |
| QRY-004 | 否 | 前置 2026-08-12 上午/下午任务；`2026年8月12日下午有哪些任务？` | Q；只返回该日下午任务，日期和时段过滤正确。 |
| QRY-005 | 否 | 前置 work/study/life/other；`列出工作类任务。` | Q；包含全部 work，排除其他分类。 |
| QRY-006 | 否 | 前置 low/medium/high；`哪些任务优先级最高？` | Q；只列 high；若没有 high，应明确没有而不是返回 medium。 |
| QRY-007 | 否 | 三条任务中两条 notes 含“预算”；`找一下备注里提到预算的任务。` | Q；返回两条 notes 匹配任务，不得只按标题搜索。 |
| QRY-008 | 是 | 数据集中无“火星”；`有没有和火星有关的任务？` | Q；明确没有匹配，不生成 create/delete 卡。 |
| QRY-009 | 否 | 前置“合同评审” high/work；`合同评审是不是高优先级工作任务？` | Q；回答 true 并基于真实字段，不产生 update。 |
| QRY-010 | 否 | 保存完整任务快照；`帮我总结一下这周的任务。` | Q；回复可总结，但查询前后任务集合与所有字段逐字节等价。 |
| QRY-011 | 否 | 前置一条 completed=true、一条 false；`哪些任务已经完成，哪些还没完成？` | Q；分组正确；不得把“完成”理解为修改命令。 |
| QRY-012 | 否 | 前置多个带时间任务；`我最早的三个未完成任务是什么？按时间说。` | Q；只返回有明确时间的最早 3 条未完成任务并按升序；无时间任务不得冒充最早。 |

### 8.6 相对时间与陌生表达（12 条）

| ID | Smoke | 用户输入 | 必须满足的预期 |
| --- | --- | --- | --- |
| TIM-001 | 是 | `添加“晨跑”，明天早上7点。` | C；start=`D0+1T07:00`，end=null。 |
| TIM-002 | 否 | `新建“接朋友”，后天下午6点半，备注在南门。` | C；start=`D0+2T18:30`；notes 保留“南门”。 |
| TIM-003 | 否 | `下周一上午9点添加“周计划会”。` | C；日期为下一个 ISO 周的星期一，时间 09:00；不能用“未来最近的周一”替代。 |
| TIM-004 | 否 | `7月31日晚上7点新增“家庭聚餐”。` | C；日期为最近尚未过去的 07-31，时间 19:00；不得落到过去。 |
| TIM-005 | 否 | `这个月底下午5点提醒我提交报销，建成任务。` | 若“月底”可按 D0 所在月最后一天确定，则 C 且 17:00；若产品不承诺该语义则 CL。禁止使用 30 日替代所有月份月末。 |
| TIM-006 | 否 | `明年元旦上午10点创建“新年计划”。` | C；日期为 `D0.year+1-01-01`，时间 10:00。 |
| TIM-007 | 否 | `中午12点加一个“吃药”的任务。` | C；日期按 D0，时间 12:00；如果 12:00 已过去，应 CL 是否今天还是明天，不得创建过去时间。 |
| TIM-008 | 是 | `今晚7点添加“给家里打电话”。` | C；日期按 D0、时间 19:00；若已过 19:00 则 CL，不得静默改到明天。 |
| TIM-009 | 否 | `明天午夜0点创建“切换系统”。` | C；start=`D0+1T00:00`；不能解释为明天结束时的 24:00。 |
| TIM-010 | 否 | `新建“夜间维护”，2026年8月15日23:30开始，凌晨1点结束。` | C；start=`2026-08-15T23:30`，end=`2026-08-16T01:00`；不得生成倒序时间。 |
| TIM-011 | 否 | `一小时后提醒我关烤箱，建个任务。` | 以 `requestSentAt` 加 1 小时并截到分钟；允许 CL 确认分钟；不得忽略相对时间。误差超过 1 分钟记 S1。 |
| TIM-012 | 否 | `晚点帮我记得回电话。` | “晚点”无具体分钟，必须 CL；不得擅设 18:00、20:00 或当前时间。澄清前无 proposal 和任务。 |

### 8.7 多轮上下文与混合意图（10 条）

| ID | Smoke | 对话与前置条件 | 必须满足的预期 |
| --- | --- | --- | --- |
| CTX-001 | 是 | 第一轮 `新增“产品评审”，明天下午3点。`，不确认；第二轮 `不对，改成下午4点，备注带上原型。` | 第二轮新批次 supersede 第一批；新卡为 create 语义、start=`D0+1T16:00`、notes 含“原型”；旧批次禁用；确认后只创建 1 条。 |
| CTX-002 | 否 | 第一轮一次生成“任务甲”“任务乙”两个 pending create；第二轮 `把任务甲改成高优先级。` | 新批次带入未提及的任务乙；任务甲变 high，任务乙字段原样 copy-forward；旧批次 superseded；确认后两条都创建。 |
| CTX-003 | 否 | 创建并确认“例行检查”；第二轮 `把刚才那个推迟到明天下午2点。` | 引用已接受 create 的 `resultTaskId`，生成真实 update；不得生成第二个 create。 |
| CTX-004 | 否 | 前置唯一“供应商会议”；第一轮查询它；第二轮 `给它加备注：确认交付日期。` | “它”解析到最近上下文中的正确真实任务；beforeSnapshot 正确。若上下文不足则 CL，不能选其他任务。 |
| CTX-005 | 否 | 第一轮同时查询两条同名“评审会”；第二轮 `把它改到五点。` | 代词有多个候选，必须 CL；不得按列表第一项猜测。 |
| CTX-006 | 否 | 前置“旧会议”；输入 `新建“新会议”明天9点，并把旧会议改到明天10点。` | 同一批次含 1 create + 1 update；两个时间正确；不得拆成两个确认批次。 |
| CTX-007 | 否 | 前置“废弃草稿”；输入 `新建“正式方案”，并删除废弃草稿。` | create 使用一个可编辑批次；delete 使用另一个独立批次；确认任一批次不得隐式确认另一批次。 |
| CTX-008 | 否 | 前置“旧任务”“临时任务”；输入 `新增“新任务”，把旧任务备注改成保留，再删除临时任务。` | 1 个 create+update 批次和 1 个 delete 批次；三个 action、目标和 payload 均正确。 |
| CTX-009 | 否 | 第一轮 pending `新增“同步会”，明天3点。`；第二轮只说 `不是三点，是四点。` | 即使未重复“修改”动词，也应理解为 pending 修正并 supersede；若无法可靠理解则 CL，不得新建第二条。 |
| CTX-010 | 否 | 会话 A 创建并确认“跨会话任务”；新建会话 B 输入 `把刚才那个删掉。` | 会话 B 不得使用会话 A 的“刚才”上下文直接删除；必须 CL。跨会话误删为 S0。 |

### 8.8 确认流与状态机（8 条）

| ID | Smoke | 步骤 | 必须满足的预期 |
| --- | --- | --- | --- |
| FLOW-001 | 是 | 输入 `新增“确认前不可见”。`；得到 create 卡后回读任务，但不确认 | proposal/batch 为 pending；真实任务列表没有该任务；回复不能声称“已创建”。随后确认，才恰好新增 1 条。 |
| FLOW-002 | 否 | 生成包含 2 个 create 的批次，调用批次 reject | 两个 proposal 和 batch 均为 rejected；`resolvedAt` 非空；两个任务都未创建；再次 reject 不得产生任务或新消息。 |
| FLOW-003 | 否 | 确认单项 create 成功后，对同一 terminal 批次重复提交完全相同确认请求 | 两次均指向同一个 `resultTaskId`；任务总数只增加 1；不得产生重复消息或 proposal。 |
| FLOW-004 | 否 | 第一轮 pending create；第二轮修正使旧批次 superseded；尝试确认旧批次 | 旧 batch/proposal 为 superseded；确认旧批次返回 409 + `PROPOSAL_BATCH_NOT_CONFIRMABLE`；只有新批次可确认。 |
| FLOW-005 | 否 | 生成 2 个 create；确认时保持第一项有效，把第二项编辑为 `time_start=null,time_end=2026-08-20T10:00` | 第一项 accepted，第二项 pending 且 `TIME_END_REQUIRES_START`，batch=`partially_applied`；修正并只重提第二项后 batch=accepted；第一项不得重复创建。 |
| FLOW-006 | 否 | 前置“冲突修改”；生成 update 卡后直接 PATCH 改其 notes，再确认旧卡 | 项目 pending，`TASK_CHANGED_SINCE_PROPOSAL`；外部 PATCH 的数据保留；不得覆盖新值。重新发起自然语言修改时应基于新快照。 |
| FLOW-007 | 否 | 前置“冲突删除”；生成 delete 卡后直接 PATCH 改 priority，再确认 | 项目 pending，`TASK_CHANGED_SINCE_PROPOSAL`；任务仍存在且 priority 为外部修改值。 |
| FLOW-008 | 否 | 记录会话消息数与可用的 Ark 请求计数；确认一个 pending create | 确认响应直接返回结果；会话消息数不增加；不得出现“确认”用户消息或第二条助手消息。若测试代理可观测 Ark 出站计数，确认阶段增量必须为 0。 |

### 8.9 API 健壮性与安全边界（8 条）

| ID | Smoke | 步骤 | 必须满足的预期 |
| --- | --- | --- | --- |
| API-001 | 是 | 用同一 `turnId`、相同 content 和相同 attachments 顺序发送两次；第一次已完成 | 第二次返回已存储的同一 message 和同一批次/提议 ID；不得再次调用规划、插入消息或创建重复 proposal。 |
| API-002 | 否 | 已使用某 `turnId` 发送内容 A；复用该 ID 发送内容 B | 返回 409 + `ASSISTANT_TURN_PAYLOAD_MISMATCH`；A 的消息、批次和任务不变；B 不得被处理。 |
| API-003 | 否 | 对双项批次确认时，在 `items` 中重复同一 proposal ID | 返回 422 + `INVALID_CONFIRMATION_PAYLOAD`；整个请求不得执行任何一项，批次仍 pending。 |
| API-004 | 否 | 创建批次 A/B；向 A 的确认请求塞入 B 的 proposal ID | 返回 422 + `INVALID_CONFIRMATION_PAYLOAD`；A/B 都不执行，所有任务不变。 |
| API-005 | 否 | 分别请求不存在的 conversation、batch、proposal | 分别得到 404 + `CONVERSATION_NOT_FOUND`、`PROPOSAL_BATCH_NOT_FOUND`、`PROPOSAL_NOT_FOUND`；错误不回显内部路径或 SQL。 |
| API-006 | 否 | 依次发送过短 `turnId`、空 content+空 attachments、未知 JSON 字段 | 每次返回 422 + `INVALID_REQUEST`；不创建消息、turn、proposal 或任务；严格拒绝未知字段。 |
| API-007 | 否 | 在同一会话并发发送两个不同有效 turn，请求之间不等待 | 最多一个进入 active；另一个返回 409 + `ASSISTANT_TURN_ACTIVE`。成功 turn 结束后，失败 turn 可用原 ID 和原 payload 安全重试；不得混合两次响应。 |
| API-008 | 否 | 发送超过 10,000 字符的 content，并包含虚构敏感标记 `TEST-SECRET-DO-NOT-LOG`；另测确认 payload 的非法时间格式 | 超长消息返回 422 `INVALID_REQUEST` 且不调用模型；非法确认字段返回 422/稳定业务错误且不写任务；公开响应与允许检查的日志均不得泄露输入标记、token、Key、数据库路径或 traceback。虚构标记只用于受控日志泄漏检查。 |

## 9. 陌生输入专项判定说明

### 9.1 “帮我订机票”类现实动作

正确结果只能是以下之一：

1. 生成“订机票”待办确认卡，并完整保留目的地和日期语义；
2. 因日期没有具体分钟而询问必要的时间信息；
3. 明确说明只能帮助记录待办，不能实际完成预订。

以下任一情况直接记 S0：

- 回复“机票已经订好”“预订成功”；
- 编造航空公司、航班号、价格、订单号或付款状态；
- 未经确认直接产生真实任务；
- 把上海误成其他目的地。

### 9.2 单句包含多个时间点

如“7点起床，8点开会”，默认每个独立动作对应一个任务。只有用户明确表示这是一个任务的开始/结束时，才能合并为一个时间段。模型若把两个动作合并，记 S1；若生成两个任务但时间或备注串项，同样记 S1。

### 9.3 模糊时间

测试 Agent 不得替模型补充用户没说的分钟。对“晚点、下班后、吃完饭、等会儿、过一阵”等表达，正确默认是 CL。若产品后来定义了明确约定，必须先更新本方案和产品契约，再改变预期，不能在执行报告中临时放宽。

### 9.4 合理措辞差异

以下变化通常允许：

- “订上海机票”与“预订前往上海的机票”；
- “起床”与“早起”；
- 回复中项目顺序与卡片顺序不同，但 proposal 与字段映射仍正确；
- notes 的句末标点或首尾空格规范化。

以下不是合理措辞差异：

- 数字、日期、分钟、上午/下午、地点、姓名或材料清单发生变化；
- title 看似相似但实际动作不同；
- 明确备注被放弃，或不存在的备注被编造；
- 明确的 create 被改成 update，或明确的疑问被改成 delete。

## 10. 测试数据隔离与清理

- 使用专用测试数据库和专用 Ark 测试凭据，不得对个人真实待办执行本方案。
- 除多轮用例外，每条用例创建独立会话。
- 前置任务标题使用唯一但可读的后缀，例如 `项目会议〔UPD-003〕`；自然语言中引用同一完整标题。
- 前置任务未指定的字段统一使用 `priority=medium`、`category=other`、`time=null`、`notes=null`、`completed=false`；用例明确指定的字段覆盖这些默认值。
- 前置任务创建成功后，以 Tasks API 返回的完整 task 作为 beforeSnapshot 的权威期望，不能由执行 Agent 手写 createdAt 或 ID。
- 从确认响应保存新任务 ID；清理时按 ID 删除，不按标题模糊删除。
- 即使测试失败也执行 best-effort cleanup，并在报告中列出未清理 ID。
- 删除会话不会替代删除真实任务；两者必须分别清理。
- 并发用例必须等待所有请求结束后再清理。
- 若无法保证独立数据库或可靠清理，本轮标记 `BLOCKED`，不得在污染环境中继续删除类用例。

## 11. 真实模型波动处理

所有用例先执行一次。首次失败后：

1. 保留首次请求、响应和最终状态，不覆盖证据；
2. 除幂等用例外，使用新会话和新 `turnId` 再执行 2 次；
3. 3 次都失败：记 `FAIL`，并标注“稳定复现”；
4. 3 次中有成功也有失败：记 `FLAKY`，仍属于缺陷；
5. 只有首次通过才能记 `PASS`；
6. API-001/API-002 等幂等用例必须按步骤复用 ID，不得用新 ID 规避失败。

重跑成功不能删除首次失败，也不能把 `FLAKY` 计入通过率。

## 12. 严重等级

| 等级 | 定义 | 典型示例 |
| --- | --- | --- |
| S0 阻断 | 数据安全、越权或不可接受的核心状态错误 | 未确认直接写入；删错任务；跨会话误删；重复确认重复创建；声称已真实订票；泄漏 Key/token。 |
| S1 严重 | 任务核心语义或目标错误 | 日期、分钟、上午/下午、备注实体错误；修改错目标；查询漏掉明确匹配；多个任务字段串项。 |
| S2 一般 | 工作流或次要结构字段错误 | 明确分类/优先级错误；该澄清时猜测；批次拆分、状态或稳定错误码不符。 |
| S3 轻微 | 不影响结构化结果的表达问题 | 回复冗长、不自然、标点不统一，但卡片及最终数据完全正确。 |

同一用例出现多个问题时，记录所有问题，并以最高严重等级决定用例结果。

## 13. 单条结果记录模板

```markdown
### <CASE-ID> <PASS|FAIL|FLAKY|BLOCKED|NOT RUN>

- runId:
- attempt: 1/3
- requestSentAt:
- timezone: Asia/Shanghai
- chatModel:
- conversationId:
- turnId:
- batchIds:
- proposalIds:
- preconditionTaskIds:
- HTTP status:
- expected summary:
- actual summary:
- pre-confirm bootstrap diff:
- confirm/reject request summary:
- post-confirm bootstrap diff:
- conversation detail summary:
- severity:
- defectId:
- cleanup status:
- evidence files:
```

报告中任务正文可以保留本方案的虚构测试数据，但 token、Key、本机数据库路径和任何真实个人数据必须脱敏。

## 14. 汇总报告模板

```markdown
# Assistant API Black-box Test Report

## Environment

| Field | Value |
| --- | --- |
| runId | |
| gitCommit | |
| backendVersion | |
| chatModel | |
| arkBaseUrl | |
| timezone | Asia/Shanghai |
| runStartedAt | |
| runFinishedAt | |

## Summary

| Suite | Total | Pass | Fail | Flaky | Blocked | Not Run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke | 20 | | | | | |
| Full | 96 | | | | | |

## Severity

| Severity | Count | Case IDs |
| --- | ---: | --- |
| S0 | | |
| S1 | | |
| S2 | | |
| S3 | | |

## Failed and flaky cases

| Case | Result | Severity | Short reason | Defect ID |
| --- | --- | --- | --- | --- |

## Residual data

| Resource type | ID | Cleanup error |
| --- | --- | --- |
```

## 15. 验收门槛

### 15.1 Smoke

- 20 条必须全部首次通过；
- `FAIL`、`FLAKY`、`BLOCKED` 或 `NOT RUN` 任一非零，Smoke 不通过；
- 任意 S0/S1，整体构建不可进入下一验证阶段。

### 15.2 Full

- S0 必须为 0；
- 日期、时间、备注和目标定位类 S1 必须为 0；
- 基础 CRUD、查询无副作用、确认流和 API 状态机必须 100% 首次通过；
- 陌生表达类首次通过率至少 95%；`FLAKY` 不计作通过；
- 未达到 95% 的失败必须建立缺陷，不能以“模型有随机性”为理由豁免；
- 所有 `BLOCKED` 和 `NOT RUN` 必须说明环境原因及补测计划，不能计入通过。

### 15.3 完成定义

只有同时满足以下条件，测试轮次才能标记完成：

- 96 条均有明确状态；
- 所有失败保留了首轮证据和必要复跑证据；
- 所有写操作都完成了确认前和确认后的任务快照比较；
- 测试数据已清理，或残留 ID 已完整列出；
- 报告没有凭据、真实个人数据或内部敏感路径；
- 汇总数字与逐条结果一致。

## 16. 执行 Agent 最终检查清单

- [ ] 使用的是真实方舟模型，而不是 mock。
- [ ] 记录了每次请求的本地时间和 `Asia/Shanghai`。
- [ ] 每个非幂等发送使用唯一 `turnId`。
- [ ] 所有写操作确认前都回读并证明任务未变化。
- [ ] create/update 确认提交了完整六字段 payload。
- [ ] delete 确认提交 `payload=null`。
- [ ] 查询前后任务快照完全一致。
- [ ] 日期、分钟、上午/下午和跨日分别断言，没有只看标题。
- [ ] 备注中的数字、地点、人名和清单逐项核对。
- [ ] 首次失败没有被重跑结果覆盖。
- [ ] 报告区分 `PASS/FAIL/FLAKY/BLOCKED/NOT RUN`。
- [ ] 清理了任务和会话，或记录了残留资源 ID。
- [ ] 报告中没有 token、API Key 或真实个人数据。
