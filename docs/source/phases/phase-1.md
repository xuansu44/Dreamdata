# Phase 1 — Register, Tag, Search, Lifecycle

**Scope:** F1 register · F2 list+info · F3 tag rows · F4 note rows ·
F5 search by field · F6 search by tag · F7 combined search · F8 delete ·
F9 rename · F10 overwrite.

**Scale bar:** demonstrably works up to 1M rows.

**Status:** L1–L8 all green. Dev tag `v0.0.1`.
**Completed:** Phase 1 shipped, Phase 2 in progress (see [Phase 2](./phase-2.md)).

## What you can do

The Phase 1 SDK is a vertical slice: register a dataset, annotate
rows, search by field or tag or both, then rename, overwrite, or
delete. The full API surface is documented in the
[Engine](../api/engine.md) and [Dataset](../api/dataset.md) reference.

```python
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/abs/path/to/workspace",
    user_id="alice",
))

ds = engine.register_dataset("phase1_demo", [Path("conversations.jsonl")])
ds.tag([0, 1], "good")
ds.note(0, "best row")
print(ds.search_by_field("rating", 5))
print(ds.search_by_tag("good"))
print(ds.search(field_path="rating", field_value=5, tag="good"))
```

## Worked examples

### Happy path: tag, search, combined

```python
import json
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

# 1. Prepare a small JSONL fixture
fixture = Path("/tmp/phase1_demo.jsonl")
fixture.write_text("\n".join(json.dumps({
    "id": i,
    "messages": [{"role": "user" if i % 2 == 0 else "assistant"}],
    "rating": 5 if i % 3 == 0 else 3,
}) for i in range(10)) + "\n")

# 2. Register and tag
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds = engine.register_dataset("demo", [fixture])
ds.tag([0, 3, 6, 9], "top_rated")  # the rows with rating == 5

# 3. Three search modes
field_results = ds.search_by_field("rating", 5)
tag_results = ds.search_by_tag("top_rated")
combined = ds.search(field_path="rating", field_value=5, tag="top_rated")

# The combined result is exactly the intersection
assert set(combined["row_idx"]) == set(field_results["row_idx"]) & set(tag_results["row_idx"])

engine.close()
```

### Error path: invalid dataset name

```python
from dreamdata import Engine
from dreamdata.errors import DatasetNameInvalid

engine = Engine(Settings(...))

# Path traversal, null bytes, slashes, and over-length names all raise
try:
    engine.register_dataset("../escape", [Path("a.jsonl")])
except DatasetNameInvalid as exc:
    print(exc.context)  # {'name': '../escape', 'reason': '...'}
```

The valid dataset name charset is `^[a-zA-Z0-9_-]{1,128}$`. The check
fires at the SDK boundary, before any filesystem or SQL use — so path
traversal (`../etc/passwd`), absolute paths, null bytes, and empty
strings cannot reach either layer.

## Architectural invariants

Phase 1 establishes the invariants the rest of the project depends on.
The test suite asserts these directly — not just functional correctness:

- **JSONL files are read-only.** Registration *copies* user-supplied
  files into the workspace; the originals' SHA-256 and mtime are
  preserved. `tests/sdk/test_register.py::test_register_does_not_modify_original_file`
  pins this.
- **All metadata lives in PostgreSQL.** Tags, notes, row_sources,
  file_stats, and the dataset/version tables are the single source of
  truth for "what exists and where". `tests/component/test_meta.py`
  covers every repository method.
- **DuckDB is read-only for business data.** The in-memory DuckDB
  instance is opened read_only=False so it can register temp views
  for query processing — but no method issues INSERTs into JSONL
  files. `tests/component/test_engine.py::test_engine_writes_no_business_files`
  asserts the workspace file set is unchanged after a scan.
- **The SDK is the only public surface.** `Engine` and `Dataset`
  never expose raw DuckDB connections or SQL. The `engine/`, `meta/`,
  `storage/` layers are private; user code that imports them is
  unsupported and may break across dev tags.
- **Typed exceptions, never `None`-on-failure.** Every public method
  either succeeds or raises an `SdkError` subclass with named context
  fields (`name`, `path`, `reason`, etc.). Secrets (`DATABASE_URL`,
  raw row content) are never in error messages.

## What's deferred

| Feature | Phase |
|---------|-------|
| Field index (`field_index`) for pruning | Phase 2 |
| Multi-user tag isolation (`user_id` filter) | Phase 2 |
| Regex / range / IN / boolean filters | Phase 2 |
| True version-bump overwrite (COW) | Phase 3 |
| `map` / `filter_map` / `append` transforms | Phase 3 |
| `row_sources` inheritance across versions | Phase 3 |
| Parquet cache for hot fields | Phase 4 |
| FastAPI REST + Web UI | Phase 5 |
| Ray distributed execution | Phase 6 (optional) |

## MVP limitations to know about

1. **Tags are visible across users.** Phase 1 stores the `user_id` on
   every annotation but does not filter on it during reads — single-user
   MVP semantics. Phase 2 introduces the filter so each user sees only
   their own tags.
2. **Search is direct DuckDB scan.** No field index, no file_stats
   pruning. A scan of 1M rows is sub-second on commodity hardware; a
   scan of 100M rows is where Phase 2's indexing matters.
3. **Overwrite is delete-then-register.** Phase 1's `overwrite=True`
   replaces the dataset (tags/notes lost). True version-bump overwrite
   that preserves history arrives in Phase 3 with COW.
4. **One implicit version per dataset.** Phase 1 always has
   `version_number = 1`. Map/filter_map/append that create new
   versions arrive in Phase 3.

## Test coverage

Eight layers, every one fully automated. See `.mex/context/testing.md`
for the design.

| Layer | Scope | Path |
|-------|-------|------|
| L1 unit | Pure helpers (field paths, errors, settings, storage) | `tests/unit/` |
| L2 component | One internal layer against real PostgreSQL / DuckDB / filesystem | `tests/component/` |
| L3 SDK integration | One module per F-feature (happy + edge + error) | `tests/sdk/` |
| L4 property | Hypothesis-generated invariants | `tests/property/` |
| L5 fuzz | Adversarial inputs (malformed JSON, path traversal, etc.) | `tests/fuzz/` |
| L6 scale | 1M-row smoke (slow; nightly) | `tests/scale/` |
| L7 mutation | mutmut on `meta/`, `engine/`, `storage/` (nightly) | n/a |
| L8 acceptance | End-to-end register → tag → search → rename → overwrite → delete | `tests/e2e/` |
