#!/usr/bin/env python3
"""
Dreamdata Release Script

负责完整的发布流程：
- 版本验证
- Git 操作
- CI 监测
- GitHub Release 创建
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_cmd(cmd: list[str], cwd: Path | None = None, check: bool = True) -> str:
    """运行命令并返回输出"""
    result = subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    if check and result.returncode != 0:
        print(f"命令失败: {' '.join(cmd)}")
        print(f"错误输出: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def validate_version(version: str) -> str:
    """验证并标准化版本号"""
    # 移除 v 前缀
    if version.startswith('v'):
        version = version[1:]

    # 验证语义化版本格式
    pattern = r'^\d+\.\d+\.\d+$'
    if not re.match(pattern, version):
        print(f"错误: 版本号格式不正确 '{version}'，应为 MAJOR.MINOR.PATCH (如 0.1.0)")
        sys.exit(1)

    return version


def check_git_status() -> None:
    """检查 git 工作区状态"""
    status = run_cmd(["git", "status", "--porcelain"])
    if status:
        print("错误: 工作区不干净，请先提交或暂存更改:")
        print(status)
        sys.exit(1)


def update_version_in_pyproject(version: str) -> None:
    """更新 pyproject.toml 中的版本号"""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    content = pyproject_path.read_text()

    # 更新版本号
    content = re.sub(
        r'version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        content
    )

    pyproject_path.write_text(content)
    print(f"已更新版本号到 {version}")


def git_commit_and_tag(version: str, notes: str) -> None:
    """创建 git commit 和 tag"""
    # 提交版本更新
    run_cmd(["git", "add", "pyproject.toml"])
    run_cmd(["git", "commit", "-m", f"Release v{version}"])

    # 创建 tag
    run_cmd(["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}\n\n{notes}"])

    print(f"已创建 commit 和 tag v{version}")


def git_push(version: str) -> None:
    """推送代码和 tag 到 GitHub"""
    run_cmd(["git", "push"])
    run_cmd(["git", "push", "origin", f"v{version}"])
    print("已推送到 GitHub")


def get_latest_workflow_run() -> tuple[str, str, str] | None:
    """获取最新的 workflow run 信息"""
    try:
        output = run_cmd(["gh", "run", "list", "--limit", "1", "--json", "status,conclusion,url"])
        import json
        data = json.loads(output)
        if data:
            return (data[0]["status"], data[0]["conclusion"], data[0]["url"])
    except Exception:
        pass
    return None


def monitor_ci() -> bool:
    """监测 CI 直到全部通过或失败"""
    print("开始监测 CI 状态...")
    print("=" * 60)

    max_wait = 30 * 60  # 最多等待 30 分钟
    poll_interval = 30  # 每 30 秒检查一次
    start_time = time.time()

    while time.time() - start_time < max_wait:
        # 检查所有最近的 runs
        output = run_cmd(["gh", "run", "list", "--limit", "5", "--json", "status,conclusion,headSha,name"])
        import json
        runs = json.loads(output)

        print(f"\n[{time.strftime('%H:%M:%S')}] 当前 CI 状态:")
        all_completed = True
        all_success = True

        for run in runs:
            status = run["status"]
            conclusion = run["conclusion"]
            name = run["name"]
            sha = run["headSha"][:7]

            status_icon = {
                "completed": "✓" if conclusion == "success" else "✗",
                "in_progress": "⚡",
                "queued": "⏳",
                "requested": "⏳",
            }.get(status, "?")

            print(f"  {status_icon} {name} @ {sha}: {status} ({conclusion or 'pending'})")

            if status != "completed":
                all_completed = False
            if conclusion != "success":
                all_success = False

        if all_completed:
            print("\n" + "=" * 60)
            if all_success:
                print("✓ 所有 CI 测试通过！")
                return True
            else:
                print("✗ 部分 CI 测试失败")
                return False

        time.sleep(poll_interval)

    print("\n" + "=" * 60)
    print("✗ 等待 CI 超时")
    return False


def build_artifacts() -> None:
    """构建发布产物"""
    print("构建发布产物...")
    run_cmd(["uv", "build"])
    print("构建完成")


def create_github_release(version: str, notes: str) -> None:
    """创建 GitHub Release"""
    # 检查 dist 目录
    dist_dir = PROJECT_ROOT / "dist"
    assets = []
    if dist_dir.exists():
        for f in dist_dir.iterdir():
            if f.is_file():
                assets.append(str(f))

    # 创建 release 命令
    cmd = [
        "gh", "release", "create", f"v{version}",
        "--title", f"v{version}",
        "--notes", notes,
    ]

    # 添加构建产物
    for asset in assets:
        cmd.append(asset)

    run_cmd(cmd)
    print(f"✓ GitHub Release v{version} 已创建")


def main():
    parser = argparse.ArgumentParser(description="Dreamdata 发布工具")
    parser.add_argument("version", help="版本号 (如 0.1.0 或 v0.1.0)")
    parser.add_argument("notes", help="发布说明")
    parser.add_argument("--skip-ci", action="store_true", help="跳过 CI 监测")
    parser.add_argument("--skip-build", action="store_true", help="跳过构建")

    args = parser.parse_args()

    print("=" * 60)
    print("Dreamdata Release Tool")
    print("=" * 60)

    # 1. 验证版本号
    version = validate_version(args.version)
    print(f"\n版本号: v{version}")
    print(f"发布说明: {args.notes}")
    print()

    # 2. 检查 git 状态
    check_git_status()

    # 3. 更新版本号
    update_version_in_pyproject(version)

    # 4. Git commit 和 tag
    git_commit_and_tag(version, args.notes)

    # 5. 推送到 GitHub
    git_push(version)

    # 6. 监测 CI
    if not args.skip_ci:
        print()
        ci_success = monitor_ci()
        if not ci_success:
            print("\n发布流程中止: CI 未通过")
            print("如需强制发布，请使用 --skip-ci 选项")
            sys.exit(1)

    # 7. 构建产物
    if not args.skip_build:
        print()
        build_artifacts()

    # 8. 创建 GitHub Release
    print()
    create_github_release(version, args.notes)

    print("\n" + "=" * 60)
    print(f"✓ 发布 v{version} 完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
