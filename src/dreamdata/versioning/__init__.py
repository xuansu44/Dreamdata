"""Versioning and COW (copy-on-write) transforms.

Phase 3: dataset versions, append, map, filter_map.
Phase 4: Parquet caching.
"""

from dreamdata.versioning.core import (
    VersionedRowSource,
    VersionManager,
    VersionMeta,
)

__all__ = [
    "VersionManager",
    "VersionMeta",
    "VersionedRowSource",
]
