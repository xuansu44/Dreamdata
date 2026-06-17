---
name: query-and-indexing
description: The read path — how DuckDB scans JSONL/Parquet, how field_index and file_stats prune scans, how a version resolves to a UNION ALL view across ancestors. Load when working on search, filters, indexing, or query performance.
triggers:
  - "query"
  - "search"
  - "scan"
  - "index"
  - "pruning"
  - "filter"
  - "duckdb"
  - "predicate"
  - "union all"
edges:
  - target: context/architecture.md
    condition: when the high-level read flow is needed
  - target: context/metadata-schema.md
    condition: when the field_index/file_stats table shapes are needed
  - target: context/versioning.md
    condition: when the version-to-physical-rows resolution behind the UNION ALL view is needed
  - target: patterns/debug-duckdb-scan.md
    condition: when a scan returns wrong results or errors
last_updated: 2026-06-16
---

# Query & Indexing

**Status:** Design documented. MVP uses **direct DuckDB scan only** — no field indexes, no file_stats pruning. Indexing and pruning arrive in phase 2; multi-ancestor UNION ALL arrives with versioning in phase 3.

## Read path (target design)

1. **Resolve candidate rows.** Given a filter, the SDK asks PostgreSQL which logical row indices could match:
   - If the filtered field has a `field_index`, fetch matching `row_idx` from `field_index`.
   - If not, fall back to all rows in the version (full scan).
2. **Prune files.** For each candidate file, check `file_stats`: if the filter's range is outside the file's min/max for that field, skip the file entirely.
3. **Resolve physical locations.** Translate the surviving logical `row_idx` set into `(file, byte_offset, byte_length)` via `row_sources`.
4. **Execute.** Hand the file/offset list to DuckDB:
   - For a full scan: build a `UNION ALL` of `read_json_auto(file)` across all referenced files (including ancestors), project logical row order, apply the filter.
   - For a point lookup: seek to the offset and read the line.
5. **Return** a `pandas.DataFrame`.

## MVP read path (phase 1)

No `field_index`, no `file_stats` pruning. The SDK resolves the version's `row_sources` (all self-sources in MVP) into a file list, hands it to DuckDB as a `read_json_auto` glob/union, applies the filter, and returns the DataFrame. Simple and correct; optimisation comes later.

## Indexing (phase 2)

`ds.create_index(field_path)` scans the version's rows, extracts `(field_value, row_idx)`, writes them to `field_index`, and updates `file_stats` min/max per file. Subsequent filters on that field use the index to shrink the candidate set before DuckDB sees it.

## Filter syntax (target)

Filters support: equality, comparison (`>`, `<`, `>=`, `<=`), regex, `IN`, and boolean composition (`AND`/`OR`). Field paths are dotted with numeric array indices (e.g., `messages.0.role`). [TO BE DETERMINED — exact filter DSL shape (dict vs mini-DSL vs Python predicates) after first design pass.]

## Key invariants

- DuckDB is **read-only** for business data. It never writes rows.
- The SDK never exposes raw DuckDB connections or SQL to user code.
- Pruning is a performance optimisation only — it must never change query results. A pruned scan and an unpruned scan return identical rows.
- The UNION ALL view across ancestors is an internal detail; users see one logical dataset.

## Open design questions

- **Filter DSL shape:** [TO BE DETERMINED — populate after first implementation.]
- **Parquet cache trigger policy:** [TO BE DETERMINED — when does the engine auto-generate Parquet for a hot field? On Nth scan? Manual?]
- **Cost-based choice between index point-lookup and full scan:** [TO BE DETERMINED — needs a small cost model after first benchmarks.]
- **Handling mixed schemas across files in one version:** [TO BE DETERMINED — DuckDB's `read_json_auto` infers per-file; pin the union strategy.]
