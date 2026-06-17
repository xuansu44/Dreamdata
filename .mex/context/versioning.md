---
name: versioning
description: The dataset versioning model — immutable versions, row_sources mapping, copy-on-write deltas, tag/index inheritance. Load when working on versions, map/filter_map, append, or how a version resolves to physical rows.
triggers:
  - "version"
  - "COW"
  - "copy on write"
  - "row_sources"
  - "append"
  - "map"
  - "filter_map"
  - "delta"
  - "inheritance"
  - "ancestor"
edges:
  - target: context/architecture.md
    condition: when the high-level system flow is needed
  - target: context/metadata-schema.md
    condition: when the actual table definitions for versions and row_sources are needed
  - target: context/query-and-indexing.md
    condition: when the read-path UNION ALL across ancestors is needed
  - target: context/decisions.md
    condition: when the reasoning behind COW versioning is needed
  - target: patterns/register-dataset.md
    condition: registration creates the initial version v1
last_updated: 2026-06-16
---

# Versioning

**Status:** Design documented. Implementation is phase 3 of the roadmap. The model below is the design intent; concrete gotchas are marked `[TO BE DETERMINED — populate after first implementation]`.

## Model

A **dataset** has one or more **versions**. Every mutation (register, append, map, filter_map) creates a new version. Versions are immutable once published.

Each version is defined by:
1. **Delta JSONL files** — the rows physically written by this version (new/changed rows only).
2. **A `row_sources` mapping** — for every logical row index in this version, points to the physical file and byte offset holding its content. Unchanged rows point back into an ancestor's files; changed/new rows point into this version's delta files.

This is row-level copy-on-write: a version stores only its deltas, and reads transparently union ancestor files.

## How a new version is produced (map/filter_map)

1. Plan parallel chunks over the parent version's logical rows.
2. For each row, fetch its content (via `row_sources`) and apply the user function.
3. Hash the original row and the result row.
4. **Hashes equal → inherit:** the new version's `row_sources` entry copies the parent's entry (same physical location).
5. **Hashes differ → write delta:** append the result row to this version's `new_rows/*.jsonl`, record a new `row_sources` entry pointing at it.
6. **Inherit tags and field indexes:** copy parent `user_annotations` and `field_index` rows for inherited logical indices; for changed indices, re-derive from the new content.

## How a version is read

The SDK resolves the version's `row_sources` into a list of `(file, byte_offset, byte_length)` tuples in logical order. For a full scan, it builds a DuckDB `UNION ALL` view across all referenced files (including ancestor files) and projects logical row order. For a point lookup, it seeks directly to the offset. Transparent to the caller — a version reads like a single file regardless of how many ancestors contribute.

## Key invariants

- Versions are immutable after publication; the only write is during creation.
- A version's `row_sources` is the single source of truth for "what rows does this version contain and where are they".
- Ancestor files are never garbage-collected while any live version references them.
- Tags and indexes attach to `(version_id, row_idx)`; inheritance copies them by logical index when rows are inherited.

## Open design questions

- **Garbage collection of unreferenced ancestor files:** [TO BE DETERMINED — populate after first implementation. Need a reference-count or GC pass that runs after version deletion.]
- **Hash function for COW comparison:** [TO BE DETERMINED — likely sha256 of canonicalised JSON, but canonicalisation rules (key order, whitespace) must be pinned.]
- **Append vs map semantics for `new_rows/` layout:** [TO BE DETERMINED — single file per version vs sharded by row range; affects parallel read.]
- **Concurrent version creation on the same parent:** [TO BE DETERMINED — locking model in PostgreSQL.]
