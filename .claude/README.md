# Claude Code 项目配置

本目录包含 dreamdata 项目的 Claude Code agent 和 skill 配置。

## Agents

### Release Agent

负责自动化完整的发布流程：

- 版本验证和更新
- Git commit, tag 和 push
- CI 状态监测
- GitHub Release 创建

**文件位置:**
- `.claude/agents/release-agent.md` - Agent 定义
- `.claude/agents/RELEASE-AGENT-GUIDE.md` - 使用指南
- `.claude/skills/release.md` - Skill 定义
- `scripts/release.py` - 发布脚本

**使用方式:**

```bash
# 直接运行脚本
./scripts/release.py 0.2.0 "发布说明"

# 或在 Claude Code 中使用 skill
/release 0.2.0 "发布说明"
```

## 目录结构

```
.claude/
├── agents/
│   ├── release-agent.md          # Release Agent 定义
│   └── RELEASE-AGENT-GUIDE.md    # 使用指南
├── skills/
│   └── release.md                # Release Skill 定义
└── README.md                     # 本文件

scripts/
└── release.py                    # 发布脚本
```

## 前置要求

- GitHub CLI (`gh`) 已安装并登录
- Git 已配置正确的 remote
- GitHub Actions 已启用
- uv 包管理器

## 更多信息

详见 `.claude/agents/RELEASE-AGENT-GUIDE.md`。
