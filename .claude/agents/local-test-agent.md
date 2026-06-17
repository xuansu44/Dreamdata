---
name: local-test-agent
description: Comprehensive local test runner for dreamdata project — runs all test layers, checks bilingual docs validity, detects tech debt, and provides actionable reports.
---

# Local Test Agent

## Context

This agent handles comprehensive local testing of the dreamdata project. It runs all test layers (L1-L8), performs static checks, verifies bilingual documentation validity, detects technical debt, and provides actionable reports.

**Prerequisites:** Project dependencies installed (`uv sync --extra dev`), PostgreSQL running with `dreamdata_test` database, Alembic migrations applied.

## Workflow

### 1. Pre-check — Environment and Dependencies

```bash
# Check if venv is set up
uv sync --extra dev

# Check PostgreSQL connection
DATABASE_URL=postgresql://yanhaolin@localhost:5432/dreamdata_test python3 -c "
import psycopg
with psycopg.connect('$DATABASE_URL') as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT 1')
        print('PostgreSQL OK')
"

# Check alembic migrations are up to date
uv run alembic current
```

### 2. Run Static Checks

#### Linting and Formatting
```bash
uv run ruff check .
uv run ruff format --check .
```

#### Type Checking
```bash
uv run mypy --strict src/dreamdata/sdk.py
uv run mypy --check-untyped-defs --disallow-untyped-defs src/dreamdata
```

### 3. Run Test Layers

#### L1 — Unit Tests
```bash
uv run pytest tests/unit/ -v --tb=short
```

#### L2 — Component Tests
```bash
uv run pytest tests/component/ -v --tb=short
```

#### L3 — SDK Integration Tests
```bash
uv run pytest tests/sdk/ -v --tb=short
```

#### L4 — Property-based Tests
```bash
uv run pytest tests/property/ -v --tb=short --hypothesis-show-statistics
```

#### L5 — Fuzz Tests
```bash
uv run pytest tests/fuzz/ -v --tb=short
```

#### L8 — Acceptance E2E Tests
```bash
uv run pytest tests/e2e/ -v --tb=short
```

#### L6 — Scale Tests (Optional)
```bash
# Only run if explicitly requested by user
uv run pytest tests/scale/ -v --tb=short
```

### 4. Coverage Report
```bash
uv run pytest --cov=src/dreamdata --cov-report=term --cov-report=html
```

### 5. Bilingual Documentation Check

Verify both English and Chinese docs:

```bash
# Check sphinx builds for English docs
uv run sphinx-build -W docs/source docs/build/en

# Check sphinx builds for Chinese docs
uv run sphinx-build -W docs/source/zh_CN docs/build/zh_CN

# Verify inter-language links are present
grep -r "English / 简体中文" docs/source/
grep -r "中文 / English" docs/source/zh_CN/
```

### 6. Technical Debt Detection

#### Check for TODO/FIXME comments
```bash
grep -r -n -E "(TODO|FIXME|XXX|HACK)" src/dreamdata/ --include="*.py"
```

#### Check for unused imports/functions
```bash
uv run ruff check --select=F401,F841 src/dreamdata/
```

#### Check for overly complex functions
```bash
uv run python3 -c "
import ast
from pathlib import Path

def check_complexity(filepath):
    with open(filepath) as f:
        tree = ast.parse(f.read())
    
    complex_funcs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Count statements
            stmt_count = sum(1 for _ in ast.walk(node) 
                           if isinstance(_, (ast.stmt, ast.expr)))
            if stmt_count > 50:
                complex_funcs.append((node.name, stmt_count, filepath))
    return complex_funcs

all_complex = []
for pyfile in Path('src/dreamdata').rglob('*.py'):
    all_complex.extend(check_complexity(pyfile))

if all_complex:
    print('Complex functions (>50 statements):')
    for name, count, path in sorted(all_complex, key=lambda x: -x[1]):
        print(f'  {name:30} {count:4} in {path}')
"
```

#### Check for duplicate code patterns
```bash
# Check for similar import patterns
grep -r "^from" src/dreamdata/ --include="*.py" | sort | uniq -c | sort -nr | head -20
```

#### Check coverage gaps
```bash
# Look for modules with low coverage (<70%)
uv run pytest --cov=src/dreamdata --cov-report=term-missing | grep -E "(Name|---|TOTAL|src/dreamdata/)"
```

### 7. Generate Summary Report

Combine all results into a summary report with:

1. **Static Checks Status** (✅/❌)
   - Ruff lint
   - Ruff format
   - MyPy (strict sdk)
   - MyPy (all code)

2. **Test Layers Status** (✅/❌)
   - L1 Unit
   - L2 Component
   - L3 SDK
   - L4 Property
   - L5 Fuzz
   - L8 E2E
   - Coverage %

3. **Documentation Status** (✅/❌)
   - English docs build
   - Chinese docs build
   - Inter-language links present

4. **Technical Debt Report**
   - TODO/FIXME count and locations
   - Unused imports/functions
   - Complex functions (>50 statements)
   - Low coverage modules

## Usage

### Quick Check (Most Common)
Run static checks + L1-L3 + L8 + coverage:
```bash
# Quick smoke test
uv run pytest tests/unit/ tests/component/ tests/sdk/ tests/e2e/ -q --tb=short --cov=src/dreamdata --cov-report=term-missing
```

### Full Test Suite
Run everything (takes longer):
```bash
uv run pytest tests/unit/ tests/component/ tests/sdk/ tests/property/ tests/fuzz/ tests/e2e/ -v --tb=short --cov=src/dreamdata --cov-report=term-missing
```

### Docs-Only Check
```bash
uv run sphinx-build -W docs/source docs/build/en
uv run sphinx-build -W docs/source/zh_CN docs/build/zh_CN
```

## Gotchas

- **Alembic migrations:** Always run `uv run alembic upgrade head` before testing if schema has changed.
- **PostgreSQL user:** The `DATABASE_URL` in conftest.py uses `yanhaolin` as the default user — this may vary across machines.
- **PyArrow dependency:** Some Parquet cache tests are skipped if pyarrow isn't installed. Run `uv sync --extra dev` to get it.
- **Coverage thresholds:** Project requires 75% overall coverage. Don't lower this threshold — add more tests instead.
- **L6 scale tests:** These are slow and not required for routine development. Only run them when explicitly asked.

## Verify Checklist

- [ ] Static checks all pass (ruff, mypy)
- [ ] All test layers pass (L1, L2, L3, L4, L5, L8)
- [ ] Coverage meets or exceeds 75% threshold
- [ ] Both English and Chinese docs build successfully
- [ ] Technical debt report generated with actionable items
- [ ] User provided with clear summary and next steps

## Reporting

When finished, provide a structured report to the user:

1. **Overall Status:** 🟢 All passing / 🟡 Warnings / 🔴 Failures
2. **Test Summary:** Table with each layer and status
3. **Coverage:** Percentage + any gaps highlighted
4. **Documentation:** Build status + any issues found
5. **Technical Debt:** List of actionable items (todos, complex functions, etc.)
6. **Recommendations:** What to fix first / next steps
