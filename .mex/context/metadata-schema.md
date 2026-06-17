---
name: metadata-schema
description: The PostgreSQL metadata schema — datasets, dataset_versions, row_sources, user_annotations, field_index, file_stats. Load when designing schema changes, writing repository code, or reasoning about how metadata maps to physical rows.
triggers:
  - "schema"
  - "table"
  - "metadata"
  - "row_sources"
  - "annotation"
  - "index"
  - "file_stats"
  - "dataset_versions"
edges:
  - target: context/architecture.md
    condition: when the high-level role of metadata in the system is needed
  - target: context/versioning.md
    condition: when the row_sources model behind the schema is needed
  - target: context/query-and-indexing.md
    condition: when the index/file_stats tables' role in query pruning is needed
  - target: patterns/register-dataset.md
    condition: registration populates datasets, row_sources, file_stats
last_updated: 2026-06-17
---

# Metadata Schema

**Status:** Target schema documented. MVP implements only the tables marked **MVP**; the rest arrive in later phases. Column lists are the design intent — `[TO BE DETERMINED — populate after first implementation]` flags items to pin during the first repository pass.

## Tables

### `datasets` (MVP)
One row per registered dataset. Top-level handle.
- `id` (PK), `name` (unique), `current_version_id` (FK → dataset_versions), `inferred_fields` (jsonb — field paths detected at registration), `created_at`.
- [TO BE DETERMINED — exact column types and indexes after first migration.]

### `dataset_versions` (MVP — single implicit v1; full versioning in phase 3)
One row per version of a dataset.
- `id` (PK), `dataset_id` (FK), `version_number` (int), `parent_version_id` (FK, nullable), `row_count` (bigint), `created_at`.
- MVP: each dataset has exactly one row here (`version_number = 1`).

### `row_sources` (MVP — self-source only; inheritance in phase 3)
Maps each logical row index in a version to its physical location.
- `id` (PK), `version_id` (FK), `row_idx` (bigint — logical index within the version), `source_version_id` (FK — which version's file holds the bytes; equals `version_id` in MVP), `file_path` (text — relative to `WORKSPACE_PATH`), `byte_offset` (bigint), `byte_length` (int).
- This is the hot table; expect billions of rows at scale. [TO BE DETERMINED — partitioning strategy (by version_id? by dataset_id?) after first benchmark.]

### `user_annotations` (MVP — single-user; isolation in phase 2)
Tags and notes attached to logical rows.
- `id` (PK), `version_id` (FK), `user_id` (text), `row_idx` (bigint), `kind` (enum: tag | note), `value` (text — tag name or note body), `created_at`.
- MVP: `user_id` is populated from `USER_ID` but not filtered on; phase 2 adds the `user_id` filter so each user sees only their own annotations.
- Unique on `(version_id, user_id, row_idx, kind, value)` for tags.

### `field_index` (phase 2 — not in MVP)
Indexed `(field_value, row_idx)` per version for a chosen field.
- `id` (PK), `version_id` (FK), `field_path` (text), `row_idx` (bigint), `value` (jsonb — typed value or null).
- Used for point/range lookups to prune DuckDB scans.

### `file_stats` (MVP)
Per-file statistics for pruning.
- `id` (PK), `version_id` (FK), `file_path` (text), `field_path` (text), `min_value` (jsonb), `max_value` (jsonb), `row_count` (bigint).
- Lets the query engine skip whole files when a filter is outside the file's min/max for a field.

## Relationships

```
datasets 1---* dataset_versions 1---* row_sources
                                1---* user_annotations
                                1---* field_index   (phase 2)
                                1---* file_stats
```

`row_sources.source_version_id` may point at an ancestor version (phase 3); in MVP it always equals `version_id`.

## Conventions

- All tables use surrogate bigint PKs (`id`) plus the natural keys noted above.
- All `*_at` columns are `timestamptz`.
- All paths are stored **relative to `WORKSPACE_PATH`**, never absolute — workspaces must be movable.
- Field paths use dotted notation with numeric array indices (e.g., `messages.0.role`).

## Open design questions

- **Driver choice:** resolved 2026-06-17 — `psycopg` v3 (sync). See `context/stack.md`.
- **Migration tool:** resolved 2026-06-17 — Alembic. See `context/stack.md`.
- **Partitioning of `row_sources` and `field_index` at billion-row scale:** [TO BE DETERMINED — benchmark after first large dataset.]
- **JSON value canonicalisation in `field_index.value`:** [TO BE DETERMINED — pin a canonical form for range comparison.]
