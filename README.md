# dreamdata

A versioned management engine for LLM training data — JSONL-native storage with
multi-user tag isolation, flexible retrieval, functional transforms, and dataset
versioning, scaling to TBs.

**Status:** v0.4.0 stable release. Phases 1-6 are complete: core
registration + tagging + search + multi-user isolation + advanced filters +
field indexing + versioning (COW, append, map/filter_map) + Parquet caching +
REST API + Web UI + **user authentication & permissions (Phase 6)**.
See `.mex/ROUTER.md` for the full project state.

## Install

```bash
pip install dreamdata
```

For development:
```bash
uv sync --extra dev
```

## Quickstart

See `docs/source/quickstart.md` or the online documentation.

## Features (v0.4.0)

- Register datasets from JSONL files (originals untouched)
- Tag and annotate rows (private per-user by default)
- Search by field, tag, or combined
- Advanced filters (regex, range, IN, boolean combinations)
- Field indexes for fast lookups
- Automatic pruning via file_stats + field_index
- **Versioning (Phase 3):** append-only COW versions, map/filter_map transforms
- **Parquet caching (Phase 4):** optional pyarrow-based cache for faster scans
- **User authentication & permissions (Phase 6):** JWT-based auth, API keys, role-based access control (admin, owner, read_write, read_only)
