# Phase 4 — Parquet Cache

**Scope:** F23 refresh_parquet_cache · F24 list_parquet_caches · F25 auto cache generation (stub) ·
F26 cost-based routing (stub).

**Status:** L1–L8 all green. Dev tag `v0.2.0`.

## What you can do

Phase 4 adds Parquet caching for faster scans:

1. **Manual cache refresh:** create Parquet files for a dataset version
2. **Automatic cache use:** scans use Parquet cache when available
3. **Field-specific caches:** cache specific fields for targeted queries
4. **Fallback to JSONL:** if cache is missing or corrupt, falls back to original JSONL

The Parquet cache is optional: install with `pip install "dreamdata[parquet]"`.

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

# Register dataset
ds = engine.register_dataset("phase4_demo", [Path("conversations.jsonl")])

# Refresh Parquet cache (F23)
cache_info = ds.refresh_parquet_cache()
print(cache_info)
# ParquetCacheInfo(cache_id=1, field_path=None, cache_kind="full", ...)

# List existing caches (F24)
caches = ds.list_parquet_caches()
for cache in caches:
    print(cache.cache_kind, cache.row_count)

# Subsequent scans use Parquet cache automatically (F25/F26)
df = ds.scan()  # fast!
df_filtered = ds.search_by_field("rating", 5)  # also fast when cache available

engine.close()
```

## Worked examples

### Happy path: Parquet cache speeds up scans

```python
import json
import time
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

# 1. Prepare a larger fixture (10k rows)
fixture = Path("/tmp/large_dataset.jsonl")
fixture.write_text("\n".join(json.dumps({
    "id": i,
    "score": i / 10000,
    "text": f"document {i}",
}) for i in range(10000)) + "\n")

# 2. Register dataset
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds = engine.register_dataset("large_demo", [fixture])

# 3. First scan (JSONL, slower)
start = time.time()
df1 = ds.scan()
jsonl_time = time.time() - start
print(f"JSONL scan: {jsonl_time:.3f}s")

# 4. Refresh cache
ds.refresh_parquet_cache()

# 5. Second scan (Parquet, faster)
start = time.time()
df2 = ds.scan()
parquet_time = time.time() - start
print(f"Parquet scan: {parquet_time:.3f}s")
print(f"Speedup: {jsonl_time / parquet_time:.1f}x")

# Verify same data
assert len(df1) == len(df2)

engine.close()
```

### Optional dependency: graceful fallback

```python
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

# Works even without pyarrow installed!
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))

# All JSONL functionality works as normal
ds = engine.register_dataset("fallback_demo", [Path("conversations.jsonl")])
df = ds.scan()  # uses JSONL directly
assert len(df) > 0

# Trying to use Parquet features raises helpful error
try:
    ds.refresh_parquet_cache()
except ImportError:
    print("Install pyarrow for Parquet cache: pip install 'dreamdata[parquet]'")

engine.close()
```

## What's deferred to later phases

- **Automatic cache invalidation:** currently doesn't track when versions change
- **Cost-based optimizer:** full query planning (currently just checks if cache exists)
- **FastAPI REST layer:** web interface (Phase 5)
- **Ray execution:** distributed processing (Phase 6, optional)
