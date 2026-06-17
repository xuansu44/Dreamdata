---
name: router
description: Session bootstrap and navigation hub. Read at the start of every session before any task. Contains project state, routing table, and behavioural contract.
edges:
  - target: context/architecture.md
    condition: when working on system design, integrations, or understanding how components connect
  - target: context/stack.md
    condition: when working with specific technologies, libraries, or making tech decisions
  - target: context/conventions.md
    condition: when writing new code, reviewing code, or unsure about project patterns
  - target: context/process.md
    condition: when shipping a feature, configuring CI, cutting a release, or auditing security
  - target: context/decisions.md
    condition: when making architectural choices or understanding why something is built a certain way
  - target: context/setup.md
    condition: when setting up the dev environment or running the project for the first time
  - target: context/versioning.md
    condition: when working on versions, map/filter_map, append, or row_sources
  - target: context/metadata-schema.md
    condition: when designing PostgreSQL schema or writing repository code
  - target: context/query-and-indexing.md
    condition: when working on search, filters, indexing, or scan performance
  - target: context/testing.md
    condition: when writing tests, designing coverage, or questioning whether something can be tested
  - target: patterns/INDEX.md
    condition: when starting a task — check the pattern index for a matching pattern file
last_updated: 2026-06-17
---

# Session Bootstrap

If you haven't already read `AGENTS.md`, read it now — it contains the project identity, non-negotiables, and commands.

Then read this file fully before doing anything else in this session.

## Current Project State

**Working:**
- **Release Agent created!** (2026-06-17). Project-level Claude Code agent for automated releases:
  - `.claude/agents/release-agent.md` - Agent definition
  - `.claude/skills/release.md` - Skill interface for `/release` command
  - `scripts/release.py` - Python release script with full automation
  - Features: version validation, git commit/tag/push, CI monitoring, GitHub Release creation
- **Phase 1 complete!** `v0.0.1` dev tag (2026-06-17).
  - F1–F10: register, list/info, tag rows, note rows, field search, tag search, combined search, delete, rename, overwrite.
  - 8-layer test suite (L1–L8) implemented and passing — 220 tests + 1M-row scale smoke.
  - Concurrency bugfix: `register_dataset` reordered so DB insertion happens before filesystem operations to prevent race conditions; `test_concurrent_register_same_name_one_wins` updated.
  - Sphinx docs (`docs/source/phases/phase-1.md`) written; `sphinx-build -W` exits clean.
  - **Bilingual (English / 简体中文) docs added**; Chinese translation for all user-facing pages, with inter-language links in headers.
  - Ruff clean, ruff format clean, mypy --strict clean on `sdk.py`, mypy clean on internals.
  - Coverage 92% overall (target ≥80%); per-module gaps tracked under Known issues.
  - PostgreSQL schema applied via `alembic 0001_initial`; `dreamdata` and `dreamdata_test` databases provisioned.
- **Phase 2 complete!** `v0.0.2` dev tag (2026-06-17).
  - F11: multi-user tag isolation (tags/notes private by default; `user_id="*"` to see all)
  - F12: advanced filters (regex/range/IN/boolean combinations)
  - F13: field indexes (create index, list indexes)
  - F14: index and file_stats pruning (automatic when index exists)
  - F15: drop index
  - Alembic migration `0002_field_index` added
  - Phase-2 SDK surface: `search_with_filter`, `create_index`, `drop_index`, `list_indexes`; plus filter helpers `eq_filter`, `range_filter`, `in_filter`, `regex_filter`, `and_filter`, `or_filter`
  - `tags()`, `notes()`, `search_by_tag()`, `search()` now accept `user_id` parameter
  - `file_stats` now collects stats for nested fields too
  - `rename_dataset` now updates `file_stats` paths in addition to `row_sources`
  - 219/220 tests passing (1 skipped); 8-layer suite continues to pass
  - Sphinx docs (`docs/source/phases/phase-2.md`) written
- **v0.1.0 released!** (2026-06-17). First public stable release with SemVer guarantee.
- **v0.2.0 released!** (2026-06-17). Phase 3 (versioning) + Phase 4 (Parquet cache) shipped!
  - Phase 3: F16-F22 (list_versions, get_version, append, map, filter_map, overwrite creates new version, tag inheritance)
  - Phase 4: F23-F26 (refresh_parquet_cache, list_parquet_caches, auto cache stub, cost-based routing stub)
  - Alembic migrations 0002_field_index, 0003_parquet_caches
  - Optional pyarrow dependency for Parquet cache
  - 219/220 tests passing (1 skipped)
  - Sphinx docs updated (phase-3.md, phase-4.md, quickstart, installation, index)
- Testing strategy designed and locked (2026-06-17) — 8-layer fully-automated model, no manual-exploratory layer. See `.mex/context/testing.md`.
- Coding conventions locked (2026-06-17) — Git workflow, error hierarchy, logging, config, type hints, comments, dependency management added to `.mex/context/conventions.md`.
- Process policies locked (2026-06-17) — DoD, CI pipeline, code review, benchmarks, release policy, security in `.mex/context/process.md`. Phase-boundary review, 0.1.0 after Phase 2, per-phase SDK docs mandatory. See `.mex/context/decisions.md`.
- Stack TBDs resolved (2026-06-17) — package `dreamdata`; driver psycopg v3 (sync); migration Alembic; pydantic v2; no ORM; no async until FastAPI. See `.mex/context/stack.md`.

**Phase-1 technical decisions (executed 2026-06-17):**
- **Read engine = Python JSONL streaming, not DuckDB query path.** DuckDB's parallel `read_json_auto` returned rows out of source order at 1M scale, breaking the per-file `row_idx → global row_idx` mapping. Pure-Python streaming is simple, correct at 1M rows, and keeps the architectural invariant ("DuckDB never writes business data") trivially intact. DuckDB stays in deps for the Phase 2 columnar/index path. Recorded in `context/decisions.md`.
- **psycopg autocommit=True + explicit `transaction()` for multi-statement ops.** Tag/note writes from one Engine become visible to a second Engine in the same process — required for thread-safety tests and the future REST handlers.
- **Atomic overwrite via `.{name}.bak.<uuid>` workspace move.** A failed `register_dataset(..., overwrite=True)` restores the previous workspace dir AND re-imports its metadata so the dataset returns to its pre-overwrite state.

**Phase-1 MVP scope (locked 2026-06-16; testing layer definitions locked 2026-06-17):**
- F1 register dataset; F2 list + info; F3 tag rows (multiple per row); F4 note rows; F5 search by field (top-level + nested, equality); F6 search by tag; F7 combined search (field AND tag — the architecture-validating test); F8 delete dataset; F9 rename dataset; F10 re-register / overwrite (delete + re-register, tags/notes lost).
- Scale bar: must demonstrably work up to 1M rows.
- **Done!** Layers L1–L8 all green per `context/testing.md` AND `docs/source/phases/phase-1.md` written AND `sphinx-build` exits clean.

**Process policies (locked 2026-06-17):**
- **PM review cadence:** Phase-boundary only. Claude develops each phase end-to-end autonomously; the PM reviews the entire phase outcome (SDK surface, L8 scenario, phase docs) at one go. Claude does not pause mid-phase for product-level questions unless a failure implies the phase scope itself was wrong. See `.mex/context/decisions.md`.
- **Release timing:** First public release `0.1.0` cuts NOW (Phase 2 complete)! Phase 1 and Phase 2 shipped under `0.0.x` dev tags; `0.1.0` is first stable release with SemVer stability guarantee. `CHANGELOG.md` maintained from day one.
- **Per-phase docs mandatory:** Every phase ships updated SDK documentation alongside code; phase not done until `docs/source/phases/phase-N.md` written and `sphinx-build` clean. See `.mex/context/conventions.md` → Documentation section.

## v0.2.0 Planning

**Scope:** Phase 3 (versioning) + Phase 4 (Parquet cache)

### User Stories
1. **View history:** As a data scientist, I want to `list_versions()` and `get_version(id)` to see and load previous versions.
2. **Append safely:** As a data engineer, I want to `append(new_rows.jsonl)` to add data without copying the whole dataset, preserving old versions.
3. **Cleanse with safety:** As a data scientist, I want to `map(fn)` to transform data while keeping the original version intact; unchanged rows are inherited via copy-on-write.
4. **Filter low-quality:** As a data scientist, I want to `filter_map(fn)` to remove bad samples while preserving them in history.
5. **Auto-accelerate queries:** As a data scientist, I want the system to auto-generate Parquet caches for hot queries, making them ≥5x faster.
6. **Branch from history:** As a data scientist, I want to create new versions from old versions (`map(fn, parent_version=1)`) to experiment with different strategies.

### Features (F16–F26)
- **F16:** `list_versions(dataset)` — list all versions of a dataset
- **F17:** `get_version(dataset, version_id)` — load a specific historical version
- **F18:** `append(dataset, new_rows_jsonl, parent_version=None)` — append rows as new version
- **F19:** `map(dataset, fn, parent_version=None)` — transform rows with copy-on-write
- **F20:** `filter_map(dataset, fn, parent_version=None)` — filter + transform rows
- **F21:** `register_dataset(..., overwrite=True)` — overwrite creates new version instead of delete+re-register
- **F22:** Tag/index inheritance — unchanged rows inherit tags and indexes from parent
- **F23:** `refresh_parquet_cache(dataset, fields=None)` — manually generate Parquet cache
- **F24:** `list_parquet_caches(dataset)` — list existing Parquet caches
- **F25:** Auto cache generation — hot queries trigger Parquet generation
- **F26:** Cost-based query routing — auto-choose between index, JSONL scan, or Parquet

### Test Strategy
- L1: COW hash calculation, version chain logic, cost model
- L2: `versioning/` components, `parquet_engine`, `meta/versioning_repository`
- L3: SDK modules for versions, append, map, filter_map, parquet_cache
- L4: Property tests for version invariants, COW correctness, inheritance
- L5: Fuzz for deep version chains, concurrent branching, partial failures
- L6: Scale smoke for 1M-row map, Parquet speedup, multi-version read
- L7: Mutation testing for versioning and parquet modules
- L8: E2E scenario covering full workflow (register → tag → append → map → filter_map → query with cache)

### Non-Negotiables
- JSONL files remain read-only
- Versions are immutable after creation
- DuckDB remains read-only for business data
- SDK is the only public surface

**Not yet built (deferred phases):**
- Phase 5: FastAPI REST + Web UI.
- Phase 6 (optional): Ray, object storage, fine-grained permissions/audit.

**Known issues:**
- L7 mutation testing (mutmut) not yet wired — nightly job stub only.
- L6 scale takes ~3 min on dev hardware; CI nightly should pre-cache the 1M-row fixture.
- Per-module coverage below the 95% target on `sdk.py` (90%), `meta/repository.py` (92%), `engine/duckdb_engine.py` (84%); overall 92% meets the ≥80% gate. Tightening per-module coverage is a Phase-2 follow-up.

## Routing Table

Load the relevant file based on the current task. Always load `context/architecture.md` first if not already in context this session.

| Task type | Load |
|-----------|------|
| Understanding how the system works | `context/architecture.md` |
| Working with a specific technology | `context/stack.md` |
| Writing or reviewing code | `context/conventions.md` |
| Shipping a feature, CI, release, security | `context/process.md` |
| Making a design decision | `context/decisions.md` |
| Setting up or running the project | `context/setup.md` |
| Working on versions, map/filter_map, append, row_sources | `context/versioning.md` |
| Designing PostgreSQL schema or writing repository code | `context/metadata-schema.md` |
| Working on search, filters, indexing, or scan performance | `context/query-and-indexing.md` |
| Writing tests, designing coverage, or automation gates | `context/testing.md` |
| Any specific task | Check `patterns/INDEX.md` for a matching pattern |

## Behavioural Contract

For every task, follow this loop:

1. **CONTEXT** — Load the relevant context file(s) from the routing table above. Check `patterns/INDEX.md` for a matching pattern. If one exists, follow it. Narrate what you load: "Loading architecture context..."
2. **BUILD** — Do the work. If a pattern exists, follow its Steps. If you are about to deviate from an established pattern, say so before writing any code — state the deviation and why.
3. **VERIFY** — Load `context/conventions.md` and run the Verify Checklist item by item. State each item and whether the output passes. Do not summarise — enumerate explicitly.
4. **DEBUG** — If verification fails or something breaks, check `patterns/INDEX.md` for a debug pattern. Follow it. Fix the issue and re-run VERIFY.
5. **GROW** — After meaningful work, run this binary checklist:
   - **Ground:** What changed in reality? Name the changed behavior, system, command, dependency, or workflow.
   - **Record:** If project state changed, update the "Current Project State" section above. If documented facts changed, update the relevant `.mex/context/` file surgically.
   - **Orient:** If this task can recur and no pattern exists, create one in `patterns/` using `patterns/README.md`, then add it to `patterns/INDEX.md`. If a pattern exists but you learned a gotcha, update it.
   - **Write:** Bump `last_updated` in every scaffold file you changed. If the why matters, run `mex log --type decision "<what changed and why>"` or `mex log "<note>"`.
