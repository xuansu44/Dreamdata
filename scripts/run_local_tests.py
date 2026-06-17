#!/usr/bin/env python3
"""
Local test runner for dreamdata project.
Runs all test layers, checks docs, detects tech debt.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)


@dataclass
class CheckResult:
    name: str
    success: bool
    output: str = ""
    duration: float = 0.0


def run_cmd(cmd: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def run_uv_cmd(args: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
    """Run a command through uv."""
    return run_cmd(["uv", "run", *args], capture_output=capture_output)


def check_ruff() -> CheckResult:
    """Run ruff lint and format checks."""
    print("Running ruff check...")
    code1, _, stderr1 = run_uv_cmd(["ruff", "check", "."])
    lint_ok = code1 == 0

    print("Running ruff format check...")
    code2, _, stderr2 = run_uv_cmd(["ruff", "format", "--check", "."])
    format_ok = code2 == 0

    output = []
    if not lint_ok:
        output.append("Ruff lint errors:\n" + stderr1)
    if not format_ok:
        output.append("Ruff format errors:\n" + stderr2)

    return CheckResult(
        name="ruff (lint + format)",
        success=lint_ok and format_ok,
        output="\n".join(output),
    )


def check_mypy() -> CheckResult:
    """Run mypy type checks."""
    print("Running mypy (strict on sdk)...")
    code1, _, stderr1 = run_uv_cmd(["mypy", "--strict", "src/dreamdata/sdk.py"])
    sdk_ok = code1 == 0

    print("Running mypy (all code)...")
    code2, _, stderr2 = run_uv_cmd(
        ["mypy", "--check-untyped-defs", "--disallow-untyped-defs", "src/dreamdata"]
    )
    all_ok = code2 == 0

    output = []
    if not sdk_ok:
        output.append("Mypy SDK errors:\n" + stderr1)
    if not all_ok:
        output.append("Mypy all-code errors:\n" + stderr2)

    return CheckResult(
        name="mypy",
        success=sdk_ok and all_ok,
        output="\n".join(output),
    )


def run_pytest(
    test_dirs: List[str], name: str, with_coverage: bool = False
) -> CheckResult:
    """Run pytest on specific directories."""
    print(f"Running pytest: {name}...")
    cmd = ["pytest", *test_dirs, "-q", "--tb=short"]
    if with_coverage:
        cmd.extend(["--cov=src/dreamdata", "--cov-report=term-missing"])

    code, stdout, stderr = run_uv_cmd(cmd, capture_output=True)
    return CheckResult(
        name=name,
        success=code == 0,
        output=stdout + "\n" + stderr,
    )


def check_docs() -> CheckResult:
    """Check bilingual documentation builds."""
    print("Building English docs...")
    code1, _, stderr1 = run_uv_cmd(
        ["sphinx-build", "-W", "docs/source", "docs/build/en"]
    )
    en_ok = code1 == 0

    print("Building Chinese docs...")
    code2, _, stderr2 = run_uv_cmd(
        ["sphinx-build", "-W", "docs/source/zh_CN", "docs/build/zh_CN"]
    )
    zh_ok = code2 == 0

    # Check inter-language links
    print("Checking inter-language links...")
    en_has_links = False
    zh_has_links = False
    try:
        for md_file in Path("docs/source").rglob("*.md"):
            if "English / 简体中文" in md_file.read_text():
                en_has_links = True
                break

        for md_file in Path("docs/source/zh_CN").rglob("*.md"):
            content = md_file.read_text()
            if "中文 / English" in content or "English / 简体中文" in content:
                zh_has_links = True
                break
    except Exception:
        pass

    output = []
    if not en_ok:
        output.append("English docs build errors:\n" + stderr1)
    if not zh_ok:
        output.append("Chinese docs build errors:\n" + stderr2)
    if not en_has_links and en_ok:
        output.append("Warning: No English → Chinese links found in docs")
    if not zh_has_links and zh_ok:
        output.append("Warning: No Chinese → English links found in docs")

    return CheckResult(
        name="bilingual docs",
        success=en_ok and zh_ok,
        output="\n".join(output),
    )


def check_tech_debt() -> Dict[str, List[str]]:
    """Detect technical debt."""
    debt = {
        "TODO/FIXME": [],
        "unused_imports": [],
        "complex_functions": [],
        "low_coverage": [],
    }

    # Find TODO/FIXME comments
    for py_file in Path("src/dreamdata").rglob("*.py"):
        try:
            lines = py_file.read_text().split("\n")
            for i, line in enumerate(lines, 1):
                if any(tag in line for tag in ["TODO", "FIXME", "XXX", "HACK"]):
                    debt["TODO/FIXME"].append(f"{py_file}:{i}: {line.strip()}")
        except Exception:
            pass

    # Find unused imports via ruff
    code, stdout, _ = run_uv_cmd(
        ["ruff", "check", "--select=F401,F841", "src/dreamdata/"]
    )
    if stdout.strip():
        debt["unused_imports"].extend(stdout.strip().split("\n"))

    # Check for complex functions
    def check_complexity(filepath: Path) -> List[Tuple[str, int, str]]:
        import ast

        try:
            with open(filepath) as f:
                tree = ast.parse(f.read())
        except Exception:
            return []

        complex_funcs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Count statements
                stmt_count = sum(
                    1 for _ in ast.walk(node) if isinstance(_, (ast.stmt, ast.expr))
                )
                if stmt_count > 50:
                    complex_funcs.append((node.name, stmt_count, str(filepath)))
        return complex_funcs

    all_complex = []
    for py_file in Path("src/dreamdata").rglob("*.py"):
        all_complex.extend(check_complexity(py_file))

    for name, count, path in sorted(all_complex, key=lambda x: -x[1]):
        debt["complex_functions"].append(f"{name:30} {count:4} in {path}")

    return debt


def main():
    parser = argparse.ArgumentParser(
        description="Local test runner for dreamdata"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick check (L1-L3 + L8 + coverage)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full test suite (all layers)",
    )
    parser.add_argument(
        "--docs-only",
        action="store_true",
        help="Only check documentation",
    )
    parser.add_argument(
        "--scale",
        action="store_true",
        help="Include scale tests (L6, slow)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("dreamdata Local Test Runner")
    print("=" * 60)
    print()

    results: List[CheckResult] = []

    # Static checks
    if not args.docs_only:
        results.append(check_ruff())
        results.append(check_mypy())

        # Test layers
        if args.quick:
            # Quick check: L1 + L2 + L3 + L8 + coverage
            results.append(
                run_pytest(
                    ["tests/unit/", "tests/component/", "tests/sdk/", "tests/e2e/"],
                    "quick (L1-L3 + L8)",
                    with_coverage=True,
                )
            )
        elif args.full:
            # Full suite
            results.append(run_pytest(["tests/unit/"], "L1 Unit"))
            results.append(run_pytest(["tests/component/"], "L2 Component"))
            results.append(run_pytest(["tests/sdk/"], "L3 SDK"))
            results.append(run_pytest(["tests/property/"], "L4 Property"))
            results.append(run_pytest(["tests/fuzz/"], "L5 Fuzz"))
            results.append(run_pytest(["tests/e2e/"], "L8 E2E"))
            if args.scale:
                results.append(run_pytest(["tests/scale/"], "L6 Scale"))
            # Coverage
            results.append(
                run_pytest(
                    ["tests/"],
                    "coverage",
                    with_coverage=True,
                )
            )
        else:
            # Default: most tests without property/fuzz (faster)
            results.append(run_pytest(["tests/unit/"], "L1 Unit"))
            results.append(run_pytest(["tests/component/"], "L2 Component"))
            results.append(run_pytest(["tests/sdk/"], "L3 SDK"))
            results.append(run_pytest(["tests/e2e/"], "L8 E2E"))

    # Docs check
    results.append(check_docs())

    # Tech debt check
    if not args.docs_only:
        print("\nChecking for technical debt...")
        tech_debt = check_tech_debt()

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()

    all_ok = True
    for result in results:
        status = "✅ PASS" if result.success else "❌ FAIL"
        print(f"{status}: {result.name}")
        if not result.success and result.output:
            # Show last 5 lines of output
            lines = result.output.strip().split("\n")[-5:]
            for line in lines:
                print(f"  {line}")
        all_ok = all_ok and result.success

    # Tech debt summary
    if not args.docs_only:
        print()
        print("-" * 60)
        print("TECHNICAL DEBT")
        print("-" * 60)
        for category, items in tech_debt.items():
            if items:
                print(f"\n{category} ({len(items)}):")
                for item in items[:10]:  # Show up to 10
                    print(f"  {item}")
                if len(items) > 10:
                    print(f"  ... and {len(items) - 10} more")

    print()
    print("=" * 60)
    if all_ok:
        print("✅ ALL CHECKS PASSED!")
    else:
        print("❌ SOME CHECKS FAILED — SEE ABOVE FOR DETAILS")
        sys.exit(1)


if __name__ == "__main__":
    main()
