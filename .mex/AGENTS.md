---
name: agents
description: Always-loaded project anchor. Read this first. Contains project identity, non-negotiables, commands, and pointer to ROUTER.md for full context.
last_updated: 2026-06-17
---

# dreamdata

## What This Is

A versioned management engine for LLM training data — JSONL-native storage with multi-user tag isolation, flexible retrieval, functional transforms, and dataset versioning, scaling to TBs.

## Non-Negotiables

- **JSONL files are read-only** — all mutations create new versions; never edit originals in place.
- **All metadata lives in PostgreSQL** — never write tags, indexes, or version chain back into files.
- **DuckDB is read-only for business data** — it scans JSONL/Parquet; writes go through the version manager.
- **The SDK is the only public surface** — user code never calls DuckDB or PostgreSQL directly.

## Commands

- REPL: `uv run python`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type check: `uv run mypy src/dreamdata`
- Migrate DB: `uv run alembic upgrade head` [TO BE DETERMINED — migration tool]

## Scaffold Growth
After meaningful work, run GROW:
- Ground: what changed in reality?
- Record: update `ROUTER.md` and relevant `context/` files
- Orient: create or update a `patterns/` runbook if this can recur
- Write: bump `last_updated` on changed scaffold files and run `mex log` when rationale matters

The scaffold grows from real work, not just setup. See the GROW step in `ROUTER.md` for details.

## Navigation
At the start of every session, read `ROUTER.md` before doing anything else.
For full project context, patterns, and task guidance — everything is there.
