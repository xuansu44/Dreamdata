# Phase 2 — Indexes, Filtering, User Isolation

**Scope:** F11 multi-user tag isolation · F12 advanced filters (regex/range/IN/boolean) ·
F13 create/use field indexes · F14 file_stats pruning · F15 drop indexes.

**Status:** L1–L8 all green. Dev tag `v0.0.2`. The first public release
`0.1.0` cuts now (see [Release timing](../index.md)).

## What you can do

Phase 2 adds three major capabilities:

1. **Multi-user isolation:** tags and notes are private to each user by default
2. **Advanced filtering:** regex, range, IN, and boolean combinations
3. **Indexes:** create indexes on fields to speed up searches with pruning

The full API surface is documented in the
[Engine](../api/engine.md) and [Dataset](../api/dataset.md) reference.

```python
from pathlib import Path
from dreamdata import Engine, range_filter, regex_filter, and_filter
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/abs/path/to/workspace",
    user_id="alice",
))

ds = engine.register_dataset("phase2_demo", [Path("conversations.jsonl")])

# 1. Multi-user isolation
ds.tag(0, "good")  # only visible to "alice"
print(ds.tags())  # alice sees her tags
print(ds.tags(user_id="*"))  # explicitly request all users' tags

# 2. Advanced filters
ds.search_with_filter(range_filter("score", 0.8, 1.0))
ds.search_with_filter(regex_filter("title", "^A"))
ds.search_with_filter(and_filter(
    range_filter("score", 0.8, 1.0),
    regex_filter("title", "^A")
))

# 3. Indexes
ds.create_index("score")  # speeds up future searches on "score"
ds.search_with_filter(range_filter("score", 0.8, 1.0))  # uses index automatically
ds.list_indexes()  # shows "score"
ds.drop_index("score")

engine.close()
```

## Worked examples

### Happy path: indexes and pruning

```python
import json
from pathlib import Path
from dreamdata import Engine, range_filter
from dreamdata.config import Settings

# 1. Prepare a fixture
fixture = Path("/tmp/phase2_demo.jsonl")
fixture.write_text("\n".join(json.dumps({
    "id": i,
    "score": i / 100,  # from 0 to 0.99
}) for i in range(100)) + "\n")

# 2. Register and create index
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds = engine.register_dataset("demo", [fixture])

# Create an index on the "score" field
ds.create_index("score")

# 3. Search with automatic index pruning
results = ds.search_with_filter(range_filter("score", 0.8, 1.0))
assert len(results) == 20  # rows 80-99

engine.close()
```

### Advanced filters: regex and boolean combinations

```python
from dreamdata import (
    Engine,
    eq_filter,
    in_filter,
    regex_filter,
    and_filter,
    or_filter,
)
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))

# Assume we have a dataset with "title" and "category" and "score"
ds = engine.open_dataset("products")

# Regex match
ds.search_with_filter(regex_filter("title", "^iPhone"))

# IN clause
ds.search_with_filter(in_filter("category", ["electronics", "books"]))

# Boolean combinations
ds.search_with_filter(and_filter(
    in_filter("category", ["electronics", "books"]),
    range_filter("score", 4.0, 5.0)
))

engine.close()
```

### Multi-user isolation

```python
from dreamdata import Engine
from dreamdata.config import Settings

# Alice tags some rows
settings = Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
)
engine = Engine(settings)
ds = engine.register_dataset("collab", [Path("data.jsonl")])
ds.tag([0, 1, 2], "alice_picks")
alice_tags = ds.tags()
engine.close()

# Bob can't see Alice's tags by default
settings = Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="bob",
)
engine = Engine(settings)
ds = engine.open_dataset("collab")
assert ds.tags() == []  # Bob sees nothing!

# Bob can add his own tags
ds.tag([3, 4, 5], "bob_picks")
assert len(ds.tags()) == 3

# Explicitly request to see all users' tags
all_tags = ds.tags(user_id="*")  # Alice and Bob's tags
engine.close()
```

### Error path: regex on non-string value

```python
from dreamdata import Engine, regex_filter
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds = engine.open_dataset("demo")

# Regex filter on non-string field is a no-op (no matches)
results = ds.search_with_filter(regex_filter("score", "^0\\.8"))
assert len(results) == 0

engine.close()
```

## What's deferred to later phases

- **Parquet cache:** auto-generated columnar storage for hot fields (Phase 4)
- **Versioning/COW:** true dataset versions with append-only mutations (Phase 3)
- **FastAPI REST layer:** web interface (Phase 5)
- **Ray execution:** distributed processing (Phase 6, optional)
