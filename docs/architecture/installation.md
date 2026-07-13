# macOS 安装与构建

当前打包目标为 macOS 11+、Apple Silicon（arm64）。桌面包已经包含 Python sidecar，最终用户不需要安装 Python、uv 或 Node.js。

## 安装发布包

1. 从 Releases 下载 `Todo List_<version>_aarch64.dmg`。
2. 打开 DMG，将 `Todo List.app` 拖入 Applications。
3. 当前项目使用 ad-hoc 签名而非 Apple Developer ID 公证。首次启动可右键选择“打开”；若 Gatekeeper 仍阻止，可执行：

```bash
xattr -dr com.apple.quarantine /Applications/Todo\ List.app
```

## 数据位置与卸载

应用程序可直接移到废纸篓。SQLite 数据独立保存在：

```text
~/Library/Application Support/com.todo-app.desktop/todo.sqlite3
```

完全退出应用后，可备份这个文件。若要彻底清除数据：

```bash
rm -rf "$HOME/Library/Application Support/com.todo-app.desktop"
```

此操作不可恢复。应用没有账号或云端副本。

## 开发构建

要求：macOS arm64、Node.js/npm、Rust、Python 3.12 和 uv。

```bash
uv sync --directory backend --frozen
npm --prefix frontend install
npm --prefix desktop install

# 生成 PyInstaller sidecar
bash desktop/scripts/build-sidecar.sh

# 开发模式
npm --prefix desktop run dev

# 构建 .app 和 .dmg（构建脚本会重新生成 sidecar）
npm --prefix desktop run build
```

产物：

```text
desktop/src-tauri/target/release/bundle/macos/Todo List.app
desktop/src-tauri/target/release/bundle/dmg/
```

## ad-hoc 签名

```bash
npm --prefix desktop run sign:macos
```

`desktop/scripts/sign-macos-bundle.sh` 会先签名 `.app/Contents/MacOS/todo-backend`，再签名包含它的 `.app`，最后签名 DMG。验证命令：

```bash
codesign --verify --deep --strict --verbose=2 \
  "desktop/src-tauri/target/release/bundle/macos/Todo List.app"
```

ad-hoc 签名证明 bundle 结构完整，但不等同于 Developer ID 签名和 Apple 公证。
