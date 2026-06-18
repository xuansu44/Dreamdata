# Changelog

All notable changes to dreamdata are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-06-18

### Changed
- Enhanced `local-test-agent` with semantic docs checks and tech debt detection
- Improved `scripts/run_local_tests.py` to use tomllib instead of tomlkit
- Added `planning-release.md` pattern for release planning workflow
- Updated ROUTER.md with v0.3.0 (Phase 5) plan

### Fixed
- Fixed version consistency check in local test runner

## [0.1.0] - 2026-06-17

First public stable release with SemVer stability guarantee. Includes
Phase 1 (core registration + tagging + search) and Phase 2 (multi-user
isolation + advanced filters + field indexing).

### Added (Phase 2)

- **F11** Multi-user tag isolation — `tags()`, `notes()`, `search_by_tag()`
  now accept `user_id` parameter; tags/notes are private by default.
  Use `user_id="*"` to see all users' annotations.
- **F12** Advanced filters — `search_with_filter()` with `eq_filter`,
  `range_filter`, `in_filter`, `regex_filter`, `and_filter`, `or_filter`.
  Backward compatible: `FieldFilter(path, value)` continues to work for
  equality checks.
- **F13** `Dataset.create_index(path)` — create a field index for fast
  lookups; uses PostgreSQL JSONB for type flexibility.
- **F14** Automatic pruning — `file_stats` (collected at registration)
  prunes entire files before scanning; `field_index` prunes to candidate
  `row_idx` when index exists.
- **F15** `Dataset.drop_index(path)`, `Dataset.list_indexes()` — manage
  field indexes.
- **Alembic migration 0002_field_index** — adds `field_index` table and
  JSONB columns to `file_stats`.

### Changed (Phase 2)

- `Dataset.rename_dataset()` now updates `file_stats` paths in addition
  to `row_sources`.
- `file_stats` now collects stats for nested fields.

### Added (Phase 1)

- **F1** `Engine.register_dataset(name, files, *, overwrite=False)` —
  register a dataset from one or more JSONL files. Files are copied
  into the workspace; originals are never modified. Returns a
  `Dataset` handle.
- **F2** `Engine.list_datasets()`, `Engine.open_dataset(name)`,
  `Engine.info(name)` — list registered datasets, open by name, and
  inspect summary metadata.
- **F3** `Dataset.tag(row_idx, tag)`, `Dataset.remove_tag(...)`,
  `Dataset.tags()` — attach/detach multiple tags per row; idempotent
  upsert; NFC normalisation on write.
- **F4** `Dataset.note(row_idx, body)`, `Dataset.notes()` — free-form
  note bodies attached to rows.
- **F5** `Dataset.search_by_field(path, value)` — equality search on
  any dotted field path (top-level or nested, with numeric array
  indices).
- **F6** `Dataset.search_by_tag(tag)` — return all rows carrying the
  tag.
- **F7** `Dataset.search(*, field_path=None, field_value=None,
  tag=None)` — combined field-AND-tag search. Architecture-validating
  invariant: combined result is exactly the intersection of the two
  single-axis searches.
- **F8** `Engine.delete_dataset(name)` — remove a dataset's metadata
  and workspace directory; original JSONL files untouched.
- **F9** `Engine.rename_dataset(old, new)` — rename; tags, notes,
  row_sources, and file paths are migrated atomically.
- **F10** `Engine.register_dataset(..., overwrite=True)` — overwrite
  = delete + re-register. Tags and notes are lost (true version-bump
  overwrite arrives in Phase 3 with COW).
- **Typed exception hierarchy** rooted at `DreamDataError` with
  layer-specific subclasses (`SdkError`, `MetaError`, `EngineError`,
  `StorageError`). Every error carries named context fields; no
  secrets are surfaced in messages.
- **Pydantic-based `Settings`** loaded from environment — single
  source of truth for engine configuration.
- **Alembic-managed PostgreSQL schema** for `datasets`,
  `dataset_versions`, `row_sources`, `user_annotations`, `file_stats`.
- **Python JSONL streaming read engine** (`engine/duckdb_engine.py`)
  with single-pass file iteration that preserves source line order at
  1M+ rows. The `DuckDBEngine` class name is preserved for forward
  compatibility; DuckDB is used for field-index queries in Phase 2.
- **Eight-layer test suite** (L1–L8) per `.mex/context/testing.md` —
  fully automated, no manual-exploratory layer.
- **Sphinx documentation** with autodoc; per-phase guides for Phase 1
  and Phase 2.
- **Bilingual (English / 简体中文) docs** — Chinese translation for all user-facing pages.
- **Concurrency bugfix** for `register_dataset`: database insertion moved before filesystem operations to avoid race conditions.

### Security

- Dataset names are validated against `^[a-zA-Z0-9_-]{1,128}$` at the
  SDK boundary, before any filesystem or SQL use.
- All SQL is parameterised (psycopg v3 `%s`); table and column names
  use `sql.Identifier` from a closed allow-list in `meta/`.
- All filesystem access goes through the `Workspace` path resolver,
  which refuses absolute paths, null bytes, and symlink escapes.
- Tag and note values are length-capped (default 4 KB / 64 KB) and
  NFC-normalised to prevent storage abuse.

### Known limitations

- One implicit version per dataset (`version_number = 1`).
  `map`/`filter_map`/`append` arrive in Phase 3 with COW versioning.
