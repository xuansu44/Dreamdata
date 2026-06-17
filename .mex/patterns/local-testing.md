---
name: local-testing
description: How to run local tests with the local-test-agent — full test layers, bilingual docs validation, tech debt detection. Use when the user asks to "run tests", "check docs", or "find tech debt".
---

# Local Testing Pattern

## Quick Start

Use the `local-test-agent` via:
```
# In chat:
Use the local-test-agent to run all tests.
```

Or use the script directly:
```bash
# Quick check (most common)
scripts/run_local_tests.py --quick

# Full test suite
scripts/run_local_tests.py --full

# Docs-only check
scripts/run_local_tests.py --docs-only

# Full + scale tests (slow)
scripts/run_local_tests.py --full --scale
```

## What It Runs

### Static Checks (Always)
- Ruff lint + format
- MyPy (strict on SDK + check-untyped-defs on all)

### Test Layers
- L1 Unit (`tests/unit/`)
- L2 Component (`tests/component/`)
- L3 SDK Integration (`tests/sdk/`)
- L4 Property-based (`tests/property/`)
- L5 Fuzz (`tests/fuzz/`)
- L6 Scale (`tests/scale/` — optional)
- L8 E2E (`tests/e2e/`)

### Documentation
- English sphinx build (no warnings)
- Chinese sphinx build (no warnings)
- Inter-language links presence

### Tech Debt Detection
- TODO/FIXME/XXX/HACK comments
- Unused imports/vars (F401/F841)
- Complex functions (>50 statements)

## Using the Agent

When the user asks for:

| User says | Agent should do |
|---|---|
| "run tests" | `--quick` mode (fast) |
| "run all tests" | `--full` mode |
| "check docs" | `--docs-only` mode |
| "find tech debt" | Run debt check only and report |
| "check coverage" | Run with coverage report |

## Before Testing

1. Make sure PostgreSQL is running with `dreamdata_test` database
2. Make sure Alembic migrations are up to date: `uv run alembic upgrade head`
3. Make sure `uv sync --extra dev` has been run

## Interpreting Results

The agent reports:
- 🟢 All passing
- 🟡 Warnings (e.g., docs warnings, coverage gaps)
- 🔴 Failures (tests failed, static checks failed)

Always show the actionable items first, sorted by priority.
