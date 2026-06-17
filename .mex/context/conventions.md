---
name: conventions
description: How code is written in this project — naming, structure, patterns, and style. Load when writing new code or reviewing existing code.
triggers:
  - "convention"
  - "pattern"
  - "naming"
  - "style"
  - "how should I"
  - "what's the right way"
edges:
  - target: context/architecture.md
    condition: when a convention depends on understanding the system structure
  - target: context/testing.md
    condition: when applying conventions to test code or designing coverage
  - target: context/process.md
    condition: when applying conventions to PR / CI / release workflow
  - target: context/stack.md
    condition: when a convention depends on a specific library choice
  - target: patterns/add-sdk-method.md
    condition: when adding a new SDK method and applying the conventions concretely
last_updated: 2026-06-17
---

# Conventions

## Naming

- **Python modules/packages**: `snake_case` (e.g., `dataset.py`, `version_manager.py`).
- **Classes**: `PascalCase` (e.g., `Engine`, `Dataset`, `VersionManager`).
- **Functions/methods**: `snake_case`, verb-first (e.g., `register_dataset`, `search`, `tag_rows`).
- **PostgreSQL tables**: `snake_case`, plural (e.g., `datasets`, `dataset_versions`, `row_sources`, `user_annotations`, `field_index`, `file_stats`).
- **PostgreSQL columns**: `snake_case` (e.g., `version_id`, `row_idx`, `byte_offset`, `created_at`).
- **Field paths** (for query/index): dotted with numeric indices for arrays (e.g., `messages.0.role`, `metadata.source`).

## Structure

- **`src/dreamdata/`** is the package layout (src-layout via uv). Package name `dreamdata` confirmed 2026-06-17 — matches scaffold name, no conflict with existing PyPI packages of `dataengine`.
- **Public SDK surface** lives in `dreamdata/sdk.py` (or `dreamdata/api/`): `Engine`, `Dataset`. Everything else is internal.
- **Internal layers** — `engine/` (DuckDB wrapper), `meta/` (PostgreSQL repository), `storage/` (workspace + JSONL I/O), `versioning/` (later). Each layer has one responsibility.
- **No business logic in the SDK facade** — the facade delegates to internal layers; it only orchestrates and shapes return values.
- **All PostgreSQL access goes through `meta/`** — no raw SQL outside the repository layer.
- **Tests live under `tests/`** mirrored to source layout (e.g., `tests/sdk/test_register.py`, `tests/meta/test_row_sources.py`).

## Patterns

**SDK method coordinates DuckDB + PostgreSQL, returns DataFrame or new handle:**
```python
# Correct — facade delegates, returns DataFrame
def search(self, filters: dict) -> "pandas.DataFrame":
    candidate_rows = self._meta.resolve_rows(self.version_id, filters)
    return self._engine.scan(self._row_sources_for(candidate_rows), filters)

# Wrong — leaks DuckDB to the facade, bypasses the engine layer
def search(self, filters):
    return self._duckdb.execute("SELECT * FROM read_json_auto(...)")
```

**Immutable operations — transforms return a new handle:**
```python
# Correct
def map(self, func) -> "Dataset":
    new_version = self._versioning.apply_map(self.version_id, func)
    return Dataset(self._engine_ref, new_version)

# Wrong — mutating self.version_id in place
```

**Typed exceptions with context, no silent failures:**
```python
# Correct
raise DatasetNotFound(name=name)
raise FieldPathInvalid(path="messages.0.role", reason="array index on non-list field")

# Wrong
return None  # caller has to guess
```

## Git Workflow

**Branch naming:**
- Feature work: `feat/F<n>-<short-slug>` (e.g., `feat/F3-tag-rows`)
- Bug fixes: `fix/<short-slug>`
- Docs: `docs/<short-slug>`
- Refactors with no behavior change: `refactor/<short-slug>`
- Chores (deps, CI, configs): `chore/<short-slug>`

**Commit messages:** Conventional Commits, single-line subject + optional body.
- Allowed types: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `perf:`, `chore:`
- Subject ≤ 72 chars, imperative mood ("add", not "added")
- Scope optional: `feat(sdk):`, `fix(meta):`
- Breaking change: append `!` (e.g., `feat(sdk)!:`) and explain in body
- Body answers *why*, not *what*

**Pull requests:**
- One PR per logical change. F-features may bundle related sub-features (e.g., F3 + F4 if both touch annotations).
- Squash-and-merge to main. PR title becomes the squash commit subject.
- PR template (`.github/pull_request_template.md`): summary, test plan, breaking changes, docs updated.
- `main` is protected: no direct pushes, CI must be green.
- Tagging: `v0.0.x` dev tag after each phase boundary; `v0.1.0` after Phase 2 — see `context/process.md`.

## Error Hierarchy

Root abstract class `DreamdataError`; layer-specific subclasses carry named context fields (no positional args, no stringly-typed errors).

```
DreamdataError                    # abstract root, never raised directly
├── SdkError                      # public SDK surface — user-visible
│   ├── DatasetNotFound(name)
│   ├── DatasetAlreadyExists(name)
│   ├── FieldPathInvalid(path, reason)
│   ├── TagValueInvalid(value, reason)
│   └── FilterInvalid(filter, reason)
├── MetaError                     # PostgreSQL layer — operational
│   ├── MetadataWriteFailed(table, reason)
│   └── MetadataConstraintViolation(constraint, detail)
├── EngineError                   # DuckDB layer — operational
│   ├── ScanFailed(file, reason)
│   └── EngineResourceExhausted(resource, limit)
└── StorageError                  # filesystem layer — operational
    ├── FileNotReadable(path, reason)
    ├── FileNotWritable(path, reason)
    └── WorkspaceMisconfigured(setting, expected)
```

**Rules:**
- Every `raise` passes named kwargs matching the exception's documented fields.
- Public SDK raises `SdkError` subclasses only — internal `MetaError`/`EngineError`/`StorageError` are caught at the SDK boundary and either re-raised as the closest matching `SdkError` (preserving the original via `__cause__`) or allowed to propagate during clearly-internal failures.
- No bare `except Exception:`; no `except: pass`; no `return None` on failure.
- `__str__` includes the context fields, never includes secrets (`DATABASE_URL`, raw user data).

## Logging

**Library:** stdlib `logging` + `structlog` for key-value structured output.

**Correlation:** every public SDK call generates a `correlation_id` (uuid4 hex) and binds it to the structlog context for the duration of the call. Internal layers log with the same `correlation_id` automatically.

**Levels:**
- `DEBUG` — SQL text, DuckDB scan plans, file offsets read
- `INFO` — lifecycle events (dataset registered, version created, index built)
- `WARNING` — degraded mode (parquet cache miss, fell back to JSONL scan), slow query (> 1s)
- `ERROR` — operation failed but process can continue
- `CRITICAL` — invariant violation (e.g., `row_sources` count != file line count mid-write)

**Forbidden:**
- `print()` anywhere in `src/`
- Logging `DATABASE_URL`, `USER_ID`, raw row content, or full exception tracebacks that include these
- `logging.getLogger(__name__)` repeated in hot paths — cache as module-level `_log = structlog.get_logger()`

**Format:** JSON in CI/production (`structlog.processors.JSONRenderer`), pretty console in dev (`structlog.dev.ConsoleRenderer`).

## Configuration

**Library:** `pydantic-settings` (`BaseSettings` subclass `dreamdata.config.Settings`).

**Single source of truth:** one `Settings` instance, loaded from `.env` at engine construction. Env vars map 1:1 to settings fields (see `context/setup.md` for the canonical list).

**Rules:**
- No `os.getenv(...)` calls outside `config.py`. New config goes through `Settings`.
- The `Settings` instance is **injected** into `Engine(config: Settings)`, never imported as a module-level singleton. Tests construct `Settings(...)` with overrides.
- Secrets (`DATABASE_URL`) are `SecretStr` in pydantic; their `repr` is masked.
- Validation failures raise a typed `SettingsInvalid` (subclass of `SdkError`) at construction time with all field errors listed, not one at a time.

## Type Hints

- **Public SDK surface (`sdk.py`):** `mypy --strict` — no untyped defs, no implicit `Any`, no `Optional` without explicit `| None`.
- **Internal layers (`engine/`, `meta/`, `storage/`, `versioning/`):** `mypy --check-untyped-defs --disallow-untyped-defs` — defs must be typed, but `Any` is allowed where DuckDB/pandas APIs demand it.
- **Tests:** not type-checked (pytest collection dynamics make it noisy). Lint-only.
- No `# type: ignore` without a code (`# type: ignore[code]`) and a one-line reason.

## Comments

- **Default: no comments.** Well-named identifiers and tests explain *what*.
- **Write a comment only when:**
  - A non-obvious invariant must hold (and a test doesn't already pin it)
  - Working around a bug in a dependency (link the issue/PR + version: `# duckdb#1234 in v0.9.2`)
  - Behavior would surprise a reader (e.g., "we delete then re-insert to avoid an FK cascade")
- **One line preferred.** Multi-line comments only when a paragraph is genuinely necessary; never write multi-paragraph docstrings inside functions.
- **Never reference the current task or PR** ("added for F3", "TODO after phase 2") — that belongs in commit messages and ROUTER, not in code.

## Dependency Management

- All runtime deps in `pyproject.toml` `[project.dependencies]` with both lower bound and upper bound (e.g., `"pydantic>=2.5,<3"`).
- Dev/test deps in `[project.optional-dependencies.dev]`.
- **Adding a new dependency requires a `decisions.md` entry** with: what it does, why existing deps can't cover it, alternatives considered. The decision ships in the same PR as the dep.
- `uv.lock` is committed; CI verifies lockfile is up to date.
- `uv pip audit` runs in CI on every PR; new advisories fail the build.
- No pinning to a git commit unless the upstream release is broken and we can't wait — and if we do, an issue is filed to unpin.

## Documentation

Per-phase SDK documentation is mandatory (see `context/decisions.md` — "Per-phase Python SDK documentation is mandatory"). A phase is not done until its docs are written.

**Layout** (`docs/` at project root, Sphinx + autodoc):

```
docs/
├── source/
│   ├── conf.py                       # Sphinx config, autodoc enabled
│   ├── index.md                      # landing
│   ├── quickstart.md                 # updated whenever the user-facing flow changes
│   ├── installation.md               # uv / DATABASE_URL / WORKSPACE_PATH setup
│   ├── api/                          # auto-generated from SDK docstrings
│   │   ├── engine.md
│   │   └── dataset.md
│   └── phases/
│       ├── phase-1.md                # what's new + worked examples for F1–F10
│       ├── phase-2.md                # added when Phase 2 lands
│       └── ...
└── Makefile                          # `make html` → uv run sphinx-build
```

**Docstring style:** Google style on all public SDK methods (`Engine`, `Dataset`). Internal layers (`engine/`, `meta/`, `storage/`, `versioning/`) need docstrings only on non-obvious public-ish functions; private helpers do not.

**Per-phase docs requirements:**
1. `docs/source/phases/phase-N.md` exists and covers: what user-visible features the phase adds, at least two worked examples (one happy-path, one error-path), and a "what's deferred" section pointing to later phases.
2. `docs/source/quickstart.md` updated if the recommended first-run flow changed.
3. API reference auto-generated from docstrings covers every public SDK method added in this phase.
4. `uv run sphinx-build docs/source docs/build` exits clean (added to CI gates from Phase 1).

## Verify Checklist

Before presenting any code:
- [ ] Public SDK methods carry full type hints and Google-style docstrings.
- [ ] No business logic in the SDK facade — it delegates to internal layers.
- [ ] No raw SQL outside `meta/`; no DuckDB calls outside `engine/`.
- [ ] Read-path methods return `pandas.DataFrame`; transforms return new `Dataset` handles.
- [ ] Errors are typed exceptions with context — no `None`-on-failure, no swallowed exceptions.
- [ ] PostgreSQL table/column names match `context/metadata-schema.md`.
- [ ] No writes to original JSONL files; transforms write delta files only.
- [ ] DuckDB is used read-only for business data.
- [ ] Each public SDK method has an L4 property test (Hypothesis) and at least one L5 fuzz case — see `context/testing.md`.
- [ ] No mocks of PostgreSQL / DuckDB / filesystem in L2 component tests or above.
- [ ] Tests assert the architectural invariants (immutability, metadata-as-source-of-truth, DuckDB read-only), not just functional correctness.
- [ ] **Phase docs written** — `docs/source/phases/phase-N.md` covers new SDK methods; quickstart updated if flow changed; `sphinx-build` exits clean.
