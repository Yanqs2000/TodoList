# TodoList 安装指南（macOS）

> 适用版本：v0.1.5 及以上  
> 适用系统：macOS 11.0 (Big Sur) 及以上  
> 适用架构：Apple Silicon（M1/M2/M3/M4 系列）

## 下载

从 GitHub Releases 下载最新版 `.dmg` 文件：

https://github.com/Yanqs2000/TodoList/releases

文件名格式：`Todo List_X.X.X_aarch64.dmg`

> ⚠️ **架构说明**：当前仅提供 `aarch64`（Apple Silicon）版本。  
> 如果你使用 Intel Mac（i5/i7/i9 等），此版本无法运行。后续会提供 Universal Binary。

---

## 安装步骤

### 1. 挂载 DMG

双击下载的 `.dmg` 文件，会挂载为一个磁盘镜像。

### 2. 拖动安装

将 `Todo List.app` 拖到右侧的 `Applications` 文件夹。

### 3. 首次启动（关键）

由于本项目是开源软件，没有购买 Apple 开发者证书（$99/年），macOS Gatekeeper 会拦截未公证应用。**首次打开有三种方式**，任选其一：

#### 方式 A：右键打开（推荐，最简单）

1. 在 `Applications` 文件夹中找到 `Todo List`
2. **按住 Control 键点击图标**（或右键）
3. 选择「打开」
4. 弹出警告对话框，点击「打开」
5. 以后双击即可正常启动

#### 方式 B：终端命令（推荐给有终端基础的用户）

打开「终端」App，粘贴并回车：

```bash
xattr -dr com.apple.quarantine /Applications/Todo\ List.app
```

这会移除 macOS 给下载文件加的隔离属性。运行后双击 App 即可启动。

#### 方式 C：系统偏好设置允许

1. 双击 `Todo List`，看到"无法打开"或"已损坏"提示
2. 打开「系统设置」→「隐私与安全性」
3. 滚动到底部，会看到"已阻止使用 Todo List"
4. 点击「仍要打开」
5. 输入密码确认

---

## 常见问题

### Q1: 提示"应用程序已损坏，无法打开"

**原因**：macOS Gatekeeper 给下载的文件加了 `com.apple.quarantine` 隔离属性，且本应用未做 Apple 公证。

**解决**：用上面的「方式 B」终端命令移除隔离属性：

```bash
xattr -dr com.apple.quarantine /Applications/Todo\ List.app
```

如果 App 不在 `Applications`，把路径换成实际位置即可。

### Q2: 提示"无法验证开发者"

**原因**：同 Q1。本应用使用 ad-hoc 签名（无 Apple Developer ID）。

**解决**：用「方式 A」右键打开，或「方式 B」终端命令。

### Q3: 在 Intel Mac 上无法打开

**原因**：当前版本只编译了 Apple Silicon（arm64）架构。

**解决**：
- 短期：使用 `node` + `npm run dev` 跑 Web 版本
- 长期：等待 Universal Binary 版本

### Q4: DMG 文件本身打不开

**原因**：可能是下载不完整。

**解决**：
1. 检查 DMG 文件大小，应与 GitHub Releases 页面显示一致
2. 在终端校验 SHA256：
   ```bash
   shasum -a 256 "Todo List_0.1.5_aarch64.dmg"
   ```
   与 Release 说明里的校验和对比
3. 不一致则重新下载

### Q5: 安装后启动闪退

**排查步骤**：

1. 在终端启动看错误日志：
   ```bash
   /Applications/Todo\ List.app/Contents/MacOS/app
   ```
2. 检查 macOS 版本是否 ≥ 11.0
3. 如果是 Apple Silicon 但仍闪退，可能是签名被破坏，重新下载安装

---

## 卸载

直接将 `Todo List.app` 拖到废纸篓即可。

应用数据存储在 `~/Library/Application Support/com.todo-app.desktop/`，如需彻底清理可一并删除：

```bash
rm -rf ~/Library/Application\ Support/com.todo-app.desktop/
```

localStorage 数据在应用的 WebView 内部，删除 App 即自动清除。

---

## 开发者信息

### 为什么不签名公证？

Apple Developer Program 每年 $99，对个人开源项目是不小的成本。本应用采用 ad-hoc 签名（`codesign --sign -`），可以让 macOS 识别应用结构完整性，但无法通过 Gatekeeper 自动验证。用户需手动绕过一次（见上文三种方式）。

### 如何构建带签名的 DMG？

```bash
# 1. 构建 .app 和 .dmg
npm run tauri build

# 2. 对产物做 ad-hoc 签名（自动调用 scripts/sign-macos-bundle.sh）
npm run sign:macos

# 或一步到位
npm run tauri:build
```

签名脚本会对 `.app` 做 `--deep --options runtime` 深度签名 + hardened runtime，对 `.dmg` 做外层签名。详见 `scripts/sign-macos-bundle.sh`。

### 后续规划

- Universal Binary（同时支持 arm64 + x86_64）
- 可选的 Apple Developer ID 签名 + 公证（需用户提供证书）

详见 [development-logs/v0.1.4-code-review-bugfix.md](./development-logs/v0.1.4-code-review-bugfix.md) 末尾的后续建议。
