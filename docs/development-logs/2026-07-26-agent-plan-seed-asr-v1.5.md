# Agent Plan Seed ASR 修复与 v1.5 打包

日期：2026-07-26

分支：`worktree-voice-input-ui`

版本：`1.5.0`

## 问题与根因

应用在 Agent Plan 配置下把 WAV 作为 OpenAI 兼容的 `input_audio` 发送到：

```text
https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions
```

真实服务返回：

```text
400 InvalidParameter: audio input is not supported by this model
```

该错误只表示当前请求协议不支持音频，不能推导为 Agent Plan 或豆包不支持语音。Agent Plan
控制台提供独立的语音识别资源：

```text
模型：doubao-seed-asr-2.0
Resource-Id：volc.seedasr.sauc.duration
WebSocket：wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream
```

参考：

- https://docs.volcengine.com/docs/82379/2516286?lang=zh
- https://www.volcengine.com/docs/6561/1354869?lang=zh

因此根因是后端调用了错误的接口和协议，不是 WAV 上传失败，也不是 Agent Plan 缺少语音能力。

## 修复

- 新增 Seed ASR WebSocket 二进制协议客户端。
- Agent Plan `/api/plan/v3` 配置走 Seed ASR；普通方舟 `/api/v3` 继续保留原
  `chat.completions + input_audio` 行为。
- 请求使用 Agent Plan Key 和 `volc.seedasr.sauc.duration` 资源标识。
- WAV 在发送前读取真实容器参数；双声道、24 位、44.1 kHz PCM 自动转换为单声道、16 位、
  16 kHz PCM。
- WAV 使用 64 KiB 分片；MP3 使用 3200 B 分片，避免压缩音频单帧过长造成尾部遗漏。
- 无语音结果返回 `422 AUDIO_NOT_RECOGNIZED`。
- `ASSISTANT_UNAVAILABLE` 保持为助手功能错误，不再把整个 App 误判为本地后端不可用。
- PyInstaller 运行时加入 `websockets>=15.0.1`。

## TDD 证据

新增协议测试后，未修复的 1.4 代码按预期失败：

```text
Expected: 完整文本
Actual:   错误接口
```

这证明测试确实捕获了旧代码仍走 `chat.completions` 的问题。修复后，测试确认：

- Agent Plan 不再调用 `chat.completions`。
- 请求地址、API Key 请求头和 Resource-Id 正确。
- 44.1 kHz、双声道、24 位 WAV 被规范化为 16 kHz、单声道、16 位。
- 无语音结果不再返回空字符串 200。
- 助手模型 503 不再转换成全局 `InfrastructureError`。

## 真实 Agent Plan 验证

使用应用当前保存的 Agent Plan 配置和用户提供的：

```text
/Users/yanqs/Music/LXMusic/虚构 - 周深.wav
```

原文件参数：

```text
大小：10,398,936 B
格式：PCM WAV
采样率：44,100 Hz
声道：2
位深：24 bit
SHA-256：b73ce610edb4614eed96c5e00a2c9c4594766fd1a088c93d71115eccbe561b75
```

三层真实验证结果：

| 层级 | 上传 | 转写 | 转写后健康检查 |
|---|---:|---:|---:|
| 1.5 源码隔离后端 | 201 | 200 | 200 |
| 1.5 `.app` 包内 sidecar | 201 | 200 | 200 |
| `/Applications/Todo List.app` 已安装 sidecar | 201 | 200 | 200 |

已安装 App 返回：

```text
开的理由。我在你逃走之前先逃走。如果没有这些，如果，你才会爱我。
```

目标歌词除开头弱起音“分”外连续匹配。Seed ASR 多次稳定遗漏该首字；增加前置静音和声道对照
也未恢复，因此没有使用硬编码歌词伪造完全匹配。

生产上传目录中的最新文件：

```text
assistant_uploads/bbe9b98235be44a291e3a8bc61221bc2.wav
SHA-256：b73ce610edb4614eed96c5e00a2c9c4594766fd1a088c93d71115eccbe561b75
```

与原文件哈希完全一致，说明上传和持久化没有损坏音频。

## 自动化与打包验证

| 检查 | 结果 |
|---|---|
| 后端完整测试 | `327 passed, 3 skipped` |
| Seed ASR 目标 Ruff | 通过 |
| 前端 API 目标测试 | `9 passed` |
| 前端生产构建 | 通过 |
| 前端全量测试 | `181 passed, 1 timeout`；超时用例独立重放 `7 passed` |
| 包内 sidecar 生命周期测试 | `3 passed` |
| `.app` 严格 codesign | 通过 |
| DMG codesign | 通过 |
| `hdiutil verify` | 通过 |
| 安装后版本 | `1.5.0` |

前端全量唯一失败是既有 UI 测试在并行负载下超过 5 秒；该文件独立重放 7/7 通过，不涉及
语音或 API 错误分类代码。

## 最终产物

```text
App:
desktop/src-tauri/target/release/bundle/macos/Todo List.app

DMG:
desktop/src-tauri/target/release/bundle/dmg/Todo List_1.5.0_aarch64.dmg
```

哈希：

```text
包内 sidecar:
90d78893b7f773940926f08d78c594c72222a3c6c5a9b6ba181864acf1770648

DMG:
65b092b5c8ef62f4ce61458a9f120be51f8749869f426584b5bd7c53e062ad08
```

已安装至：

```text
/Applications/Todo List.app
```

安装前的 1.4 App 已保留为：

```text
/Applications/Todo List.app.backup-20260726-224556
```
