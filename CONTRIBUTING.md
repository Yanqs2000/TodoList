# 贡献指南

感谢你的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境

要求：Node.js、npm、Python 3.12、[uv](https://docs.astral.sh/uv/)、Rust 工具链、macOS arm64。

```bash
# Python 后端
uv sync --directory backend --frozen
uv run --directory backend pytest

# 前端
npm --prefix frontend install
npm --prefix frontend test

# 桌面端开发
npm --prefix desktop install
bash desktop/scripts/build-sidecar.sh
npm --prefix desktop run dev
```

## 提交规范

- 遵循仓库根目录 `AGENTS.md` 和 `CLAUDE.md` 中的编码约定
- 一个 commit 只做一件事
- commit message 使用中文描述，格式：`类型: 简述`
  - `fix:` 修复 bug
  - `feat:` 新功能
  - `refactor:` 重构
  - `test:` 测试
  - `docs:` 文档
  - `release:` 发布版本

## 分支策略

- `main` — 稳定版本
- `dev-*` — 功能开发分支
- PR 合并到 `main` 前需要通过全量测试

## Pull Request 检查清单

- [ ] 后端 `pytest` 全量通过
- [ ] 前端 `npm test` 全量通过
- [ ] `ruff check` 无新增错误
- [ ] TypeScript `tsc -b` 无新增错误
- [ ] 新增代码有对应的测试
- [ ] 未包含 API Key、token、个人数据
- [ ] 文档已更新（如适用）
