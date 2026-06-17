---
name: debug-duckdb-scan
description: Diagnose failures and wrong results in a DuckDB JSONL/Parquet scan — the main read-path failure boundary. Use when search/scan returns wrong rows, wrong types, or errors.
triggers:
  - "duckdb error"
  - "scan fails"
  - "wrong results"
  - "search returns wrong rows"
  - "read_json_auto"
  - "pruning wrong"
edges:
  - target: context/query-and-indexing.md
    condition: when the read-path design and invariants are needed
  - target: patterns/add-sdk-method.md
    condition: when the bug is in an SDK method's read path
last_updated: 2026-06-16
---

# Debug a DuckDB Scan

## Context

Load `context/query-and-indexing.md` for the read-path model. DuckDB scans are the main read-path failure boundary: file path issues, schema inference, nested fields, encoding, and pruning all surface here.

## Steps

1. **Reproduce minimally.** Get the smallest filter + dataset that reproduces. Note expected vs actual row count.
2. **Check the file list.** Print the resolved `row_sources` file list for the version. Each path should be relative to `WORKSPACE_PATH` and exist on disk. A missing or absolute path is the most common cause of zero-row scans.
3. **EXPLAIN the query.** In a REPL, run the DuckDB query with `EXPLAIN`. Confirm `read_json_auto` (or `read_parquet`) is hitting the expected files and that the filter is pushed down (not applied after a full load).
4. **Isolate the file.** If a UNION ALL across files misbehaves, scan each file separately to find the offending one.
5. **Check field inference.** `read_json_auto` infers types per file. For nested or mixed-schema fields, query the field path explicitly rather than relying on auto columns. [VERIFY AFTER FIRST IMPLEMENTATION — pin the exact DuckDB nested-access syntax used in this codebase.]
6. **Check pruning (phase 2+).** If indexes/file_stats are in play, confirm the pruned candidate set is a subset of the unpruned set. Pruning must never change results — if it does, the index is stale or the comparison logic is wrong.
7. **Check encoding.** UTF-8 only. If DuckDB reports parse errors at specific byte offsets, inspect those bytes — usually a non-UTF-8 byte or a truncated line.

## Gotchas

- **Globs vs explicit file lists.** `read_json_auto('dir/*.jsonl')` and `read_json_auto([file1, file2])` behave differently for ordering and union. [VERIFY AFTER FIRST IMPLEMENTATION — pin which form the engine uses and why.]
- **Mixed schemas across files.** Auto-inferred columns may differ per file; the UNION ALL may produce NULLs or drop columns silently. Explicit field-path access avoids this.
- **Logical row order.** DuckDB does not preserve file order across a UNION ALL by default — the SDK must project logical order via `row_sources.row_idx`. Forgetting this is a common source of "the rows are shuffled" bugs.
- **NULLs in indexed fields.** Range pruning with NULL min/max can skip files that should be included. Phase 2 indexing must handle NULL explicitly. [VERIFY AFTER FIRST IMPLEMENTATION.]
- **Memory budget.** A scan that worked on a small dataset may OOM on a large one. Check `DUCKDB_MEMORY_LIMIT`.

## Verify

Before closing the debug session:
- [ ] The minimal reproduction now returns the expected row count.
- [ ] `EXPLAIN` shows the filter pushed into the scan where possible.
- [ ] If pruning was involved, pruned vs unpruned return identical results.
- [ ] The fix is in the engine layer (`engine/`), not patched in the facade.
- [ ] A regression test is added under `tests/engine/` for the specific failure.

## Debug

- **Zero rows returned, no error:** file list is empty or paths are wrong — check `row_sources` resolution first.
- **All rows returned ignoring filter:** filter is being applied post-load instead of pushed down — restructure the query so DuckDB sees the predicate at scan time.
- **Type errors on a field that looks numeric:** `read_json_auto` inferred it as varchar because one file had a non-numeric value; use explicit field-path access or fix the data.
- **Rows shuffled across the union:** the SDK is not projecting `row_sources.row_idx` into the final order — add an `ORDER BY row_idx`.

## Update Scaffold

- [ ] If the root cause is a new gotcha, add it to `context/query-and-indexing.md` or this pattern.
- [ ] If the same failure recurs, consider promoting the regression test into the verify checklist.
