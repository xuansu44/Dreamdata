# Quickstart

A 60-second tour of the dreamdata SDK: register a dataset, tag rows,
note rows, search by field, by tag, and combined — the Phase-1 happy
path.

## Set up

```python
from dreamdata import Engine
from dreamdata.config import Settings

settings = Settings(
    database_url="postgresql://user:password@localhost:5432/dreamdata",
    workspace_path="/abs/path/to/workspace",
    user_id="alice",
)

engine = Engine(settings=settings)
```

In production, `Settings()` loads from environment variables — see
[Installation](installation.md).

## Register a dataset

```python
from pathlib import Path

ds = engine.register_dataset(
    "conversations_v1",
    [Path("data/conversations.jsonl")],
)
print(ds.row_count, ds.inferred_fields[:5])
```

The supplied JSONL files are copied into the workspace under
`<workspace>/conversations_v1/v1/data/`. The originals are never
modified. Every metadata path is stored relative to `WORKSPACE_PATH`.

## Tag and note rows

```python
ds.tag([0, 1, 2], "high_quality")
ds.tag(0, "favorite")
ds.note(0, "best conversation in the set")

print(ds.tags())
# [(0, 'high_quality'), (0, 'favorite'), (1, 'high_quality'), ...]

print(ds.notes())
# [(<id>, 0, 'best conversation in the set')]
```

Tags are idempotent: re-tagging the same `(row, tag)` is a no-op.
Tag values are NFC-normalised on write.

## Search

```python
# F5: search by top-level field
df = ds.search_by_field("rating", 5)

# F5: search by nested field path (messages[0].role)
df = ds.search_by_field("messages.0.role", "user")

# F6: search by tag
df = ds.search_by_tag("high_quality")

# F7: combined search (field AND tag)
df = ds.search(field_path="rating", field_value=5, tag="high_quality")
```

All search methods return a `pandas.DataFrame` with columns
`row_idx` (the global logical row index in this version) and `data`
(the parsed JSON value of the row).

## Lifecycle: rename and overwrite

```python
# F9: rename preserves tags, notes, and data
new_ds = engine.rename_dataset("conversations_v1", "conversations_v2")

# F10/F21: overwrite creates new version (v0.2+); history preserved
# In v0.1.x this was delete + re-register; in v0.2+ it creates v2
fresh = engine.register_dataset(
    "conversations_v2",
    [Path("data/conversations_v2.jsonl")],
    overwrite=True,
)
```

## Versioning (Phase 3)

```python
# F16: list all versions
versions = engine.list_versions("conversations_v2")
print(versions)  # [VersionMeta(version_number=1, ...), VersionMeta(version_number=2, ...)]

# F17: get a specific version
v1 = engine.open_dataset("conversations_v2", version_number=1)
print(v1.row_count)

# F18: append new rows (creates v3)
ds = engine.open_dataset("conversations_v2")
ds_v3 = ds.append([Path("data/more_conversations.jsonl")])

# F19: map/transform rows (creates v4)
def transform(row):
    row["processed"] = True
    return row
ds_v4 = ds_v3.map(transform)

# F20: filter_map rows (filter + transform, creates v5)
def filter_positive(row):
    if row.get("rating", 0) >= 4:
        row["high_quality"] = True
        return row
    return None
ds_v5 = ds_v4.filter_map(filter_positive)
```

## Parquet Cache (Phase 4, optional)

```python
# Install with: pip install "dreamdata[parquet]"

# F23: refresh Parquet cache for faster scans
cache_info = ds.refresh_parquet_cache()
print(cache_info)

# F24: list existing caches
caches = ds.list_parquet_caches()
print(caches)

# F25/F26: subsequent scans use Parquet cache automatically when available
df = ds.scan(limit=100)
```

## Lifecycle: delete

```python
engine.delete_dataset("conversations_v2")
```

Removes the dataset's metadata, its row_sources, annotations, and
file_stats, and deletes the workspace directory. The original JSONL
files you supplied at registration time are not touched.

## Close the engine

```python
engine.close()
```

Or use the context manager:

```python
with Engine(settings=settings) as engine:
    ds = engine.register_dataset("temp", [Path("data/a.jsonl")])
    print(ds.scan())
```
