# Release Agent 使用指南

## 概述

Release Agent 是一个项目级别的 Claude Code agent，负责自动化完整的发布流程：

1. **版本管理** - 验证并更新版本号
2. **Git 操作** - 创建 commit、tag 并推送
3. **CI 监测** - 持续监测 GitHub Actions 直到全部通过
4. **Release 发布** - 创建 GitHub Release 并附加构建产物

## 文件结构

```
.claude/
├── agents/
│   ├── release-agent.md          # Agent 定义
│   └── RELEASE-AGENT-GUIDE.md    # 本文件
└── skills/
    └── release.md                # Release Skill 定义

scripts/
└── release.py                    # 发布脚本
```

## 前置要求

1. **GitHub CLI** - 已安装并登录 (`gh auth login`)
2. **Git** - 已配置正确的 remote
3. **GitHub Actions** - 已在项目中启用
4. **uv** - 项目使用 uv 进行包管理

## 使用方式

### 方式一：直接运行脚本

```bash
# 完整发布流程
./scripts/release.py 0.2.0 "新增高级过滤功能"

# 跳过 CI 监测
./scripts/release.py 0.2.0 "热修复" --skip-ci

# 跳过构建
./scripts/release.py 0.2.0 "仅打标签" --skip-build
```

### 方式二：通过 Claude Code Skill

在 Claude Code 中调用：

```
/release 0.2.0 "新增高级过滤功能和性能优化"
```

## 发布流程详解

### 1. 版本验证

- 验证版本号格式 (MAJOR.MINOR.PATCH)
- 自动移除 `v` 前缀 (如果有)

### 2. Git 状态检查

确保工作区干净，没有未提交的更改。

### 3. 更新版本号

自动更新 `pyproject.toml` 中的 `project.version` 字段。

### 4. Git 提交和打标签

- 创建提交: `git commit -m "Release v0.1.0"`
- 创建标签: `git tag -a v0.1.0 -m "..."`

### 5. 推送到 GitHub

- 推送代码: `git push`
- 推送标签: `git push origin v0.1.0`

### 6. CI 监测

- 每 30 秒检查一次 CI 状态
- 最多等待 30 分钟
- 显示所有 workflow 的实时状态
- 如果 CI 失败，提供 `--skip-ci` 选项

### 7. 构建产物

运行 `uv build` 生成:
- `dist/dreamdata-<version>-py3-none-any.whl`
- `dist/dreamdata-<version>.tar.gz`

### 8. 创建 GitHub Release

使用 GitHub CLI 创建 Release 并附加所有构建产物。

## CI 状态输出示例

```
============================================================
开始监测 CI 状态...
============================================================

[09:45:12] 当前 CI 状态:
  ✓ ci-main @ a1b2c3d: completed (success)
  ✓ ci-pr @ a1b2c3d: completed (success)
  ⚡ ci-nightly @ a1b2c3d: in_progress (pending)

[09:45:42] 当前 CI 状态:
  ✓ ci-main @ a1b2c3d: completed (success)
  ✓ ci-pr @ a1b2c3d: completed (success)
  ✓ ci-nightly @ a1b2c3d: completed (success)

============================================================
✓ 所有 CI 测试通过！
```

## 错误处理

### Git 工作区不干净

```
错误: 工作区不干净，请先提交或暂存更改:
 M pyproject.toml
?? temp.txt
```

解决: 提交或 stash 更改。

### CI 失败

```
✗ 部分 CI 测试失败
发布流程中止: CI 未通过
如需强制发布，请使用 --skip-ci 选项
```

解决: 修复 CI 或使用 `--skip-ci`。

### GitHub CLI 未登录

```
命令失败: gh release create ...
错误输出: authentication failed
```

解决: 运行 `gh auth login`。

## 版本回滚

如果需要撤销发布:

```bash
# 删除本地 tag
git tag -d v0.1.0

# 删除远程 tag
git push origin --delete v0.1.0

# 撤销 commit (如果还没 push)
git reset --soft HEAD~1
```

## 最佳实践

1. **先测试再发布** - 在发布前确保所有测试本地通过
2. **写好发布说明** - 清晰列出新功能、修复和变更
3. **遵循语义化版本** - MAJOR (不兼容变更), MINOR (新功能), PATCH (修复)
4. **不要跳过 CI** - 除非紧急修复，否则应该等待 CI 通过
5. **检查 Release 页面** - 发布后在 GitHub 验证 Release 是否正确

## 相关文件

- `pyproject.toml` - 项目配置和版本号
- `.github/workflows/` - CI 工作流定义
- `.mex/ROUTER.md` - 项目状态
