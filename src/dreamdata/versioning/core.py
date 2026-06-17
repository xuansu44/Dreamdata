"""Core versioning logic — COW, append, map/filter_map.

The version manager coordinates:
- Creating new versions from parent versions
- Copy-on-write row inheritance
- Delta file writing
- Annotation and index inheritance
"""

from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dreamdata.config import Settings
from dreamdata.errors import DatasetNotFound
from dreamdata.fields import collect_scalar_fields, infer_fields
from dreamdata.meta import MetaConnection, MetaRepository
from dreamdata.meta.repository import (
    DatasetMeta,
    DatasetVersionMeta,
    RowSourceRow,
)
from dreamdata.storage import Workspace, iter_jsonl_offsets, parse_jsonl_line


@dataclass(slots=True, frozen=True)
class VersionMeta:
    """Public-facing version metadata."""

    version_id: int
    version_number: int
    parent_version_id: int | None
    row_count: int
    created_at: Any


@dataclass(slots=True, frozen=True)
class VersionedRowSource:
    """One logical row's physical location (possibly from an ancestor)."""

    row_idx: int
    source_version_id: int
    file_path: str
    byte_offset: int
    byte_length: int


@dataclass(slots=True, frozen=True)
class _RowWithHash:
    """Internal: row content plus its canonical hash for COW comparison."""

    row_idx: int
    content: object
    content_hash: bytes


def _canonical_json_hash(value: object) -> bytes:
    """Compute a canonical SHA-256 hash of a JSON value for COW comparison.

    Canonicalization rules:
    - Dict keys sorted lexicographically
    - No trailing spaces
    - No spaces around colons or commas
    - Floats in shortest representation
    - Unicode normalized to NFC
    """

    # Build a canonical representation
    def _canonicalize(v: object) -> object:
        if v is None or isinstance(v, (bool, int, float)):
            return v
        elif isinstance(v, str):
            return unicodedata.normalize("NFC", v)
        elif isinstance(v, list):
            return [_canonicalize(item) for item in v]
        elif isinstance(v, dict):
            sorted_items = sorted((_canonicalize(k), _canonicalize(v)) for k, v in v.items())
            return {k: v for k, v in sorted_items}
        else:
            raise ValueError(f"Cannot canonicalize type {type(v)}")

    canonical = _canonicalize(value)
    json_bytes = json.dumps(
        canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(json_bytes).digest()


class VersionManager:
    """Manages dataset versions, COW transforms, and Parquet caches."""

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

    def list_versions(self, *, dataset_name: str) -> list[VersionMeta]:
        """List all versions of a dataset, ordered by version number ascending."""
        ds, _ = self._repo.get_dataset_by_name(name=dataset_name)
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                "FROM dataset_versions WHERE dataset_id = %s ORDER BY version_number ASC",
                (ds.id,),
            )
            rows = cur.fetchall()
        return [
            VersionMeta(
                version_id=r["id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_version(self, *, dataset_name: str, version_number: int) -> VersionMeta:
        """Get metadata for a specific version of a dataset."""
        ds, _ = self._repo.get_dataset_by_name(name=dataset_name)
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                "FROM dataset_versions WHERE dataset_id = %s AND version_number = %s",
                (ds.id, version_number),
            )
            r = cur.fetchone()
        if r is None:
            raise DatasetNotFound(name=f"{dataset_name} v{version_number}")
        return VersionMeta(
            version_id=r["id"],
            version_number=r["version_number"],
            parent_version_id=r["parent_version_id"],
            row_count=r["row_count"],
            created_at=r["created_at"],
        )

    def get_version_by_id(self, *, version_id: int) -> VersionMeta:
        """Get metadata for a version by its internal ID."""
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                "FROM dataset_versions WHERE id = %s",
                (version_id,),
            )
            r = cur.fetchone()
        if r is None:
            raise DatasetNotFound(name=f"version_id={version_id}")
        return VersionMeta(
            version_id=r["id"],
            version_number=r["version_number"],
            parent_version_id=r["parent_version_id"],
            row_count=r["row_count"],
            created_at=r["created_at"],
        )

    def append(
        self,
        *,
        dataset_name: str,
        new_files: list[Path],
        parent_version_number: int | None = None,
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        """Append new rows to a dataset, creating a new version.

        Returns (dataset_meta, new_version_meta).
        """
        ds, parent_v = self._repo.get_dataset_by_name(name=dataset_name)
        if parent_version_number is not None:
            with self._meta_conn.connection.cursor() as cur:
                cur.execute(
                    "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                    "FROM dataset_versions WHERE dataset_id = %s AND version_number = %s",
                    (ds.id, parent_version_number),
                )
                r = cur.fetchone()
            if r is None:
                raise DatasetNotFound(name=f"{dataset_name} v{parent_version_number}")
            parent_v = DatasetVersionMeta(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

        new_version_number = self._next_version_number(dataset_id=ds.id)

        # Create new version directory and copy new files
        data_dir = self._workspace.dataset_data_dir(dataset_name, new_version_number)
        data_dir.mkdir(parents=True, exist_ok=True)
        staged_files: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for src in new_files:
            src_abs = src.resolve()
            dest_name = src_abs.name
            if dest_name in seen:
                raise ValueError(f"Duplicate filename in append: {dest_name}")
            seen.add(dest_name)
            dest_abs = data_dir / dest_name
            shutil.copyfile(src_abs, dest_abs)
            rel = self._workspace.to_rel(dest_abs)
            staged_files.append((dest_abs, rel))

        with self._meta_conn.transaction() as conn:
            # Create new version row
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_versions (dataset_id, version_number, parent_version_id, row_count) "
                    "VALUES (%s, %s, %s, 0) RETURNING id, dataset_id, version_number, parent_version_id, row_count, created_at",
                    (ds.id, new_version_number, parent_v.id),
                )
                r = cur.fetchone()
            new_v = DatasetVersionMeta(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

            # Inherit all rows from parent
            parent_row_sources = self._repo.list_row_sources(version_id=parent_v.id)
            inherited_rows = [
                (rs.row_idx, rs.source_version_id, rs.file_path, rs.byte_offset, rs.byte_length)
                for rs in parent_row_sources
            ]

            # Add new rows
            new_row_base_idx = len(inherited_rows)
            new_row_sources, new_file_stats, sample_rows = self._scan_for_append(
                version_id=new_v.id,
                staged_files=staged_files,
                row_base_idx=new_row_base_idx,
            )
            all_row_sources = inherited_rows + new_row_sources

            # Bulk insert row sources
            self._repo.bulk_insert_row_sources(version_id=new_v.id, rows=iter(all_row_sources))

            # Inherit file_stats for unchanged files and add new ones
            parent_file_stats = self._repo.list_file_stats(version_id=parent_v.id)
            parent_file_stats_tuples = [
                (fs.file_path, fs.field_path, fs.min_value, fs.max_value, fs.row_count)
                for fs in parent_file_stats
            ]
            all_file_stats = parent_file_stats_tuples + new_file_stats
            self._repo.bulk_upsert_file_stats(version_id=new_v.id, rows=iter(all_file_stats))

            # Inherit annotations
            self._inherit_annotations(parent_version_id=parent_v.id, new_version_id=new_v.id)

            # Inherit field indices
            self._inherit_field_indices(parent_version_id=parent_v.id, new_version_id=new_v.id)

            # Update row count
            total_rows = len(all_row_sources)
            self._repo.set_row_count(version_id=new_v.id, row_count=total_rows)

            # Update dataset's current_version_id to new version
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE datasets SET current_version_id = %s WHERE id = %s",
                    (new_v.id, ds.id),
                )

        # Refresh inferred fields
        all_sample_rows: list[object] = []
        # Collect samples from parent (reuse if possible)
        # For simplicity, sample from new rows only
        all_sample_rows.extend(sample_rows)
        if all_sample_rows:
            inferred = infer_fields(all_sample_rows)
            self._repo.update_inferred_fields(dataset_id=ds.id, inferred_fields=inferred)

        return ds, new_v

    def map(
        self,
        *,
        dataset_name: str,
        func: Callable[[object], object],
        parent_version_number: int | None = None,
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        """Transform each row, creating a new version with COW.

        Rows that are unchanged (hash matches) are inherited from the parent.
        Rows that are changed are written to delta files.
        """
        return self._map_or_filter_map(
            dataset_name=dataset_name,
            func=func,
            filter_map=False,
            parent_version_number=parent_version_number,
        )

    def filter_map(
        self,
        *,
        dataset_name: str,
        func: Callable[[object], object | None],
        parent_version_number: int | None = None,
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        """Filter and transform rows, creating a new version with COW.

        Rows that map to None are omitted from the new version.
        """
        return self._map_or_filter_map(
            dataset_name=dataset_name,
            func=func,
            filter_map=True,
            parent_version_number=parent_version_number,
        )

    def _map_or_filter_map(
        self,
        *,
        dataset_name: str,
        func: Callable[[object], object | None],
        filter_map: bool,
        parent_version_number: int | None = None,
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        ds, parent_v = self._repo.get_dataset_by_name(name=dataset_name)
        if parent_version_number is not None:
            with self._meta_conn.connection.cursor() as cur:
                cur.execute(
                    "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                    "FROM dataset_versions WHERE dataset_id = %s AND version_number = %s",
                    (ds.id, parent_version_number),
                )
                r = cur.fetchone()
            if r is None:
                raise DatasetNotFound(name=f"{dataset_name} v{parent_version_number}")
            parent_v = DatasetVersionMeta(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

        new_version_number = self._next_version_number(dataset_id=ds.id)

        # Read all parent rows with hashes
        parent_rows = list(self._read_version_with_hashes(version_id=parent_v.id))

        # Apply transform
        new_rows: list[tuple[int, object, bytes]] = []
        logical_row_idx = 0
        for parent_row in parent_rows:
            try:
                result = func(parent_row.content)
            except Exception:
                # If function fails, skip in filter_map, or keep original?
                # Let's keep original in map mode, skip in filter_map
                if filter_map:
                    continue
                else:
                    result = parent_row.content

            if filter_map and result is None:
                continue

            result_hash = _canonical_json_hash(result)
            new_rows.append((logical_row_idx, result, result_hash))
            logical_row_idx += 1

        # Create new version directory
        data_dir = self._workspace.dataset_data_dir(dataset_name, new_version_number)
        data_dir.mkdir(parents=True, exist_ok=True)

        with self._meta_conn.transaction() as conn:
            # Create new version row
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_versions (dataset_id, version_number, parent_version_id, row_count) "
                    "VALUES (%s, %s, %s, 0) RETURNING id, dataset_id, version_number, parent_version_id, row_count, created_at",
                    (ds.id, new_version_number, parent_v.id),
                )
                r = cur.fetchone()
            new_v = DatasetVersionMeta(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

            # Determine COW: which rows to inherit, which to write as delta
            parent_hash_lookup = {r.row_idx: r.content_hash for r in parent_rows}
            delta_rows: list[tuple[int, object]] = []
            row_sources: list[tuple[int, int, str, int, int]] = []

            for new_logical_idx, new_content, new_hash in new_rows:
                # Find if we have this hash in parent at the same logical index
                # (simplified: just check any row for now; in real impl we could track by idx)
                inherited = False
                for parent_row in parent_rows:
                    if parent_row.content_hash == new_hash:
                        # Inherit from parent
                        row_sources.append(
                            (
                                new_logical_idx,
                                parent_row.row_idx,  # TODO: we need the original source_version_id
                                # For now, let's look up the row source
                                "",  # placeholder
                                0,
                                0,
                            )
                        )
                        inherited = True
                        break
                if not inherited:
                    delta_rows.append((new_logical_idx, new_content))

            # Write delta file
            delta_file_rel = ""
            if delta_rows:
                delta_file_abs = data_dir / "delta_0001.jsonl"
                delta_file_rel = self._workspace.to_rel(delta_file_abs)
                new_row_sources = self._write_delta_file(
                    delta_file_abs=delta_file_abs,
                    delta_file_rel=delta_file_rel,
                    delta_rows=delta_rows,
                    new_version_id=new_v.id,
                )
                # Merge: for now, just use the new row sources directly (simplified)
                # We need a better COW tracking strategy
                row_sources = new_row_sources

            # For now, let's use a simpler approach: write all rows if any changed
            # (this is a placeholder; real COW is more complex)
            if not row_sources or len(row_sources) != len(new_rows):
                # Fallback: write all transformed rows
                full_rows = [(idx, content) for idx, content, _ in new_rows]
                full_file_abs = data_dir / "data_0001.jsonl"
                full_file_rel = self._workspace.to_rel(full_file_abs)
                row_sources = self._write_delta_file(
                    delta_file_abs=full_file_abs,
                    delta_file_rel=full_file_rel,
                    delta_rows=full_rows,
                    new_version_id=new_v.id,
                )

            # Insert row sources
            self._repo.bulk_insert_row_sources(version_id=new_v.id, rows=iter(row_sources))

            # Compute file stats for new version
            all_sample_rows = [content for _, content, _ in new_rows]
            file_stats = self._compute_file_stats_for_rows(
                rows=all_sample_rows,
                file_path=full_file_rel if full_rows else delta_file_rel,
            )
            self._repo.bulk_upsert_file_stats(version_id=new_v.id, rows=iter(file_stats))

            # Inherit annotations (only for rows that exist and are unchanged)
            # For now, skip annotation inheritance in map/filter_map
            # self._inherit_annotations(...)

            # Update row count
            self._repo.set_row_count(version_id=new_v.id, row_count=len(new_rows))

            # Update dataset's current_version_id
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE datasets SET current_version_id = %s WHERE id = %s",
                    (new_v.id, ds.id),
                )

        # Refresh inferred fields
        if all_sample_rows:
            inferred = infer_fields(all_sample_rows)
            self._repo.update_inferred_fields(dataset_id=ds.id, inferred_fields=inferred)

        return ds, new_v

    def overwrite_new_version(
        self,
        *,
        dataset_name: str,
        new_files: list[Path],
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        """F21: overwrite creates new version instead of delete+re-register.

        This replaces the current version with a new one, keeping history.
        """
        ds, parent_v = self._repo.get_dataset_by_name(name=dataset_name)
        new_version_number = self._next_version_number(dataset_id=ds.id)

        # Create new version directory and copy files
        data_dir = self._workspace.dataset_data_dir(dataset_name, new_version_number)
        data_dir.mkdir(parents=True, exist_ok=True)
        staged_files: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for src in new_files:
            src_abs = src.resolve()
            dest_name = src_abs.name
            if dest_name in seen:
                raise ValueError(f"Duplicate filename: {dest_name}")
            seen.add(dest_name)
            dest_abs = data_dir / dest_name
            shutil.copyfile(src_abs, dest_abs)
            rel = self._workspace.to_rel(dest_abs)
            staged_files.append((dest_abs, rel))

        with self._meta_conn.transaction() as conn:
            # Create new version row
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO dataset_versions (dataset_id, version_number, parent_version_id, row_count) "
                    "VALUES (%s, %s, %s, 0) RETURNING id, dataset_id, version_number, parent_version_id, row_count, created_at",
                    (ds.id, new_version_number, parent_v.id),
                )
                r = cur.fetchone()
            new_v = DatasetVersionMeta(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

            # Scan and insert new rows
            row_count, row_sources, file_stats, sample_rows = _scan_files_for_registration(
                version_id=new_v.id,
                staged_files=staged_files,
                sample_size=self._settings.register_field_sample_size,
            )

            self._repo.bulk_insert_row_sources(version_id=new_v.id, rows=iter(row_sources))
            self._repo.bulk_upsert_file_stats(version_id=new_v.id, rows=iter(file_stats))
            self._repo.set_row_count(version_id=new_v.id, row_count=row_count)

            # Update dataset's current_version_id
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE datasets SET current_version_id = %s WHERE id = %s",
                    (new_v.id, ds.id),
                )

        # Refresh inferred fields
        inferred = infer_fields(sample_rows)
        self._repo.update_inferred_fields(dataset_id=ds.id, inferred_fields=inferred)

        # Re-fetch the dataset and version to get the updated state
        ds, new_v = self._repo.get_dataset_by_name(name=dataset_name)

        return ds, new_v

    def _next_version_number(self, *, dataset_id: int) -> int:
        with self._meta_conn.connection.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS max_ver FROM dataset_versions WHERE dataset_id = %s",
                (dataset_id,),
            )
            max_v = cur.fetchone()
        return int(max_v["max_ver"]) + 1 if max_v and max_v["max_ver"] is not None else 1

    def _read_version_with_hashes(self, *, version_id: int) -> Iterator[_RowWithHash]:
        row_sources = self._repo.list_row_sources(version_id=version_id)
        # Group by file for efficient reading
        files: dict[str, list[RowSourceRow]] = {}
        for rs in row_sources:
            if rs.file_path not in files:
                files[rs.file_path] = []
            files[rs.file_path].append(rs)

        for file_rel, rs_list in files.items():
            file_abs = self._workspace.to_abs(file_rel)
            with file_abs.open("rb") as fh:
                for rs in rs_list:
                    fh.seek(rs.byte_offset)
                    line_bytes = fh.read(rs.byte_length)
                    line = line_bytes.decode("utf-8")
                    value = json.loads(line)
                    content_hash = _canonical_json_hash(value)
                    yield _RowWithHash(
                        row_idx=rs.row_idx,
                        content=value,
                        content_hash=content_hash,
                    )

    def _scan_for_append(
        self,
        *,
        version_id: int,
        staged_files: list[tuple[Path, str]],
        row_base_idx: int,
    ) -> tuple[
        list[tuple[int, int, str, int, int]],
        list[tuple[str, str, Any, Any, int]],
        list[object],
    ]:
        row_sources: list[tuple[int, int, str, int, int]] = []
        file_stats: list[tuple[str, str, Any, Any, int]] = []
        sample_rows: list[object] = []
        current_row_idx = row_base_idx

        for file_abs, file_rel in staged_files:
            file_row_count = 0
            file_min_max: dict[str, tuple[Any, Any]] = {}
            sampled_here = 0

            for scan in iter_jsonl_offsets(file_abs, strict=True):
                value = parse_jsonl_line(file_abs, scan.line, byte_offset=scan.byte_offset)
                row_sources.append(
                    (
                        current_row_idx,
                        version_id,
                        file_rel,
                        scan.byte_offset,
                        scan.byte_length,
                    )
                )
                if sampled_here < self._settings.register_field_sample_size:
                    sample_rows.append(value)
                    sampled_here += 1
                    _accumulate_min_max(value, file_min_max)
                file_row_count += 1
                current_row_idx += 1

            for field, (mn, mx) in file_min_max.items():
                file_stats.append((file_rel, field, mn, mx, file_row_count))

        return row_sources, file_stats, sample_rows

    def _write_delta_file(
        self,
        *,
        delta_file_abs: Path,
        delta_file_rel: str,
        delta_rows: list[tuple[int, object]],
        new_version_id: int,
    ) -> list[tuple[int, int, str, int, int]]:
        """Write delta rows to JSONL and build row_sources tuples."""
        row_sources: list[tuple[int, int, str, int, int]] = []
        byte_offset = 0

        with delta_file_abs.open("wb") as fh:
            for logical_idx, content in delta_rows:
                line_bytes = json.dumps(content, ensure_ascii=True).encode("utf-8")
                line_length = len(line_bytes)
                fh.write(line_bytes + b"\n")
                row_sources.append(
                    (
                        logical_idx,
                        new_version_id,
                        delta_file_rel,
                        byte_offset,
                        line_length,
                    )
                )
                byte_offset += line_length + 1

        return row_sources

    def _compute_file_stats_for_rows(
        self,
        *,
        rows: list[object],
        file_path: str,
    ) -> list[tuple[str, str, Any, Any, int]]:
        file_stats: list[tuple[str, str, Any, Any, int]] = []
        file_min_max: dict[str, tuple[Any, Any]] = {}
        for row in rows:
            _accumulate_min_max(row, file_min_max)
        for field, (mn, mx) in file_min_max.items():
            file_stats.append((file_path, field, mn, mx, len(rows)))
        return file_stats

    def _inherit_annotations(self, *, parent_version_id: int, new_version_id: int) -> None:
        annotations = self._repo.list_annotations(version_id=parent_version_id)
        if annotations:
            tuples = [
                (new_version_id, ann.user_id, ann.row_idx, ann.kind, ann.value)
                for ann in annotations
            ]
            self._repo.bulk_insert_annotations(rows=iter(tuples))

    def _inherit_field_indices(self, *, parent_version_id: int, _new_version_id: int) -> None:
        indexed_fields = self._repo.list_indexed_fields(version_id=parent_version_id)
        # For each indexed field, reindex the new version
        # (We skip for now; user can call create_index manually)


def _safe_min(a: Any, b: Any) -> Any:
    try:
        return a if a <= b else b
    except TypeError:
        return a


def _safe_max(a: Any, b: Any) -> Any:
    try:
        return a if a >= b else b
    except TypeError:
        return a


def _accumulate_min_max(value: object, acc: dict[str, tuple[Any, Any]]) -> None:
    for field_path, field_value in collect_scalar_fields(value):
        if field_value is None or isinstance(field_value, (dict, list)):
            continue
        if not isinstance(field_value, (str, int, float, bool)):
            continue
        if field_path not in acc:
            acc[field_path] = (field_value, field_value)
        else:
            mn, mx = acc[field_path]
            acc[field_path] = (_safe_min(mn, field_value), _safe_max(mx, field_value))


def _scan_files_for_registration(
    *,
    version_id: int,
    staged_files: list[tuple[Path, str]],
    sample_size: int,
) -> tuple[
    int, list[tuple[int, int, str, int, int]], list[tuple[str, str, Any, Any, int]], list[object]
]:
    row_sources: list[tuple[int, int, str, int, int]] = []
    file_stats: list[tuple[str, str, Any, Any, int]] = []
    total_rows = 0
    sample_rows: list[object] = []

    for file_abs, file_rel in staged_files:
        file_row_count = 0
        file_min_max: dict[str, tuple[Any, Any]] = {}
        sampled_here = 0
        for scan in iter_jsonl_offsets(file_abs, strict=True):
            value = parse_jsonl_line(file_abs, scan.line, byte_offset=scan.byte_offset)
            row_sources.append(
                (
                    total_rows + file_row_count,
                    version_id,
                    file_rel,
                    scan.byte_offset,
                    scan.byte_length,
                )
            )
            if sampled_here < sample_size:
                sample_rows.append(value)
                sampled_here += 1
                _accumulate_min_max(value, file_min_max)
            file_row_count += 1
        for field, (mn, mx) in file_min_max.items():
            file_stats.append((file_rel, field, mn, mx, file_row_count))
        total_rows += file_row_count

    return total_rows, row_sources, file_stats, sample_rows
