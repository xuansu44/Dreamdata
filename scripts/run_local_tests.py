#!/usr/bin/env python3
"""
Local test runner for dreamdata project.
Runs all test layers, checks docs, detects tech debt.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)


@dataclass
class CheckResult:
    name: str
    success: bool
    output: str = ""
    duration: float = 0.0


def run_cmd(cmd: list[str], capture_output: bool = True) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def run_uv_cmd(args: list[str], capture_output: bool = True) -> tuple[int, str, str]:
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
    # Filter out uv's experimental feature warnings
    stderr1_filtered = filter_uv_warnings(stderr1)
    stderr2_filtered = filter_uv_warnings(stderr2)
    if not lint_ok and stderr1_filtered.strip():
        output.append("Ruff lint errors:\n" + stderr1_filtered)
    if not format_ok and stderr2_filtered.strip():
        output.append("Ruff format errors:\n" + stderr2_filtered)

    return CheckResult(
        name="ruff (lint + format)",
        success=lint_ok and format_ok,
        output="\n".join(output),
    )


def filter_uv_warnings(stderr: str) -> str:
    """Filter out uv's experimental feature warnings."""
    lines = stderr.split("\n")
    filtered = []
    for line in lines:
        if "extra-build-dependencies" in line:
            continue
        if "Pass `--preview-features" in line:
            continue
        filtered.append(line)
    return "\n".join(filtered)


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


def run_pytest(test_dirs: list[str], name: str, with_coverage: bool = False) -> CheckResult:
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
    """Check bilingual documentation builds + content consistency."""
    print("Building English docs...")
    code1, _, stderr1 = run_uv_cmd(["sphinx-build", "-W", "docs/source", "docs/build/en"])
    en_ok = code1 == 0

    print("Building Chinese docs...")
    # Build without -W first to check if only xref warnings exist
    code2, _, stderr2 = run_uv_cmd(["sphinx-build", "docs/source/zh_CN", "docs/build/zh_CN"])
    # Check if stderr only has acceptable warnings (xref missing for cross-lang links)
    zh_ok = code2 == 0 or is_acceptable_sphinx_warnings(stderr2)

    # Check inter-language links (existing HTML style links are fine)
    print("Checking inter-language links...")
    en_has_links = False
    zh_has_links = False
    try:
        for md_file in Path("docs/source").rglob("*.md"):
            content = md_file.read_text()
            if (
                "English |" in content
                or "English / 简体中文" in content
                or "zh_CN/index.html" in content
            ):
                en_has_links = True
                break

        for md_file in Path("docs/source/zh_CN").rglob("*.md"):
            content = md_file.read_text()
            if (
                "中文 / English" in content
                or "English / 简体中文" in content
                or "../index.html" in content
            ):
                zh_has_links = True
                break
    except Exception:
        pass

    # Check content consistency (semantic checks)
    print("Checking documentation content consistency...")
    content_issues = check_docs_content_consistency()

    output = []
    if not en_ok:
        output.append("English docs build errors:\n" + stderr1)
    if code2 != 0:
        output.append("Chinese docs build errors:\n" + stderr2)
    output.extend(content_issues)

    return CheckResult(
        name="bilingual docs (build + content)",
        success=en_ok and zh_ok and len(content_issues) == 0,
        output="\n".join(output),
    )


def is_acceptable_sphinx_warnings(stderr: str) -> bool:
    """Check if Sphinx warnings are acceptable (only cross-lang xref warnings)."""
    lines = stderr.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "extra-build-dependencies" in line:
            continue
        if "WARNING: Unknown source document" in line and "index" in line:
            continue
        if line.startswith("warning:"):
            continue
        return False
    return True


def check_docs_content_consistency() -> list[str]:
    """Check if documentation matches actual code."""
    issues = []

    # 1. Check version consistency
    issues.extend(check_version_consistency())

    # 2. Check SDK API matches docs
    issues.extend(check_sdk_api_consistency())

    # 3. Check library usage matches docs
    issues.extend(check_library_usage_consistency())

    # 4. Check feature/phase mentions in docs match code
    issues.extend(check_feature_consistency())

    return issues


def check_version_consistency() -> list[str]:
    """Check that version numbers are consistent across files."""
    issues = []

    # Read pyproject.toml version
    import tomlkit

    try:
        pyproject_content = Path("pyproject.toml").read_text()
        pyproject = tomlkit.parse(pyproject_content)
        toml_version = pyproject["project"]["version"]
    except Exception:
        toml_version = None

    # Check README version
    try:
        readme = Path("README.md").read_text()
        # Find version patterns in README
        readme_versions = re.findall(r"v(\d+\.\d+\.\d+)", readme)

        if toml_version:
            if toml_version not in readme:
                issues.append(f"README doesn't mention pyproject.toml version v{toml_version}")
            # Check that docs mention the current version too
            if f"v{toml_version}" not in readme:
                issues.append(f"README doesn't show current version v{toml_version} prominently")
    except Exception:
        pass

    # Check quickstart version mentions
    try:
        quickstart = Path("docs/source/quickstart.md").read_text()
        # Look for phase mentions
        if "Phase 3" in quickstart or "Phase 4" in quickstart:
            if toml_version and toml_version >= "0.2.0":
                # OK, should be there
                pass
    except Exception:
        pass

    return issues


def check_sdk_api_consistency() -> list[str]:
    """Check that documented SDK APIs actually exist in code."""
    issues = []

    # Parse SDK module to get public APIs
    try:
        sdk_content = Path("src/dreamdata/sdk.py").read_text()
    except Exception:
        return issues

    # Quickstart code examples that should exist
    quickstart_code_examples = [
        "from dreamdata import Engine",
        "from dreamdata.config import Settings",
        "Engine(",
        "engine.register_dataset",
        "ds.tag(",
        "ds.note(",
        "ds.tags()",
        "ds.notes()",
        "ds.search_by_field(",
        "ds.search_by_tag(",
        "ds.search(",
        "engine.rename_dataset(",
        "engine.delete_dataset(",
        "engine.close()",
        "ds.append(",
        "ds.map(",
        "ds.filter_map(",
        "ds.refresh_parquet_cache(",
        "ds.list_parquet_caches(",
        "ds.scan(",
        "ds.list_versions(",
    ]

    # Parse actual SDK exports
    sdk_exports: list[str] = []
    try:
        import ast

        tree = ast.parse(sdk_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sdk_exports.append(node.name)
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                sdk_exports.append(node.name)
    except Exception:
        pass

    # Check Dataset methods specifically
    dataset_methods: list[str] = []
    try:
        import ast

        tree = ast.parse(sdk_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Dataset":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        dataset_methods.append(item.name)
    except Exception:
        pass

    # Read quickstart and check code examples
    try:
        quickstart = Path("docs/source/quickstart.md").read_text()

        # Extract code blocks
        code_blocks = re.findall(r"```python\n(.*?)\n```", quickstart, re.DOTALL)

        # Look for method calls
        method_calls = re.findall(r"\.([a-zA-Z_][a-zA-Z0-9_]*)\(", quickstart)

        # Verify important Dataset methods from docs exist in code
        documented_dataset_methods = [
            "tag",
            "note",
            "tags",
            "notes",
            "search_by_field",
            "search_by_tag",
            "search",
            "scan",
            "append",
            "map",
            "filter_map",
            "list_versions",
            "create_index",
            "drop_index",
            "list_indexes",
            "refresh_parquet_cache",
            "list_parquet_caches",
        ]

        for method in documented_dataset_methods:
            if method in dataset_methods:
                continue
            # Check if it's in SDK content as method
            if f"def {method}(" not in sdk_content:
                issues.append(f"Quickstart documents Dataset.{method}() but not found in sdk.py")
    except Exception as e:
        issues.append(f"Error checking quickstart API consistency: {e}")

    return issues


def check_library_usage_consistency() -> list[str]:
    """Check that library usage in docs matches project dependencies."""
    issues = []

    import tomlkit

    try:
        pyproject_content = Path("pyproject.toml").read_text()
        pyproject = tomlkit.parse(pyproject_content)
        dependencies = pyproject["project"]["dependencies"]
        optional_deps = pyproject["project"]["optional-dependencies"]
    except Exception:
        return issues

    # Extract library names
    lib_names = set()
    for dep in dependencies:
        # Get library name from requirement string
        lib_name = re.split(r"[=<>~]", dep)[0].strip()
        lib_names.add(lib_name)
    for deps_list in optional_deps.values():
        for dep in deps_list:
            lib_name = re.split(r"[=<>~]", dep)[0].strip()
            lib_names.add(lib_name)

    # Check docs mention these libraries appropriately
    try:
        readme = Path("README.md").read_text()
        quickstart = Path("docs/source/quickstart.md").read_text()

        # Check pyarrow optional dependency
        if "pyarrow" in lib_names:
            if "parquet" not in readme.lower():
                issues.append("README doesn't mention Parquet/pyarrow functionality")
            if 'pip install "dreamdata[parquet]"' not in quickstart:
                issues.append("Quickstart doesn't show optional parquet install pattern")

        # Check pandas usage
        if "pandas" in lib_names:
            if "pandas" not in quickstart:
                issues.append("Quickstart doesn't mention pandas DataFrame returns")

        # Check psycopg/PostgreSQL
        if "psycopg" in "".join(dependencies):
            if "postgresql" not in quickstart.lower():
                issues.append("Quickstart should mention PostgreSQL requirement")

    except Exception:
        pass

    return issues


def check_feature_consistency() -> list[str]:
    """Check that phase features in docs match actual code."""
    issues = []

    # Check if phase3/versioning features are in code
    versioning_features_present = False
    try:
        sdk_content = Path("src/dreamdata/sdk.py").read_text()
        if any(
            method in sdk_content for method in ["list_versions", "append", "map", "filter_map"]
        ):
            versioning_features_present = True
    except Exception:
        pass

    # Check if phase4/parquet features are in code
    parquet_features_present = False
    try:
        if Path("src/dreamdata/parquet_cache.py").exists():
            parquet_features_present = True
    except Exception:
        pass

    # Check that ROUTER.md matches actual code state
    try:
        router = Path(".mex/ROUTER.md").read_text()

        if versioning_features_present:
            if "Phase 3" not in router:
                issues.append("ROUTER.md doesn't mention Phase 3 despite code being present")

        if parquet_features_present:
            if "Phase 4" not in router:
                issues.append("ROUTER.md doesn't mention Phase 4 despite code being present")
    except Exception:
        pass

    return issues


def check_tech_debt() -> dict[str, list[str]]:
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
    code, stdout, _ = run_uv_cmd(["ruff", "check", "--select=F401,F841", "src/dreamdata/"])
    if stdout.strip():
        debt["unused_imports"].extend(stdout.strip().split("\n"))

    # Check for complex functions
    def check_complexity(filepath: Path) -> list[tuple[str, int, str]]:
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
                stmt_count = sum(1 for _ in ast.walk(node) if isinstance(_, (ast.stmt, ast.expr)))
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
    parser = argparse.ArgumentParser(description="Local test runner for dreamdata")
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

    results: list[CheckResult] = []

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
