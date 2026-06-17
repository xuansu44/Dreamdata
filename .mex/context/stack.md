---
name: stack
description: Technology stack, library choices, and the reasoning behind them. Load when working with specific technologies or making decisions about libraries and tools.
triggers:
  - "library"
  - "package"
  - "dependency"
  - "which tool"
  - "technology"
edges:
  - target: context/decisions.md
    condition: when the reasoning behind a tech choice is needed
  - target: context/conventions.md
    condition: when understanding how to use a technology in this codebase
  - target: context/setup.md
    condition: when installing or pinning versions
last_updated: 2026-06-17
---

# Stack

## Core Technologies

- **Python 3.11+** — the SDK is pure Python; type hints required on all public API.
- **DuckDB** — embedded OLAP engine, in-process per `Engine` instance, read-only for business data.
- **PostgreSQL 15+** — metadata store; all structured state (datasets, versions, row_sources, annotations, indexes, file_stats).
- **JSONL** — native row format; registered files are immutable.
- **Parquet (later)** — auto-generated columnar cache for hot fields.
- **uv** — package manager and venv; `pyproject.toml` is the single source of truth.

## Key Libraries

- **duckdb** (Python binding) — query execution. Used only through the `engine/` internal layer; DuckDB connections are never exposed to user code.
- **pandas** — query results are returned as `pandas.DataFrame` to the user.
- **psycopg v3** (sync) — PostgreSQL driver for the `meta/` layer. Decided 2026-06-17 over asyncpg/SQLAlchemy: sync model matches the DuckDB scan flow (also sync); psycopg v3 has first-class type adaptation, prepared statements, and `COPY` for bulk inserts that we need for `row_sources`. SQLAlchemy ORM is rejected for `meta/` because the metadata access pattern is hand-tuned SQL with bulk `COPY` paths where an ORM obscures performance characteristics.
- **pydantic v2** — config + validation. Decided 2026-06-17 over stdlib dataclasses: needed for `Settings` env loading (`pydantic-settings`), secret masking (`SecretStr`), and JSON Schema generation that the later FastAPI layer can reuse. Dataclasses are insufficient for the validation pipeline.
- **pyarrow** — Parquet read/write for the columnar cache (later phase).
- **alembic** — PostgreSQL migration tool. Decided 2026-06-17 over raw SQL/yoyo: Alembic auto-generates migration scaffolds from model changes, supports downgrade paths, and is the de facto standard paired with SQLAlchemy Core (which we use for connection management even without ORM).
- **pytest** — test framework (default; override in `pyproject.toml` if different).
- **pytest-benchmark** — performance benchmark runner for L6.5 (see `context/process.md`).
- **hypothesis** — property-based testing for L4.
- **mutmut** — mutation testing for L7.
- **testcontainers-python** — spins PostgreSQL service for L2 component tests when CI service container is unavailable; L2 may also use the dedicated `dreamdata_test` DB on dev machines.
- **structlog** — structured logging (see `context/conventions.md` → Logging).
- **ruff** — linter and formatter (default).
- **mypy** — type checker; strict on public SDK, less strict on internal layers (see `conventions.md` → Type Hints).
- **sphinx** + `sphinx-autodoc` + `myst-parser` — SDK docs build (see `conventions.md` → Documentation).
- **FastAPI** (later) — REST layer.
- **Ray** (later) — distributed executor for transforms.

## What We Deliberately Do NOT Use

- **No write path through DuckDB** — DuckDB is read-only for business data; writes go through the version manager into delta JSONL files.
- **No metadata in files** — tags, indexes, version chain live in PostgreSQL only; no sidecar JSON/JSONL for metadata.
- **No direct DuckDB/PostgreSQL calls from user/notebook code** — the SDK is the only public surface; engines are private.
- **No ORM** — not for the read path (DuckDB scans JSONL/Parquet directly), not for the metadata path (raw SQL via psycopg v3, with SQLAlchemy Core only for connection plumbing if needed). ORMs obscure the bulk `COPY` and prepared-statement performance characteristics that matter at our scale.
- **No in-place mutation of dataset handles** — operations return new handles pointing at new versions.
- **No async** until the FastAPI layer — the SDK and internal layers are sync. Introducing async earlier would force an `async`-propagation that complicates DuckDB's sync API for no benefit.

## Version Constraints

- Python 3.11+ required (type-hint syntax, match statements).
- DuckDB: pin to the latest stable at first install in `pyproject.toml` (with upper bound on the next minor). `read_json_auto` behavior varies across versions; we lock to keep results reproducible. Unpin only when intentionally upgrading.
- PostgreSQL 15+ (concurrency and performance features).
- pandas: pin upper bound at first query implementation; lock DataFrame return semantics.
- psycopg: `psycopg[binary]>=3.1,<4` (binary distribution for MVP; switch to source build if a deployment target needs it).
- pydantic: `pydantic>=2.5,<3` and `pydantic-settings>=2.1,<3`.
