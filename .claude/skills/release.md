---
name: release
description: 发布新版本到 GitHub - 上传代码、监测 CI、创建 Release
parameters:
  version:
    type: string
    description: 版本号 (如 0.1.0 或 v0.1.0)
    required: true
  notes:
    type: string
    description: 发布说明
    required: true
---

# Release Skill

执行完整的发布流程：

1. 验证版本号格式
2. 检查 git 工作区状态
3. 更新项目版本号
4. 创建 git commit 和 tag
5. 推送到 GitHub
6. 监测 CI 直到全部通过
7. 创建 GitHub Release

## 使用示例

```
/release 0.2.0 "新增高级过滤功能和性能优化"
```

## 步骤详解

### 1. 版本验证

检查版本号格式是否符合语义化版本规范。

### 2. Git 状态检查

确保工作区干净，没有未提交的更改。

### 3. 更新版本号

更新 `pyproject.toml` 中的 `project.version` 字段。

### 4. Git 提交

创建版本提交并打上 git tag。

### 5. 推送

推送代码和 tag 到 GitHub。

### 6. CI 监测

持续轮询 GitHub Actions 状态，直到所有 workflow 成功或失败。

### 7. 创建 Release

使用 GitHub CLI 创建 Release 并附加构建产物。
