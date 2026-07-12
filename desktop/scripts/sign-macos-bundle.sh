#!/usr/bin/env bash
# Ad-hoc 签名 macOS .app 和 .dmg 产物。
#
# 为什么需要：Tauri 默认只对 .app 内部做 ad-hoc 签名，不会签名外层的 .dmg。
# 未签名的 .dmg 在 macOS Gatekeeper 下会显示"已损坏，无法打开"。
# 本脚本对 .app（深度签名所有辅助文件）和 .dmg 都做显式 ad-hoc 签名，
# 让结构完整，配合 INSTALL.md 中的绕过说明，普通用户即可安装。
#
# 用法：在 `npm run tauri build` 完成后运行
#   bash scripts/sign-macos-bundle.sh
#
# 退出码：0 成功；非 0 失败。

set -euo pipefail

APP_NAME="Todo List"
BUNDLE_DIR="src-tauri/target/release/bundle"
APP_PATH="${BUNDLE_DIR}/macos/${APP_NAME}.app"
DMG_DIR="${BUNDLE_DIR}/dmg"

if [ ! -d "${APP_PATH}" ]; then
  echo "❌ 找不到 .app: ${APP_PATH}" >&2
  echo "   请先运行 npm run tauri build" >&2
  exit 1
fi

echo "🔐 签名 .app (深度签名所有资源)..."
# --deep 已被 Apple 标记为过时但仍可用；对 Tauri 这种简单 bundle 足够。
# --options runtime 加 hardened runtime，是公证的前置要求（即使现在没公证也加上）。
codesign --force --deep --sign - \
  --options runtime \
  --timestamp=none \
  "${APP_PATH}"

echo "✅ .app 签名验证:"
codesign --verify --verbose=2 "${APP_PATH}" 2>&1 | sed 's/^/   /'

# 找到 DMG 文件（文件名带版本号和架构）
DMG_PATH=$(ls "${DMG_DIR}"/*.dmg 2>/dev/null | head -1 || true)
if [ -z "${DMG_PATH}" ]; then
  echo "⚠️  没找到 .dmg 文件，跳过 DMG 签名"
  exit 0
fi

echo "🔐 签名 .dmg: ${DMG_PATH##*/}"
codesign --force --sign - \
  --timestamp=none \
  "${DMG_PATH}"

echo "✅ .dmg 签名验证:"
codesign --verify --verbose=2 "${DMG_PATH}" 2>&1 | sed 's/^/   /'

echo ""
echo "🎉 签名完成"
echo "   .app: ${APP_PATH}"
echo "   .dmg: ${DMG_PATH}"
echo ""
echo "📋 分发前提示:"
echo "   1. 用户首次打开需右键 → 打开（或运行 xattr -dr 命令）"
echo "   2. 详见 docs/installation-guide.md"
