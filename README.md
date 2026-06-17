# dreamdata

A versioned management engine for LLM training data — JSONL-native storage with
multi-user tag isolation, flexible retrieval, functional transforms, and dataset
versioning, scaling to TBs.

**Status:** v0.1.0 stable release. Phase 1 and Phase 2 are complete: core
registration + tagging + search + multi-user isolation + advanced filters +
field indexing. See `.mex/ROUTER.md` for the full project state.

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

## Features (v0.1.0)

- Register datasets from JSONL files (originals untouched)
- Tag and annotate rows (private per-user by default)
- Search by field, tag, or combined
- Advanced filters (regex, range, IN, boolean combinations)
- Field indexes for fast lookups
- Automatic pruning via file_stats + field_index
