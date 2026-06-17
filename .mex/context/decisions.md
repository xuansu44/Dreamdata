---
name: decisions
description: Key architectural and technical decisions with reasoning. Load when making design choices or understanding why something is built a certain way.
triggers:
  - "why do we"
  - "why is it"
  - "decision"
  - "alternative"
  - "we chose"
edges:
  - target: context/architecture.md
    condition: when a decision relates to system structure
  - target: context/stack.md
    condition: when a decision relates to technology choice
  - target: context/versioning.md
    condition: when a decision relates to the versioning/COW model
last_updated: 2026-06-17
---

# Decisions

HOW TO USE THIS FILE: each decision follows the format below. When a decision changes, DO NOT delete the old entry — mark it superseded and add the new entry above it. The history is the event clock.

## Decision Log

### Phase-2: field_index uses JSONB for type flexibility
**Date:** 2026-06-17
**Status:** Active
**Decision:** The `field_index.value` column uses PostgreSQL JSONB type to store all scalar values (strings, integers, floats, booleans, nulls) in one column. Comparison operators work directly with JSONB values.
**Reasoning:** Using a single JSONB column avoids having to manage multiple typed columns or requiring the user to specify field types upfront. DuckDB would have handled this automatically, but we're using the pure-Python read engine (Phase 1 decision) and PostgreSQL for metadata. JSONB gives flexibility and works with equality, range, and (indirectly) regex filters.
**Alternatives considered:** Separate typed columns (string_value, int_value, float_value, bool_value) — rejected because it complicates schema and queries; always storing as string — rejected because range comparisons wouldn't work correctly for numeric types.
**Consequences:** `file_stats.min_value` and `max_value` also use JSONB, keeping consistency across schema. Regex filtering can't use the index directly (scans after index pruning), which is acceptable tradeoff.

### Phase-2: multi-user isolation opt-out via user_id="*"
**Date:** 2026-06-17
**Status:** Active
**Decision:** Tags and notes are private to each user by default. To see all users' annotations, explicitly pass `user_id="*"` to `tags()`, `notes()`, or `search_by_tag()`.
**Reasoning:** Privacy by default is the right default for a multi-user system. The escape hatch `user_id="*"` is explicit and discoverable.
**Alternatives considered:** Always show all tags (Phase 1 behavior) — rejected because it's not privacy-safe; require explicit `user_id` every time — rejected because it's verbose for the common case (current user only).
**Consequences:** Backward compatible: existing code that didn't pass `user_id` continues to work, but now only sees current user's tags (change in Phase 2 behavior; test updated to reflect this).

### Phase-2: FieldFilter backward compatibility preserved
**Date:** 2026-06-17
**Status:** Active
**Decision:** `FieldFilter(path, value)` continues to work for equality checks, same as Phase 1. New advanced filters use `FieldFilter(path, value, op=...)` pattern or helper functions like `range_filter`, `regex_filter`.
**Reasoning:** No breaking changes for existing users; gradual adoption path for new features.
**Alternatives considered:** Breaking change to require `op=` for all filters — rejected because it would break all Phase 1 code; separate `AdvancedFieldFilter` class — rejected because it would complicate the API surface.
**Consequences:** The `FieldFilter` dataclass parameters ordered `(path, value, op=FilterOp.EQ)` to keep backward compatibility; helper functions provide cleaner API for advanced use cases.

### Phase-2: two-layer pruning (file_stats, then field_index)
**Date:** 2026-06-17
**Status:** Active
**Decision:** Pruning happens in two layers: first use `file_stats` to skip entire files that can't possibly match; then, if field index exists, use `field_index` to get candidate `row_idx` before scanning.
**Reasoning:** File pruning is cheap and effective for large datasets with many files; index pruning reduces scan work even further when applicable. The layered approach gives incremental benefits depending on what data exists.
**Alternatives considered:** Always scan without pruning (Phase 1) — rejected because it doesn't meet Phase 2 goals; index only, no file stats — rejected because file stats are already collected and provide benefit without index creation.
**Consequences:** `_run_scan` first tries `_try_file_prune`, then `_try_index_lookup`; users can opt out of index use with `use_index=False` parameter if needed.

### Release timing: 0.1.0 cuts NOW (Phase 2 complete)
**Date:** 2026-06-17
**Status:** Active
**Decision:** The first public release `0.1.0` cuts NOW that Phase 2 is complete.
**Reasoning:** Phase 2 delivered the two key missing pieces for a usable product: multi-user isolation and field indexing with pruning. The SDK is stable and the test suite is comprehensive.
**Alternatives considered:** Waiting for Phase 3 (versioning) — rejected because versioning is a power-user feature, not a release blocker.
**Consequences:** `0.1.0` is the first stable release with SemVer stability guarantee; future breaking changes will be documented and accompanied by a minor or major version bump.

### Phase-1 read engine: Python JSONL streaming, not DuckDB
**Date:** 2026-06-17
**Status:** Active (Phase 1 only — DuckDB returns for the Phase 2 columnar path)
**Decision:** The MVP read path scans JSONL via single-threaded Python file iteration in `engine/duckdb_engine.py`. The `DuckDBEngine` class name is preserved for forward compatibility, but the implementation does not invoke DuckDB.
**Reasoning:** DuckDB's `read_json_auto` parallelises file reads across threads. At 1M rows the worker threads emit results out of source order, and `row_number() OVER (ORDER BY (SELECT NULL))` assigns row numbers that no longer match the source file's line position. The SDK's per-file → global `row_idx` mapping (built from `row_sources` in registration order) then dereferences the wrong rows, breaking tag-search and combined-search at scale. Single-threaded DuckDB scans preserve order but defeat the parallelism that motivates DuckDB in the first place. Pure-Python streaming is simple, deterministic, and fast enough at 1M rows.
**Alternatives considered:**
- Force DuckDB single-threaded (`PRAGMA threads=1`): rejected — defeats DuckDB's value proposition; we'd be paying the dependency cost for no win.
- Inject a row-number column into the JSONL before DuckDB reads it: rejected — would require modifying the staged files, violating the "JSONL is read-only" invariant.
- Use DuckDB's `_filename` / `_file_row_number` metadata: not exposed for `read_json_auto` in the version we pin; would require a hot-fix and may regress.
- Defer the scale claim to Phase 2: rejected — Phase 1's scope explicitly states "must demonstrably work up to 1M rows".
**Consequences:**
- DuckDB stays in `pyproject.toml` (returns for Phase 2 indexing/pruning) but is not loaded by Phase-1 code paths.
- The architectural invariant "DuckDB never writes business data" holds vacuously in Phase 1.
- Scan throughput is bounded by Python's per-line `json.loads`; benchmarks at 1M rows complete in ~3 minutes total (register + scan + filters + tag searches), within the L6 budget.
- Phase 2 must reintroduce DuckDB carefully — the order-preservation issue must be solved (likely by switching to per-file scans with explicit row enumeration in Python and using DuckDB only for the columnar `field_index` queries).

### PM review cadence: phase-boundary delivery, not per-feature
**Date:** 2026-06-17
**Status:** Active
**Decision:** The PM reviews outcomes only at phase boundaries (when L1–L8 are all green for that phase), not after every F-feature or every PR. Claude develops the full phase autonomously between boundaries.
**Reasoning:** The PM consumes outcomes, not technical details; per-feature interruption costs more in context-switching than it saves in course correction. Phase 1 establishes the SDK skeleton, so direction errors would compound if caught late — but the SDK surface is small enough (10 methods) that one end-of-phase review catches any drift without 10 mid-phase interruptions. Phase 2+ has the Phase 1 skeleton as a stable anchor, so phase-boundary review is sufficient there too.
**Alternatives considered:** Per-feature review (rejected — too many interruptions for a PM who consumes outcomes; the SDK skeleton is small enough to review as a whole), hybrid "key feature" review (rejected — adds ambiguity about what counts as "key").
**Consequences:** Claude must NOT pause mid-phase for product-level questions unless a failure implies the phase scope itself is wrong. The phase-boundary handoff must be self-contained: working code, green tests, updated ROUTER, draft phase-docs. The PM's single review covers (a) the SDK surface shape, (b) the L8 E2E scenario, (c) the phase docs draft.

### Release timing: 0.1.0 cuts after Phase 2, not Phase 1
**Date:** 2026-06-17
**Status:** Active
**Decision:** The first public release (`0.1.0`) cuts after Phase 2 (field indexing + multi-user tag isolation) is complete, not after Phase 1.
**Reasoning:** Phase 1 alone delivers registration + single-user tags + DuckDB scan, but without field indexing the read path is brute-force scan (no pruning), and without multi-user isolation the tag semantics are ambiguous for any team usage. A public release that ships those limitations sets wrong expectations and locks in a "slow + single-user" reputation. Phase 2 closes both gaps; 0.1.0 then represents a usable product, not just a vertical slice.
**Alternatives considered:** 0.1.0 after Phase 1 (rejected — premature; users would hit scan-slowness and single-user limitation immediately), 0.1.0 after Phase 3 with versioning (rejected — too far out; versioning is a power-user feature, not a release blocker for first users).
**Consequences:** Phase 1 and Phase 2 are developed under `0.0.x` dev tags; no SemVer stability guarantee until 0.1.0. The SDK API may break between dev tags during these phases. `CHANGELOG.md` is maintained from day one regardless. Once 0.1.0 ships, breaking API changes require a 0.2.0 bump and a migration note.

### Per-phase Python SDK documentation is mandatory
**Date:** 2026-06-17
**Status:** Active
**Decision:** Every phase must ship updated user-facing SDK documentation alongside the code. A phase is not "done" until both L1–L8 are green AND the corresponding docs are written.
**Reasoning:** The SDK is the only public surface; without docs it is unusable to anyone except the author. Postponing docs to "after we ship" creates a backlog that compounds — by Phase 3 the delta from Phase 1 is too large to document in one pass. Writing docs per phase also forces a clear articulation of what the phase's user-visible behavior is, which is itself a check on scope.
**Alternatives considered:** Docstrings only, no separate docs (rejected — docstrings are reference, not tutorial; new users need quickstart + per-phase guides), docs at 0.1.0 only (rejected — too late, and incentivises shipping code without thinking about how it reads).
**Consequences:** Project adds a `docs/` directory at root with Sphinx + autodoc. Required per phase: (1) update `docs/source/quickstart.md` if user-facing flow changed, (2) write `docs/source/phases/phase-N.md` covering what's new + worked examples, (3) ensure API reference auto-generated from docstrings covers the new SDK methods. Docs build (`uv run sphinx-build`) is added to CI gates from Phase 1. The Verify Checklist in `conventions.md` is extended to include "phase docs written and build-clean".

### Use DuckDB as the read-side query engine
**Date:** 2026-06-16
**Status:** Active
**Decision:** All read-side scans and filters over JSONL/Parquet execute through an embedded DuckDB instance.
**Reasoning:** DuckDB is an embedded OLAP engine with column pruning, predicate pushdown, and vectorised execution. It handles TB-scale JSONL/Parquet on a single machine with excellent Python integration, without standing up a separate service.
**Alternatives considered:** Spark (rejected — too heavy for single-machine MVP, operational overhead), Presto/Trino (rejected — requires a cluster), pure-Python scan (rejected — cannot match DuckDB's scan/pruning performance at scale).
**Consequences:** DuckDB is read-only for business data. All writes go through the version manager into delta JSONL files. The SDK must manage DuckDB's memory budget and connection lifecycle carefully.

### Use PostgreSQL for all metadata
**Date:** 2026-06-16
**Status:** Active
**Decision:** All structured metadata (datasets, versions, row_sources, annotations, indexes, file_stats) lives in PostgreSQL.
**Reasoning:** PostgreSQL is mature, supports complex transactions and concurrency, and a single table can carry billions of index rows. It is the right tool for structured relational metadata at our scale.
**Alternatives considered:** SQLite (rejected — weaker concurrency, harder to scale to read replicas later), MongoDB (rejected — relational model fits our metadata; row_sources is inherently relational), DuckDB for metadata too (rejected — mixing OLAP scan workload with OLTP metadata writes on one engine is the wrong shape).
**Consequences:** Two data stores to operate (PostgreSQL + filesystem). The SDK must keep them consistent: metadata is the source of truth, files are content.

### Use JSONL as the native row format
**Date:** 2026-06-16
**Status:** Active
**Decision:** Rows are stored as JSONL. Parquet exists only as a generated cache.
**Reasoning:** JSONL keeps the data open and inspectable — users can `cat`, `grep`, and edit files directly without import/export. It is the de facto interchange format for LLM training data.
**Alternatives considered:** Parquet as primary (rejected — binary, hard to inspect/edit, defeats the "users can look at their data" goal), CSV (rejected — no nested structure), a custom format (rejected — no ecosystem benefit).
**Consequences:** JSONL is slower to scan than Parquet; mitigated with field indexes, file_stats pruning, and an auto-generated Parquet cache for hot fields. Registered JSONL files are immutable.

### Use row-level COW (copy-on-write) for versioning
**Date:** 2026-06-16
**Status:** Active (design; implementation is phase 3 — see `context/versioning.md`)
**Decision:** A new dataset version stores only changed rows as delta JSONL; unchanged rows are reused from ancestor versions via the `row_sources` table.
**Reasoning:** Full-copy snapshots would explode disk usage at TB scale across many versions. Row-level COW with a row_sources mapping gives immutable history at near-zero cost for unchanged rows.
**Alternatives considered:** Full snapshot per version (rejected — disk), Git-style content-addressable blocks (rejected — overkill for row granularity), no versioning (rejected — core product value).
**Consequences:** Reading a version may need to union files across ancestors; the SDK hides this behind a UNION ALL view (see `context/query-and-indexing.md`). Tags and field indexes are inherited by logical row index.

### SDK is the only public surface
**Date:** 2026-06-16
**Status:** Active
**Decision:** All features are exposed via the Python SDK. User/notebook code never touches DuckDB or PostgreSQL directly.
**Reasoning:** The two-engine design (DuckDB + PostgreSQL) has subtle invariants — immutability, metadata-as-source-of-truth, COW. Direct access would let users break these invariants. A single SDK surface keeps them enforceable.
**Alternatives considered:** Expose DuckDB and PostgreSQL directly with helper functions (rejected — too easy to violate invariants), build REST-first (rejected — Web is a later phase; SDK-first matches the data-team workflow).
**Consequences:** Internal layers (`engine/`, `meta/`, `versioning/`) are private. Adding features means extending the SDK, not adding parallel entry points.

### MVP cuts at phase 1 (registration + single-user tags + DuckDB scan)
**Date:** 2026-06-16
**Status:** Active
**Decision:** The first runnable slice is dataset registration, row-offset indexing, field inference, single-user tags/notes, and DuckDB direct-scan search. Field indexing, multi-user isolation, versioning/COW, transforms, Parquet cache, REST, and Ray are explicitly later.
**Reasoning:** Phase 1 delivers an end-to-end vertical slice (register → tag → search) that proves the DuckDB+PostgreSQL split works. Each later phase layers on without rewriting the core.
**Alternatives considered:** Build phases 1–3 together (rejected — too long to first runnable slice, harder to validate the core split), REST-first (rejected — SDK-first matches the workflow and validates the engine without a Web layer).
**Consequences:** ROUTER "Not yet built" explicitly lists every phase-2+ item. Patterns seeded in `patterns/` cover phase-1 tasks only; later-phase patterns are added by GROW as those features land.
