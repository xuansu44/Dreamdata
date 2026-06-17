# Pattern Index

Lookup table for all pattern files in this directory. Check here before starting any task — if a pattern exists, follow it.

| Pattern | Use when |
|---------|----------|
| [add-sdk-method.md](add-sdk-method.md) | Adding a new method to the `Engine` or `Dataset` facade — the core repeatable structural task |
| [debug-duckdb-scan.md](debug-duckdb-scan.md) | Diagnosing wrong results or errors in a DuckDB JSONL/Parquet scan — the main read-path failure boundary |
| [register-dataset.md](register-dataset.md) | Registering a new dataset from JSONL files — the first end-to-end flow (scan → offsets → fields → file_stats → PostgreSQL) |

## Phase-1 status (2026-06-17)

All three patterns above were exercised end-to-end in Phase 1 and remain accurate. Phase-1 specifics that may surprise a reader:

- `register-dataset` now also re-imports prior metadata if an `overwrite=True` registration fails mid-flight — the workspace dir is moved aside before deletion, restored on rollback, and re-scanned to rebuild row_sources/file_stats.
- `debug-duckdb-scan` is partially superseded for Phase 1: DuckDB is not on the read path. Use it when working in Phase 2 (indexing) or for any future DuckDB integration.
