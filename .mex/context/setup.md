---
name: setup
description: Dev environment setup and commands. Load when setting up the project for the first time or when environment issues arise.
triggers:
  - "setup"
  - "install"
  - "environment"
  - "getting started"
  - "how do I run"
  - "local development"
edges:
  - target: context/stack.md
    condition: when specific technology versions or library details are needed
  - target: context/architecture.md
    condition: when understanding how components connect during setup
last_updated: 2026-06-17
---

# Setup

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** — running and reachable; the SDK needs a dedicated database.
- **uv** — install via `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`).
- **Local filesystem workspace** — a directory the SDK can read/write JSONL and (later) Parquet into.

## First-time Setup

1. `uv sync` — install dependencies from `pyproject.toml` into a project-local venv.
2. Create a PostgreSQL database: `createdb dreamdata` (or your DBA's process).
3. Copy `.env.example` to `.env` and fill in `DATABASE_URL` and `WORKSPACE_PATH`.
4. Apply schema migrations: `uv run alembic upgrade head`.
5. Create the workspace directory: `mkdir -p "$WORKSPACE_PATH"`.
6. Run the smoke test: `uv run pytest tests/sdk/test_register.py -q`.

## Environment Variables

- `DATABASE_URL` (required) — PostgreSQL connection string, e.g. `postgresql://user:pass@localhost:5432/dreamdata`.
- `WORKSPACE_PATH` (required) — absolute path to the dataset storage root (JSONL + delta + Parquet cache).
- `USER_ID` (required in MVP) — single-user MVP uses this as the annotation author; multi-user isolation arrives in phase 2.
- `DUCKDB_MEMORY_LIMIT` (optional) — e.g. `4GB`; controls DuckDB's memory budget for scans.
- `DUCKDB_THREADS` (optional) — DuckDB worker threads; defaults to CPU count.
- `PARQUET_CACHE_DIR` (optional, later) — defaults to `$WORKSPACE_PATH/.engine/cache`.
- `LOG_LEVEL` (optional) — `INFO` default.

## Common Commands

- `uv run python` — REPL with the project venv.
- `uv run pytest` — full test suite (all layers).
- `uv run pytest tests/unit/ -q` — L1 unit tests.
- `uv run pytest tests/component/ -q` — L2 component tests (real PostgreSQL + DuckDB + filesystem).
- `uv run pytest tests/sdk/ -q` — L3 SDK integration tests, one module per F-feature.
- `uv run pytest tests/property/ -q` — L4 property tests (Hypothesis).
- `uv run pytest tests/fuzz/ -q` — L5 fuzz tests.
- `uv run pytest tests/scale/ -q` — L6 scale smoke at 1M rows (slow).
- `uv run pytest tests/e2e/ -q` — L8 acceptance scenario.
- `uv run mutmut run` — L7 mutation testing (slow; nightly).
- `uv run coverage report -m` — coverage summary.
- `uv run ruff check .` — lint.
- `uv run ruff format .` — format.
- `uv run mypy --strict src/dreamdata/sdk.py` — strict type-check on the public SDK surface.
- `uv run alembic upgrade head` — apply DB migrations.

## Common Issues

**PostgreSQL connection refused:** verify `DATABASE_URL`, that `pg_isready` succeeds, and that the database exists (`psql -lqt | grep dreamdata`).
**DuckDB out-of-memory on large scan:** lower `DUCKDB_MEMORY_LIMIT` or `DUCKDB_THREADS`; ensure the workspace is on fast local disk, not a slow network mount.
**`read_json_auto` infers wrong types on mixed-schema JSONL:** expected — phase-1 search tolerates this via field-path access rather than typed columns. [TO BE DETERMINED — document the specific mitigation after first implementation.]
**Workspace path permissions:** the SDK process needs read+write on `WORKSPACE_PATH`; verify with `touch "$WORKSPACE_PATH/.engine/.write-test"`.
