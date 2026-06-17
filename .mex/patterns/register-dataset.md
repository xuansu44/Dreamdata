---
name: register-dataset
description: Register a new dataset — scan JSONL, record row offsets in row_sources, infer fields, compute file_stats, insert metadata into PostgreSQL. The first end-to-end flow in the engine.
triggers:
  - "register"
  - "new dataset"
  - "ingest"
  - "import jsonl"
edges:
  - target: context/metadata-schema.md
    condition: when the table shapes being written are needed
  - target: context/versioning.md
    condition: registration creates the initial version v1
  - target: patterns/add-sdk-method.md
    condition: register is itself an SDK method — follow the SDK-method conventions
last_updated: 2026-06-16
---

# Register a Dataset

## Context

MVP scope. Load `context/metadata-schema.md` for the table shapes and `context/versioning.md` for the version model (registration produces version v1). The user supplies one or more JSONL file paths; the engine produces a `datasets` row, a `dataset_versions` row (v1), one `row_sources` row per JSONL line, and `file_stats` rows per (file, detected field).

## Steps

1. **Validate inputs.** Each path exists, is readable, ends in `.jsonl` (or is explicitly overridden). Reject empty file lists with a typed exception.
2. **Stage files into the workspace.** Copy or hard-link the files into `$WORKSPACE_PATH/<dataset_name>/v1/data/`. Store paths **relative to `WORKSPACE_PATH`** in metadata. [VERIFY AFTER FIRST IMPLEMENTATION — copy vs hard-link vs symlink decision and its impact on immutability.]
3. **Scan and index offsets.** Stream each file line by line. For each line, record `(row_idx, file_path, byte_offset, byte_length)` into a buffer for `row_sources`. Validate that each line is valid JSON; collect malformed lines and either skip-with-warning or abort based on policy. [VERIFY AFTER FIRST IMPLEMENTATION — malformed-line policy.]
4. **Infer fields.** Sample the first N lines (e.g. 100) per file, walk the JSON structure, and collect all dotted field paths (with numeric indices for arrays). Store the union in `datasets.inferred_fields` as jsonb.
5. **Compute file_stats.** For each file and each top-level inferred field, compute min/max over the file. Write to `file_stats`. (Phase 1 may compute stats only for top-level scalar fields; nested stats arrive with indexing in phase 2.) [VERIFY AFTER FIRST IMPLEMENTATION — which fields get stats in phase 1.]
6. **Insert metadata in one transaction.** Within a single PostgreSQL transaction: insert `datasets`, insert `dataset_versions` (v1, `parent_version_id = null`), bulk-insert `row_sources`, bulk-insert `file_stats`, set `datasets.current_version_id`. Commit.
7. **Return** a `Dataset` handle bound to the new version.

## Gotchas

- **Paths must be relative to `WORKSPACE_PATH`.** Absolute paths break workspace portability and the future object-storage migration.
- **Bulk-insert `row_sources`.** A large JSONL file produces one row per line — use `COPY` or batched inserts, not per-row `INSERT`.
- **Encoding.** Assume UTF-8; reject or transcoded-replace other encodings explicitly. Don't silently mis-read.
- **Mixed schemas across files.** Field inference unions across files; downstream scans must tolerate absent fields. [VERIFY AFTER FIRST IMPLEMENTATION — record the actual DuckDB behaviour.]
- **Partial failure.** If the transaction fails after files are staged, the staged files become orphaned. Decide cleanup policy (delete on rollback, or leave for GC). [VERIFY AFTER FIRST IMPLEMENTATION.]
- **Re-registering an existing name.** Reject with a typed exception unless an explicit `overwrite` flag is set; never silently replace.

## Verify

Before claiming registration is done:
- [ ] `datasets`, `dataset_versions`, `row_sources`, `file_stats` rows all inserted in one transaction.
- [ ] `row_sources` row count matches the line count of every staged file.
- [ ] All paths in metadata are relative to `WORKSPACE_PATH`.
- [ ] `datasets.inferred_fields` is non-empty for non-empty files.
- [ ] No raw SQL outside `meta/`; no DuckDB writes.
- [ ] A follow-up `ds.search({})` returns the expected row count.

## Debug

- **Row count mismatch:** compare `wc -l <file>` against `row_sources` count for that file. Re-scan with logging to find the line where the offset drift starts (usually a malformed line or a UTF-8 boundary issue).
- **Field inference missing nested paths:** raise the sample size; check that array indices are walked (`messages.0.role`, not just `messages`).
- **Transaction commits but files missing on disk:** check the staging step — copy/hard-link may have failed silently; add a post-stage existence check.
- **`search({})` returns 0 rows after a successful register:** DuckDB glob does not match the staged path; check the relative-path logic and DuckDB's `read_json_auto` working directory.

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if registration moved from not-built to working.
- [ ] Update `context/metadata-schema.md` with concrete column types and bulk-insert strategy after the first implementation.
- [ ] If a new gotcha surfaced, add it to this pattern's Gotchas section.
