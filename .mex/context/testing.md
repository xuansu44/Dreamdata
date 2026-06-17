---
name: testing
description: How dreamdata is tested — layers, strategies, automation gates, and what "done" means for quality. Load when writing tests, designing coverage, or questioning whether something can be tested.
triggers:
  - "testing"
  - "test"
  - "coverage"
  - "automate"
  - "fuzz"
  - "property"
  - "mutation"
edges:
  - target: context/conventions.md
    condition: when applying test rules to code style
  - target: context/architecture.md
    condition: when tests need to assert architectural invariants
  - target: patterns/add-sdk-method.md
    condition: when adding an SDK method that needs test scaffolding
last_updated: 2026-06-17
---

# Testing

## Principle

dreamdata is SDK-only with no UI. **Every behavior is callable from code, therefore every behavior is testable.** "Manual exploratory check" is not a category that applies here — it is replaced by property-based testing, fuzzing, and mutation testing. The automated test suite is the only quality gate; no human-in-the-loop sign-off step exists in the path to "done."

## Layers

Eight layers, every one fully automated.

### L1 — Unit
Pure functions, no I/O. Tested in isolation under `tests/unit/`.
- Field-path parser (`messages.0.role` → tokens; reject out-of-bounds index, index on non-list, missing intermediate key)
- Field inference (sample, union across files, array index walk)
- Path relativization (absolute → relative to `WORKSPACE_PATH`)
- Typed exception constructors carry their context fields
- Tag set operations (dedup, unicode normalization)

### L2 — Component
One internal layer against its real dependency under `tests/component/`. **No mocks of PostgreSQL, DuckDB, or the filesystem.** Mocking the engines defeats the architectural validation.
- `meta/` against a real PostgreSQL test database (testcontainers, or a dedicated `dreamdata_test` DB)
- `engine/` against real DuckDB scanning real JSONL/Parquet files
- `storage/` against the real filesystem (`tmp_path`)

### L3 — SDK Integration (F1–F10)
One test module per feature under `tests/sdk/`. Each module covers happy path, edge cases, and error cases. Every test also asserts architectural invariants:
- Original JSONL never modified (mtime + sha256 before/after each op)
- `row_sources` row count == file line count
- All stored paths relative to `WORKSPACE_PATH`
- DuckDB read-only — `engine/` writes no business files
- Typed exceptions with context — never `None`-on-failure, never swallowed

### L4 — Property-based
Hypothesis strategies generate inputs from schemas; invariants must hold across the generated input space. Lives under `tests/property/`.
- JSONL row shapes: top-level scalars, nested dicts, arrays of mixed types, missing fields, nulls, deeply nested
- Field paths: valid + invalid (out-of-bounds index, non-list index, missing intermediate key)
- Tag values: duplicates, unicode, empty, long strings
- Dataset names: valid + invalid + collisions

Invariants under test:
- `register(files) → row_sources count == sum(line counts)`
- `tag(rows) → search(tag) returns exactly those rows`
- `combined_search(field, tag) == field_search ∩ tag_search` (set equality)
- `delete(name) → no metadata references it; filesystem dir removed`
- `rename(old) → search(old) raises; search(new) returns same rows`
- `overwrite → tag count == 0, note count == 0`

### L5 — Fuzz
Adversarial inputs that must not crash silently or corrupt state. Lives under `tests/fuzz/`.
- Malformed JSON lines (truncated, trailing comma, unquoted keys)
- Encoding edge cases (BOM, surrogate pairs, invalid UTF-8 bytes, mixed encodings across files)
- Path traversal in dataset names (`../etc/passwd`, absolute paths, null bytes)
- Concurrent registration of same name (race) — expected: typed exception, no partial state
- 1 MB single-line JSON, 1000-level nesting, 10 000 field paths
- Empty files, files of only newlines, files without trailing newline
- Dataset-name and tag-value length limits

### L6 — Scale smoke (1M rows)
Not run on every PR. Generated JSONL is deterministic (seeded RNG, cached in CI). Lives under `tests/scale/`.
Assertions:
- Registration completes within time budget (assert `<T` seconds; calibrate after first implementation)
- Full scan returns exactly 1M rows
- Field filter returns the expected subset with exact count
- Memory peak under `DUCKDB_MEMORY_LIMIT` (cgroup-enforced container if the CI runner lacks fine control)
- `row_sources` insertion throughput asserts bulk `COPY`, not per-row `INSERT`

### L7 — Mutation testing
mutmut or cosmic-ray on `meta/`, `engine/`, `storage/`. Mutation score ≥ 85% required. Nightly job; failing score opens an issue, not a build break.

### L8 — Acceptance E2E
Single end-to-end pytest scenario under `tests/e2e/`: register → tag → note → field-search → tag-search → combined-search → rename → overwrite → delete. This is the "vertical slice works" proof.

## Static Gates

- `uv run ruff check .` — zero errors
- `uv run ruff format --check .` — clean
- `uv run mypy --strict src/dreamdata/sdk.py` — clean
- Coverage: ≥ 95% on `sdk.py`, `meta/`, `engine/`, `storage/`; ≥ 80% overall

## CI Matrix

- Python: 3.11, 3.12, 3.13
- PostgreSQL: 15, 16
- DuckDB: pinned to latest stable (unpin only when intentionally upgrading)
- OS: Linux in CI; tests must also pass on macOS dev machines

## CI Pipeline

| Trigger | Runs |
|---|---|
| Pull request | L1, L2, L3, L5, static gates |
| Merge to main | + L4, L8 |
| Nightly | + L6 (scale), L7 (mutation) |

## Test Data

- Programmatic JSONL generators under `tests/fixtures/generators.py` — no large files committed.
- Hand-crafted adversarial fixtures under `tests/fixtures/<feature>/` — small, deterministic, commented.
- L6 generator is seeded for reproducibility; CI caches the generated file.

## Test Database

- Dedicated `dreamdata_test` database; each test session truncates relevant tables in a session fixture.
- No shared state across tests; each test uses a unique dataset name (uuid suffix).
- Transactional fixtures where possible: `meta/` tests wrap in a transaction and roll back.

## Verify Checklist

Before claiming a feature is tested:
- [ ] L1 unit tests cover all pure helpers used by the feature.
- [ ] L2 component tests cover each internal layer the feature touches.
- [ ] L3 SDK integration module exists for the feature (happy + edge + error).
- [ ] L4 property test exists for the feature's invariants.
- [ ] L5 fuzz cases exist for the feature's input boundaries.
- [ ] Architectural invariants asserted (immutability, metadata-as-source-of-truth, DuckDB read-only).
- [ ] No mocks of PostgreSQL / DuckDB / filesystem in L2 or above.
- [ ] Coverage thresholds met for the new code.
