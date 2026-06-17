---
name: architecture
description: How the major pieces of this project connect and flow. Load when working on system design, integrations, or understanding how components interact.
triggers:
  - "architecture"
  - "system design"
  - "how does X connect to Y"
  - "integration"
  - "flow"
edges:
  - target: context/stack.md
    condition: when specific technology details are needed
  - target: context/decisions.md
    condition: when understanding why the architecture is structured this way
  - target: context/versioning.md
    condition: when working on versions, map/filter_map, or row_sources
  - target: context/metadata-schema.md
    condition: when designing PostgreSQL schema or writing repository code
  - target: context/query-and-indexing.md
    condition: when working on the read path, search, indexing, or scan performance
last_updated: 2026-06-16
---

# Architecture

## System Overview

The user calls the Python SDK (`Engine`, `Dataset`) — the only public surface. On a read, the SDK resolves which logical rows are needed by querying PostgreSQL metadata (`row_sources`, `user_annotations`, `field_index`, `file_stats`), hands the candidate physical locations to DuckDB, and DuckDB scans the JSONL (or Parquet cache) applying filters. Results return to the user as a `pandas.DataFrame`. On a write (register, tag, append, map), the SDK never modifies original JSONL: it inserts metadata into PostgreSQL and, for transforms, writes delta JSONL files that later versions reference via `row_sources`.

```
SDK (Engine / Dataset)
  ├── read path:  resolve candidate rows in PostgreSQL -> DuckDB scans JSONL/Parquet -> DataFrame
  └── write path: insert metadata in PostgreSQL (+ delta JSONL for transforms) -> new version
        |                          |                              |
        v                          v                              v
  Version & Meta Manager     Query Engine (DuckDB)          Storage Layer
  (PostgreSQL)               embedded, read-only            /workspace/<dataset>/<version>/data/*.jsonl
                                                            /workspace/.engine/cache/*.parquet  (later)
```

Two engines, cleanly split: PostgreSQL is the metadata brain (source of truth for what rows exist and where), DuckDB is the read-only analytic executor (source of truth for nothing — it just reads what PostgreSQL tells it to).

## Key Components

- **SDK (`Engine`, `Dataset`)** — the only public surface. Holds PostgreSQL and DuckDB handles plus a `user_id` and `workspace` path. Every user-facing operation starts here. The facade orchestrates and shapes return values; it contains no business logic.
- **Query Engine (DuckDB, embedded, read-only)** — executes scans and filters over JSONL and Parquet. Given candidate physical offsets by the SDK, returns matched rows. Never writes business data. Lives behind the `engine/` internal layer.
- **Version & Meta Manager (PostgreSQL)** — source of truth for all metadata: dataset definitions, version chain, row_sources (logical row → physical file+offset), user_annotations (tags/notes), field_index, file_stats. Lives behind the `meta/` internal layer.
- **Storage Layer (`/workspace`)** — append-only JSONL organised by `dataset/version/data/` with `new_rows/` for deltas. Parquet cache lives under `/workspace/.engine/cache/` (auto-generated, later phase). All paths stored relative to `WORKSPACE_PATH`.
- **Versioning (later phase)** — the COW model that turns transforms into new versions with row_sources inheritance. Lives behind the `versioning/` internal layer. See `context/versioning.md`.

## External Dependencies

- **PostgreSQL 15+** — metadata brain. All structured state lives here. Accessed only through the `meta/` repository layer.
- **DuckDB (embedded)** — analytic query executor. One in-process instance per `Engine`; reads files from the workspace. Read-only for business data.
- **JSONL files** — the immutable source of truth for row content. Registered datasets are never modified in place.
- **Parquet (later phase)** — auto-generated columnar cache for hot fields; transparent to the user.
- **MinIO / S3 (optional, later)** — backend for JSONL/Parquet when scaling beyond a single machine.
- **FastAPI (later)** — REST layer over the SDK for the Web UI.
- **Ray (later)** — distributed executor for map/filter_map at scale.

## What Does NOT Exist Here

- **No Web UI or REST API in MVP** — FastAPI layer is a later phase; MVP is SDK-only.
- **No distributed execution** — Ray integration is a later phase; MVP is single-process.
- **No object storage backend** — MVP reads from the local filesystem only.
- **No field indexing in MVP** — phase 1 uses DuckDB direct scan; the `field_index` table and pruning arrive in phase 2.
- **No versioning / COW in MVP** — phase 1 has a single implicit version per dataset; row_sources inheritance, map/filter_map, and history navigation arrive in phase 3.
- **No multi-user tag isolation in MVP** — phase 1 is single-user; `user_annotations` exists but is not filtered by `user_id`.
- **No fine-grained permissions or audit log** — out of scope for the foreseeable roadmap.
