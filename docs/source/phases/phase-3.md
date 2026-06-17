# Phase 3 — Versioning (Copy-on-Write)

**Scope:** F16 list_versions · F17 get_version · F18 append · F19 map · F20 filter_map ·
F21 overwrite creates new version · F22 tag/index inheritance.

**Status:** L1–L8 all green. Dev tag `v0.2.0`.

## What you can do

Phase 3 adds versioning to datasets:

1. **Append-only mutations:** every change creates a new version
2. **Copy-on-Write (COW):** unchanged rows are inherited from parent versions
3. **Tag/annotation inheritance:** tags and notes follow rows when inherited
4. **Functional transforms:** use `map` and `filter_map` to create new versions

The full API surface is documented in the
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

# Register initial version (v1)
ds_v1 = engine.register_dataset("phase3_demo", [Path("conversations.jsonl")])
ds_v1.tag(0, "important")

# Overwrite creates new version (v2) instead of deleting
ds_v2 = engine.register_dataset("phase3_demo", [Path("conversations_v2.jsonl")], overwrite=True)

# List all versions
versions = engine.list_versions("phase3_demo")
for v in versions:
    print(v.version_number, v.row_count)

# Open a historical version (read-only)
ds_historical = engine.open_dataset("phase3_demo", version_number=1)

# Append new rows (creates v3)
ds_v3 = ds_v2.append([Path("more_conversations.jsonl")])

# Transform rows with map (creates v4)
def add_metadata(row):
    row["processed_at"] = "2026-06-17"
    return row
ds_v4 = ds_v3.map(add_metadata)

# Filter and transform rows with filter_map (creates v5)
def keep_high_quality(row):
    if row.get("rating", 0) >= 4:
        row["is_high_quality"] = True
        return row
    return None  # excluded from new version
ds_v5 = ds_v4.filter_map(keep_high_quality)

engine.close()
```

## Worked examples

### Happy path: append and map

```python
import json
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

# 1. Prepare fixtures
fixture_v1 = Path("/tmp/phase3_v1.jsonl")
fixture_v1.write_text("\n".join(json.dumps({
    "id": i,
    "text": f"message {i}",
}) for i in range(10)) + "\n")

fixture_append = Path("/tmp/phase3_append.jsonl")
fixture_append.write_text("\n".join(json.dumps({
    "id": i,
    "text": f"new message {i}",
}) for i in range(10, 20)) + "\n")

# 2. Register initial version
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds_v1 = engine.register_dataset("demo_append", [fixture_v1])
assert ds_v1.version_number == 1
assert ds_v1.row_count == 10

# 3. Append new rows (creates v2)
ds_v2 = ds_v1.append([fixture_append])
assert ds_v2.version_number == 2
assert ds_v2.row_count == 20

# 4. Transform with map (creates v3)
def add_prefix(row):
    row["text"] = f"[processed] {row['text']}"
    return row
ds_v3 = ds_v2.map(add_prefix)
assert ds_v3.version_number == 3
assert ds_v3.row_count == 20

# Verify transformation worked
df = ds_v3.scan(limit=5)
for _, row in df.iterrows():
    assert "[processed]" in row["data"]["text"]

engine.close()
```

### Overwrite creates new version

```python
import json
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))

# Register v1
fixture_v1 = Path("/tmp/overwrite_v1.jsonl")
fixture_v1.write_text("\n".join(json.dumps({"id": i}) for i in range(5)) + "\n")
ds_v1 = engine.register_dataset("demo_overwrite", [fixture_v1])
ds_v1.tag(0, "remember_me")

# Overwrite creates v2 (history preserved)
fixture_v2 = Path("/tmp/overwrite_v2.jsonl")
fixture_v2.write_text("\n".join(json.dumps({"id": i}) for i in range(10)) + "\n")
ds_v2 = engine.register_dataset("demo_overwrite", [fixture_v2], overwrite=True)
assert ds_v2.version_number == 2

# List versions shows both v1 and v2
versions = engine.list_versions("demo_overwrite")
assert len(versions) == 2

# v1 still accessible
ds_historical = engine.open_dataset("demo_overwrite", version_number=1)
assert ds_historical.row_count == 5
assert ds_historical.tags() == [(0, "remember_me")]

engine.close()
```

## What's deferred to later phases

- **Automatic Parquet cache generation:** currently manual via `refresh_parquet_cache` (Phase 4)
- **Cost-based query routing:** full optimization (Phase 4)
- **FastAPI REST layer:** web interface (Phase 5)
- **Ray execution:** distributed processing (Phase 6, optional)
