"""Parquet cache management (phase 4).

F23: refresh_parquet_cache
F24: list_parquet_caches
F25: auto cache generation (stub for now)
F26: cost-based query routing (stub for now)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

from dreamdata.config import Settings
from dreamdata.engine import FieldFilter, FilterCombination, ScanResult
from dreamdata.meta import MetaConnection, MetaRepository
from dreamdata.storage import Workspace

# Optional pyarrow import
if TYPE_CHECKING:
    import pyarrow as pa
    import pyarrow.parquet as pq
else:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        pa = None
        pq = None


@dataclass(slots=True, frozen=True)
class ParquetCacheInfo:
    """Public info about a Parquet cache."""

    cache_id: int
    field_path: str | None
    cache_file_path: str
    cache_kind: str
    row_count: int
    file_count: int
    created_at: Any
    last_used_at: Any


class ParquetCacheManager:
    """Manages Parquet caches for faster query performance."""

    __slots__ = ("_meta_conn", "_repo", "_settings", "_workspace")

    def __init__(
        self,
        *,
        settings: Settings,
        workspace: Workspace,
        meta_conn: MetaConnection,
        repo: MetaRepository,
    ) -> None:
        self._settings = settings
        self._workspace = workspace
        self._meta_conn = meta_conn
        self._repo = repo

    def refresh_parquet_cache(
        self,
        *,
        version_id: int,
        field_path: str | None = None,
    ) -> ParquetCacheInfo:
        """F23: manually refresh or create a Parquet cache.

        If field_path is None, caches all rows (full-scan cache).
        If field_path is provided, creates a columnar cache for that field.
        """
        if pa is None or pq is None:
            raise ImportError(
                "pyarrow is required for Parquet cache functionality. Install with: pip install 'dreamdata[parquet]'"
            )

        # Get version metadata to find dataset name
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT dv.id, dv.dataset_id, dv.version_number, d.name "
                "FROM dataset_versions dv JOIN datasets d ON dv.dataset_id = d.id WHERE dv.id = %s",
                (version_id,),
            )
            r = cur.fetchone()
        if r is None:
            raise ValueError(f"Version not found: {version_id}")
        dataset_name = r["name"]
        version_number = r["version_number"]

        # Read all rows via row_sources
        row_sources = self._repo.list_row_sources(version_id=version_id)
        if not row_sources:
            raise ValueError("No rows found for version")

        # Group by file
        files: dict[str, list[tuple[int, str, int, int]]] = {}
        for rs in row_sources:
            if rs.file_path not in files:
                files[rs.file_path] = []
            files[rs.file_path].append((rs.row_idx, rs.file_path, rs.byte_offset, rs.byte_length))

        # Read all rows
        all_rows: list[dict[str, Any]] = []
        for file_rel, rs_list in files.items():
            file_abs = self._workspace.to_abs(file_rel)
            with file_abs.open("rb") as fh:
                for row_idx, _, offset, length in rs_list:
                    fh.seek(offset)
                    line_bytes = fh.read(length)
                    line = line_bytes.decode("utf-8")
                    row_data = json.loads(line)
                    # Store with row_idx
                    all_rows.append({"_row_idx": row_idx, "data": row_data})

        # Create DataFrame
        df = pd.DataFrame(all_rows)

        # Write Parquet
        cache_kind = "full" if field_path is None else f"field:{field_path}"
        cache_file_name = f"{uuid.uuid4().hex[:16]}.parquet"
        cache_dir = (
            self._workspace.root / ".engine" / "parquet_cache" / dataset_name / f"v{version_number}"
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file_abs = cache_dir / cache_file_name
        cache_file_rel = self._workspace.to_rel(cache_file_abs)

        # Write with pyarrow
        table = pa.Table.from_pandas(df)
        pq.write_table(table, cache_file_abs, compression="snappy")  # type: ignore[no-untyped-call]

        # Insert into metadata
        cache_id = self._repo.insert_parquet_cache(
            version_id=version_id,
            field_path=field_path,
            cache_file_path=cache_file_rel,
            cache_kind=cache_kind,
            row_count=len(all_rows),
            file_count=len(files),
        )

        return self._get_cache_info(cache_id=cache_id)

    def list_parquet_caches(self, *, version_id: int) -> list[ParquetCacheInfo]:
        """F24: list existing Parquet caches for a version."""
        caches = self._repo.list_parquet_caches(version_id=version_id)
        return [
            ParquetCacheInfo(
                cache_id=c[0],
                field_path=c[1],
                cache_file_path=c[2],
                cache_kind=c[3],
                row_count=c[4],
                file_count=c[5],
                created_at=c[6],
                last_used_at=c[7],
            )
            for c in caches
        ]

    def has_usable_cache(
        self,
        *,
        version_id: int,
        field_filter: FieldFilter | FilterCombination | None,
    ) -> tuple[bool, ParquetCacheInfo | None]:
        """F26 stub: check if we have a usable cache for a query.

        Returns (has_cache, cache_info).
        """
        caches = self.list_parquet_caches(version_id=version_id)
        if not caches:
            return False, None

        # Check for full cache
        for cache in caches:
            if cache.cache_kind == "full":
                return True, cache

        # Check for field-specific caches
        if field_filter is not None:
            field_path = _extract_single_field_path(field_filter)
            if field_path is not None:
                for cache in caches:
                    if cache.field_path == field_path:
                        return True, cache

        return False, None

    def scan_with_cache(
        self,
        *,
        version_id: int,  # noqa: ARG002
        cache_info: ParquetCacheInfo,
        field_filter: FieldFilter | FilterCombination | None = None,
        row_indices: set[int] | None = None,
        limit: int | None = None,
    ) -> ScanResult:
        """Scan using Parquet cache."""
        # Mark cache as used
        self._repo.touch_parquet_cache(cache_id=cache_info.cache_id)

        # Read Parquet
        cache_file_abs = self._workspace.to_abs(cache_info.cache_file_path)
        df = pd.read_parquet(cache_file_abs)

        # Apply row filter first
        if row_indices is not None:
            df = df[df["_row_idx"].isin(row_indices)]

        # Apply field filter
        if field_filter is not None:
            # For now, we just return everything and let the caller filter
            # Real implementation would push filters down
            pass

        # Apply limit
        if limit is not None:
            df = df.head(int(limit))

        # Rename columns to match expected schema (file_idx, row_idx, data)
        # For simplicity, we just set file_idx=0 for all
        out_df = pd.DataFrame(
            {
                "file_idx": 0,
                "row_idx": df["_row_idx"],
                "data": df["data"],
            }
        )
        out_df["file_idx"] = out_df["file_idx"].astype("int64")
        out_df["row_idx"] = out_df["row_idx"].astype("int64")

        return ScanResult(df=out_df, row_count=len(out_df))

    def _get_cache_info(self, *, cache_id: int) -> ParquetCacheInfo:
        caches = self._repo.list_parquet_caches(version_id=0)  # HACK: we need a better way
        # Just scan for the id in any version
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT id, version_id, field_path, cache_file_path, cache_kind, row_count, file_count, created_at, last_used_at "
                "FROM parquet_caches WHERE id = %s",
                (cache_id,),
            )
            r = cur.fetchone()
        if r is None:
            raise ValueError(f"Cache not found: {cache_id}")
        return ParquetCacheInfo(
            cache_id=r["id"],
            field_path=r["field_path"],
            cache_file_path=r["cache_file_path"],
            cache_kind=r["cache_kind"],
            row_count=r["row_count"],
            file_count=r["file_count"],
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
        )


def _extract_single_field_path(filter: FieldFilter | FilterCombination) -> str | None:
    """Extract a single field path from a filter for cache matching."""
    if isinstance(filter, FieldFilter):
        return filter.path
    elif isinstance(filter, FilterCombination):
        if len(filter.filters) == 1:
            return _extract_single_field_path(filter.filters[0])
    return None
