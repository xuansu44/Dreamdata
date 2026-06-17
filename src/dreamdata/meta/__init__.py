"""Metadata repository — PostgreSQL access for the dreamdata engine.

The repository is the only place raw SQL appears in the codebase. It owns
the connection lifecycle (a single ``psycopg`` connection per ``Engine``)
and exposes typed methods returning dataclass rows.

No DuckDB / filesystem access here — this layer is metadata only.
"""

from dreamdata.meta.connection import MetaConnection
from dreamdata.meta.repository import (
    AnnotationKind,
    AnnotationRow,
    DatasetMeta,
    DatasetVersionMeta,
    FileStatRow,
    MetaRepository,
    RowSourceRow,
)

__all__ = [
    "AnnotationKind",
    "AnnotationRow",
    "DatasetMeta",
    "DatasetVersionMeta",
    "FileStatRow",
    "MetaConnection",
    "MetaRepository",
    "RowSourceRow",
]
