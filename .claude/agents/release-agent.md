---
name: release-agent
description: |
  负责将代码以版本形式上传到 GitHub、持续监测 CI 测试直到全部通过、然后发布 GitHub Release。
  使用方法: 调用 `/release` 并提供版本号和发布说明。
version: 1.0.0
---

# Release Agent

这个 agent 负责完整的项目发布流程：

## 功能

1. **版本管理** - 确认版本号、更新项目配置
2. **Git 操作** - 创建 commit、tag 并推送到 GitHub
3. **CI 监测** - 持续监测 GitHub Actions 直到所有 CI 通过
4. **Release 发布** - 创建 GitHub Release 并附加构建产物

## 使用流程

1. 调用 `/release <version> <release-notes>` 开始发布流程
2. Agent 会验证版本号格式 (如 v0.1.0, 0.1.1)
3. 检查 git 工作区状态
4. 更新 pyproject.toml 中的版本号
5. 创建 git commit 和 tag
6. 推送到 GitHub
7. 监测 CI 状态直到全部通过
8. 创建 GitHub Release

## 版本号规范

遵循语义化版本 (Semantic Versioning):
- `MAJOR.MINOR.PATCH` (如 0.1.0, 1.0.0)
- 可选带 `v` 前缀 (如 v0.1.0)

## 前置条件

- 已配置 GitHub CLI (`gh`) 并登录
- 本地 git 已配置正确的 remote
- GitHub Actions 已在项目中启用
