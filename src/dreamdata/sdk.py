"""dreamdata SDK — the only public surface.

Two classes: :class:`Engine` (top-level handle; owns DuckDB + PostgreSQL
connections) and :class:`Dataset` (a bound view of one dataset's current
version). User code never touches the internal layers directly.

Phase 3 features: list_versions, get_version, append, map, filter_map, overwrite creates new version
Phase 4 features: refresh_parquet_cache, list_parquet_caches
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import shutil
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from dreamdata.config import Settings, is_valid_dataset_name
from dreamdata.engine import (
    DuckDBEngine,
    FieldFilter,
    FilterCombination,
    FilterOp,
    and_filter,
    eq_filter,
    in_filter,
    or_filter,
    range_filter,
    regex_filter,
)
from dreamdata.errors import (
    DatasetAlreadyExists,
    DatasetNameInvalid,
    DatasetNotFound,
    EngineError,
    FileAlreadyRegistered,
    FileNotWritable,
    FilterInvalid,
    MetaError,
    NoteValueInvalid,
    RegistrationFileError,
    RowIndexOutOfRange,
    SdkError,
    SettingsInvalid,
    TagValueInvalid,
)
from dreamdata.fields import (
    collect_scalar_fields,
    infer_fields,
    is_missing,
    parse_field_path,
    traverse_field_path,
)
from dreamdata.meta import MetaConnection, MetaRepository
from dreamdata.parquet_cache import ParquetCacheInfo, ParquetCacheManager
from dreamdata.storage import (
    Workspace,
    iter_jsonl_offsets,
    parse_jsonl_line,
)
from dreamdata.versioning import VersionManager, VersionMeta

FilterValue = str | int | float | bool | None


@dataclass(slots=True, frozen=True)
class DatasetInfo:
    """Public-facing summary of a registered dataset."""

    name: str
    version_number: int
    row_count: int
    inferred_fields: list[str]
    file_count: int
    created_at: Any


@dataclass(slots=True, frozen=True)
class IndexInfo:
    """Summary info about a field index."""

    field_path: str
    row_count: int


# Export filter helpers for SDK users
__all__ = [
    "Dataset",
    "DatasetInfo",
    "Engine",
    "FilterOp",
    "IndexInfo",
    "ParquetCacheInfo",
    "VersionMeta",
    "and_filter",
    "eq_filter",
    "in_filter",
    "or_filter",
    "range_filter",
    "regex_filter",
]


class Engine:
    """Top-level handle. Owns the DuckDB and PostgreSQL connections.

    Construct with a :class:`Settings` instance (preferred for tests) or
    with environment variables (``DATABASE_URL``, ``WORKSPACE_PATH``,
    ``USER_ID``).
    """

    __slots__ = (
        "_duckdb",
        "_meta_conn",
        "_parquet_manager",
        "_repo",
        "_settings",
        "_user_id",
        "_version_manager",
        "_workspace",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        if settings is None:
            try:
                settings = Settings()
            except Exception as exc:
                raise SettingsInvalid(errors=[str(exc)]) from exc
        self._settings = settings
        self._user_id = settings.user_id
        self._workspace = Workspace(settings.workspace_path)
        self._workspace.ensure()
        self._meta_conn = MetaConnection(settings.database_url.get_secret_value())
        self._repo = MetaRepository(self._meta_conn)
        self._duckdb = DuckDBEngine(
            memory_limit=settings.duckdb_memory_limit,
            threads=settings.duckdb_threads,
        )
        self._version_manager = VersionManager(
            settings=settings,
            workspace=self._workspace,
            meta_conn=self._meta_conn,
            repo=self._repo,
        )
        self._parquet_manager = ParquetCacheManager(
            settings=settings,
            workspace=self._workspace,
            meta_conn=self._meta_conn,
            repo=self._repo,
        )

    # ----- lifecycle -----

    def close(self) -> None:
        """Close both underlying connections. The Engine is unusable after this."""
        try:
            self._duckdb.close()
        finally:
            self._meta_conn.close()

    def __enter__(self) -> Engine:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def workspace_root(self) -> Path:
        return self._workspace.root

    # ----- F1: register -----

    def register_dataset(
        self,
        name: str,
        files: list[Path] | list[str],
        *,
        overwrite: bool = False,
    ) -> Dataset:
        """Register a new dataset from one or more JSONL files (F1).

        Args:
            name: Dataset name. Must match ``^[a-zA-Z0-9_-]{1,128}$``.
            files: List of JSONL file paths (absolute or relative to CWD).
                The files are copied into the workspace; originals are left
                untouched.
            overwrite: If True and *name* already exists:
                - In v0.1.x: the existing dataset is deleted (tags/notes lost) and re-registered.
                - In v0.2.0+: a new version is created (history preserved).

        Returns:
            A :class:`Dataset` handle bound to the new dataset's version.

        Raises:
            DatasetNotFound: name failed the charset / length check.
            DatasetAlreadyExists: name taken and ``overwrite=False``.
            RegistrationFileError: a file is missing / unreadable / invalid JSONL.
        """
        _validate_dataset_name(name)
        if not files:
            raise SdkError("files list is empty", name=name)
        file_paths = _normalise_files(files)

        # Check if exists
        existing_present = True
        try:
            self._repo.get_dataset_by_name(name=name)
        except DatasetNotFound:
            existing_present = False

        if existing_present:
            if not overwrite:
                raise DatasetAlreadyExists(name=name)
            # F21: overwrite creates new version instead of delete+re-register
            ds, new_v = self._version_manager.overwrite_new_version(
                dataset_name=name,
                new_files=file_paths,
            )
            return Dataset(
                engine=self,
                dataset_id=ds.id,
                dataset_name=ds.name,
                version_id=new_v.id,
                version_number=new_v.version_number,
                row_count=new_v.row_count,
                inferred_fields=ds.inferred_fields,
            )

        # Fresh registration
        backup_dir: Path | None = None

        # Scan + infer + stats in one pass.
        try:
            ds_meta, v_meta = self._repo.insert_dataset(
                name=name,
                inferred_fields=[],
            )
            # Stage files into workspace/<name>/v1/data/ AFTER we have the database lock
            version_number = 1
            data_dir_abs = self._workspace.dataset_data_dir(name, version_number)
            data_dir_abs.mkdir(parents=True, exist_ok=True)
            staged: list[tuple[Path, str]] = []
            seen: set[str] = set()
            for src in file_paths:
                src_abs = src.resolve()
                dest_name = src_abs.name
                if dest_name in seen:
                    raise FileAlreadyRegistered(path=str(src))
                seen.add(dest_name)
                dest_abs = data_dir_abs / dest_name
                _safe_copy_file(src_abs, dest_abs)
                rel = self._workspace.to_rel(dest_abs)
                staged.append((dest_abs, rel))
            row_count, row_sources, file_stats, sample_rows = _scan_files_for_registration(
                version_id=v_meta.id,
                staged_files=staged,
                sample_size=self._settings.register_field_sample_size,
            )
            if row_count == 0:
                raise RegistrationFileError(
                    path=str(file_paths[0]),
                    reason="file contains no rows",
                )
            n_inserted = self._repo.bulk_insert_row_sources(
                version_id=v_meta.id,
                rows=iter(row_sources),
            )
            if n_inserted != row_count:
                raise MetaError(
                    "row_sources insert mismatch",
                    table="row_sources",
                    expected=row_count,
                    got=n_inserted,
                )
            self._repo.bulk_upsert_file_stats(
                version_id=v_meta.id,
                rows=iter(file_stats),
            )
            self._repo.set_row_count(version_id=v_meta.id, row_count=row_count)
            inferred = infer_fields(sample_rows)
            self._repo.update_inferred_fields(
                dataset_id=ds_meta.id,
                inferred_fields=inferred,
            )
        except Exception:
            # Roll back metadata + staged files on any failure. If we moved
            # an old workspace aside for overwrite, restore it so the
            # dataset returns to its prior state (atomicity invariant).
            shutil.rmtree(self._workspace.dataset_dir(name), ignore_errors=True)
            with contextlib.suppress(Exception):
                self._meta_conn.rollback()
            with contextlib.suppress(Exception):
                self._repo.delete_dataset(name=name)
            if backup_dir is not None and backup_dir.exists():
                shutil.move(str(backup_dir), str(self._workspace.dataset_dir(name)))
                # Re-register metadata by re-scanning the restored files.
                self._reimport_metadata_for(name)
            raise

        # Success: drop the backup if we made one.
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        return Dataset(
            engine=self,
            dataset_id=ds_meta.id,
            dataset_name=ds_meta.name,
            version_id=v_meta.id,
            version_number=v_meta.version_number,
            row_count=row_count,
            inferred_fields=inferred,
        )

    # ----- F2: list + info -----

    def list_datasets(self) -> list[str]:
        """Return the names of all registered datasets, sorted alphabetically (F2)."""
        return [d.name for d in self._repo.list_datasets()]

    def open_dataset(self, name: str, *, version_number: int | None = None) -> Dataset:
        """Open a registered dataset by name (F2).

        If version_number is provided, opens that historical version (read-only).
        Otherwise opens the current version (writable via transforms).

        Raises :class:`DatasetNotFound` if no dataset with *name* exists,
        or if the requested version doesn't exist.
        """
        ds, current_v = self._repo.get_dataset_by_name(name=name)

        if version_number is None:
            v = current_v
        else:
            # Look up specific version
            v_meta = self._version_manager.get_version(
                dataset_name=name, version_number=version_number
            )
            # Get full version metadata
            with self._meta_conn.connection.cursor() as cur:
                cur.execute(
                    "SELECT id, dataset_id, version_number, parent_version_id, row_count, created_at "
                    "FROM dataset_versions WHERE id = %s",
                    (v_meta.version_id,),
                )
                r = cur.fetchone()
            if r is None:
                raise DatasetNotFound(name=f"{name} v{version_number}")
            v = type(current_v)(
                id=r["id"],
                dataset_id=r["dataset_id"],
                version_number=r["version_number"],
                parent_version_id=r["parent_version_id"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )

        return Dataset(
            engine=self,
            dataset_id=ds.id,
            dataset_name=ds.name,
            version_id=v.id,
            version_number=v.version_number,
            row_count=v.row_count,
            inferred_fields=ds.inferred_fields,
        )

    def info(self, name: str) -> DatasetInfo:
        """Return summary metadata for *name* (F2)."""
        ds, v = self._repo.get_dataset_by_name(name=name)
        files = self._repo.list_files(version_id=v.id)
        return DatasetInfo(
            name=ds.name,
            version_number=v.version_number,
            row_count=v.row_count,
            inferred_fields=ds.inferred_fields,
            file_count=len(files),
            created_at=ds.created_at,
        )

    # ----- F8: delete -----

    def delete_dataset(self, name: str) -> None:
        """Delete a dataset and its staged files (F8).

        Tags, notes, and any other metadata are removed; the original
        JSONL files supplied at registration are not affected.

        Raises :class:`DatasetNotFound` if no such dataset exists.
        """
        self._open_or_raise(name)
        self._delete_dataset(name)

    # ----- F9: rename -----

    def rename_dataset(self, old_name: str, new_name: str) -> Dataset:
        """Rename a dataset (F9).

        Raises :class:`DatasetNotFound` if *old_name* doesn't exist.
        Raises :class:`DatasetAlreadyExists` if *new_name* is taken.
        """
        _validate_dataset_name(new_name)
        if old_name == new_name:
            return self.open_dataset(old_name)
        self._open_or_raise(old_name)
        # Capture version_id BEFORE rename so we can fix row_sources paths.
        _, v = self._repo.get_dataset_by_name(name=old_name)
        ds = self._repo.rename_dataset(old_name=old_name, new_name=new_name)
        # Move the workspace directory.
        src_dir = self._workspace.dataset_dir(old_name)
        dest_dir = self._workspace.dataset_dir(new_name)
        if src_dir.exists():
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_dir), str(dest_dir))
        # Update row_sources.file_path so future scans hit the new location.
        self._repo.update_row_source_paths_prefix(
            version_id=v.id,
            old_prefix=f"{old_name}/",
            new_prefix=f"{new_name}/",
        )
        return self.open_dataset(ds.name)

    # ----- F16: list_versions -----

    def list_versions(self, dataset_name: str) -> list[VersionMeta]:
        """F16: list all versions of a dataset, ordered by version number ascending."""
        return self._version_manager.list_versions(dataset_name=dataset_name)

    # ----- internal -----

    def _open_or_raise(self, name: str) -> None:
        try:
            self._repo.get_dataset_by_name(name=name)
        except DatasetNotFound:
            raise

    def _reimport_metadata_for(self, name: str) -> None:
        """Rebuild metadata rows for *name* from files already on disk.

        Used to restore the dataset to its prior state when an overwrite
        registration fails. The previous version (1) directory is already
        back in place under ``workspace/<name>/v1/data/``; this method
        scans those files and writes the metadata.
        """
        version_number = 1
        data_dir = self._workspace.dataset_data_dir(name, version_number)
        if not data_dir.exists():
            return
        staged: list[tuple[Path, str]] = []
        for child in sorted(data_dir.iterdir()):
            if child.is_file() and child.suffix == ".jsonl":
                staged.append((child, self._workspace.to_rel(child)))
        if not staged:
            return
        ds_meta, v_meta = self._repo.insert_dataset(name=name, inferred_fields=[])
        row_count, row_sources, file_stats, sample_rows = _scan_files_for_registration(
            version_id=v_meta.id,
            staged_files=staged,
            sample_size=self._settings.register_field_sample_size,
        )
        self._repo.bulk_insert_row_sources(version_id=v_meta.id, rows=iter(row_sources))
        self._repo.bulk_upsert_file_stats(version_id=v_meta.id, rows=iter(file_stats))
        self._repo.set_row_count(version_id=v_meta.id, row_count=row_count)
        self._repo.update_inferred_fields(
            dataset_id=ds_meta.id,
            inferred_fields=infer_fields(sample_rows),
        )

    def _delete_dataset(self, name: str) -> None:
        self._repo.delete_dataset(name=name)
        # Remove the workspace directory entirely.
        ds_dir = self._workspace.dataset_dir(name)
        if ds_dir.exists():
            shutil.rmtree(ds_dir, ignore_errors=True)


def _validate_dataset_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise DatasetNameInvalid(name=str(name), reason="empty name")
    if "\x00" in name:
        raise DatasetNameInvalid(name=name, reason="null byte in name")
    if not is_valid_dataset_name(name):
        raise DatasetNameInvalid(
            name=name,
            reason="must match ^[a-zA-Z0-9_-]{1,128}$ (no path traversal)",
        )


def _normalise_files(files: list[Path] | list[str]) -> list[Path]:
    out: list[Path] = []
    for f in files:
        p = Path(f).expanduser()
        p = (Path.cwd() / p).resolve() if not p.is_absolute() else p.resolve()
        if not p.exists():
            raise RegistrationFileError(path=str(f), reason="file does not exist")
        if not p.is_file():
            raise RegistrationFileError(path=str(f), reason="not a regular file")
        out.append(p)
    return out


def _safe_copy_file(src: Path, dest: Path) -> None:
    try:
        shutil.copyfile(src, dest)
    except OSError as exc:
        raise FileNotWritable(path=str(dest), reason=str(exc)) from exc


def _scan_files_for_registration(
    *,
    version_id: int,
    staged_files: list[tuple[Path, str]],
    sample_size: int,
) -> tuple[
    int, list[tuple[int, int, str, int, int]], list[tuple[str, str, Any, Any, int]], list[object]
]:
    """Scan staged files; return (row_count, row_sources, file_stats, sample_rows).

    The row_sources tuples are (row_idx, source_version_id, file_path,
    byte_offset, byte_length) — caller passes ``version_id`` as
    ``source_version_id`` for MVP. ``sample_rows`` is up to *sample_size*
    parsed JSON values per file, used for field inference.
    """
    row_sources: list[tuple[int, int, str, int, int]] = []
    file_stats: list[tuple[str, str, Any, Any, int]] = []
    total_rows = 0
    sample_rows: list[object] = []
    for staged_abs, rel in staged_files:
        file_row_count = 0
        file_min_max: dict[str, tuple[Any, Any]] = {}
        sampled_here = 0
        for scan in iter_jsonl_offsets(staged_abs, strict=True):
            value = parse_jsonl_line(staged_abs, scan.line, byte_offset=scan.byte_offset)
            row_sources.append(
                (
                    total_rows + file_row_count,
                    version_id,
                    rel,
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
            file_stats.append((rel, field, mn, mx, file_row_count))
        total_rows += file_row_count
    return total_rows, row_sources, file_stats, sample_rows


def _accumulate_min_max(value: object, acc: dict[str, tuple[Any, Any]]) -> None:
    """For each scalar field (including nested) of *value*, update min/max in *acc*."""
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


class Dataset:
    """A bound view of one dataset's version.

    If bound to the current version, can create new versions via append/map/filter_map.
    If bound to a historical version, is read-only.

    Read-path methods (:meth:`scan`, :meth:`search_by_field`,
    :meth:`search_by_tag`, :meth:`search`) return ``pandas.DataFrame``.
    Annotation methods (:meth:`tag`, :meth:`note`,
    :meth:`remove_tag`, :meth:`tags`, :meth:`notes`) mutate
    PostgreSQL metadata only — original JSONL is never touched.
    """

    __slots__ = (
        "_dataset_id",
        "_dataset_name",
        "_engine",
        "_inferred_fields",
        "_row_count",
        "_version_id",
        "_version_number",
    )

    def __init__(
        self,
        *,
        engine: Engine,
        dataset_id: int,
        dataset_name: str,
        version_id: int,
        version_number: int,
        row_count: int,
        inferred_fields: list[str],
    ) -> None:
        self._engine = engine
        self._dataset_id = dataset_id
        self._dataset_name = dataset_name
        self._version_id = version_id
        self._version_number = version_number
        self._row_count = row_count
        self._inferred_fields = list(inferred_fields)

    # ----- properties -----

    @property
    def name(self) -> str:
        return self._dataset_name

    @property
    def version_number(self) -> int:
        return self._version_number

    @property
    def version_id(self) -> int:
        return self._version_id

    @property
    def row_count(self) -> int:
        return self._row_count

    @property
    def inferred_fields(self) -> list[str]:
        return list(self._inferred_fields)

    @property
    def info(self) -> DatasetInfo:
        files = self._engine._repo.list_files(version_id=self._version_id)
        return DatasetInfo(
            name=self._dataset_name,
            version_number=self._version_number,
            row_count=self._row_count,
            inferred_fields=list(self._inferred_fields),
            file_count=len(files),
            created_at=None,
        )

    # ----- read path -----

    def scan(self, *, limit: int | None = None) -> pd.DataFrame:
        """Return all rows in the dataset as a DataFrame.

        Columns: ``row_idx``, ``data`` (raw JSON object).
        """
        return self._run_scan(field_filter=None, row_indices=None, limit=limit)

    def search_by_field(
        self, path: str, value: FilterValue, *, limit: int | None = None
    ) -> pd.DataFrame:
        """Return rows where ``<path> == <value>`` (F5).

        *path* is dotted with numeric indices (e.g. ``messages.0.role``).
        """
        try:
            _ = parse_field_path(path)
        except Exception:
            raise
        return self._run_scan(
            field_filter=FieldFilter(path=path, value=value),
            row_indices=None,
            limit=limit,
        )

    def search_by_tag(
        self,
        tag: str,
        *,
        user_id: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Return rows that carry the given *tag* (F6 / F11).

        If user_id is None (default), only returns tags belonging to the
        current engine's user. Pass a specific user_id to see another user's
        tags, or pass the special sentinel "*" to see tags from all users.
        """
        _validate_tag_value(tag, max_bytes=self._engine._settings.tag_value_max_bytes)
        lookup_user: str | None = self._engine.user_id if user_id is None else user_id
        if lookup_user == "*":
            lookup_user = None
        idxs = self._engine._repo.row_indices_for_tag(
            version_id=self._version_id,
            user_id=lookup_user,
            value=tag,
        )
        return self._run_scan(field_filter=None, row_indices=set(idxs), limit=limit)

    def search(
        self,
        *,
        field_path: str | None = None,
        field_value: FilterValue = None,
        tag: str | None = None,
        tag_user_id: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Combined search (F7 / F11). At least one of *field_path*/*tag* must be set.

        ``field_path`` + ``field_value`` AND ``tag`` semantics: rows must
        satisfy both predicates.

        tag_user_id controls tag visibility (see search_by_tag for details).
        """
        if field_path is None and tag is None:
            raise FilterInvalid(filter=None, reason="at least one of field_path or tag is required")

        tag_indices: set[int] | None = None
        if tag is not None:
            _validate_tag_value(tag, max_bytes=self._engine._settings.tag_value_max_bytes)
            lookup_user: str | None = self._engine.user_id if tag_user_id is None else tag_user_id
            if lookup_user == "*":
                lookup_user = None
            tag_indices = set(
                self._engine._repo.row_indices_for_tag(
                    version_id=self._version_id,
                    user_id=lookup_user,
                    value=tag,
                )
            )
            if field_path is None:
                return self._run_scan(field_filter=None, row_indices=tag_indices, limit=limit)

        ff: FieldFilter | None = None
        if field_path is not None:
            _ = parse_field_path(field_path)
            ff = FieldFilter(path=field_path, value=field_value)

        if tag_indices is not None and not tag_indices:
            return _empty_search_df()
        return self._run_scan(field_filter=ff, row_indices=tag_indices, limit=limit)

    def _run_scan(
        self,
        *,
        field_filter: FieldFilter | FilterCombination | None,
        row_indices: set[int] | None,
        limit: int | None,
    ) -> pd.DataFrame:
        # F26: try Parquet cache first (if pyarrow available)
        try:
            pyarrow_available = importlib.util.find_spec("pyarrow") is not None
            if pyarrow_available:
                has_cache, cache_info = self._engine._parquet_manager.has_usable_cache(
                    version_id=self._version_id,
                    field_filter=field_filter,
                )
                if has_cache and cache_info is not None:
                    try:
                        result = self._engine._parquet_manager.scan_with_cache(
                            version_id=self._version_id,
                            cache_info=cache_info,
                            field_filter=field_filter,
                            row_indices=row_indices,
                            limit=limit,
                        )
                        df = result.df
                        # The cache already has row_idx in the right format
                        if not df.empty:
                            df = df[["row_idx", "data"]]
                            return df.reset_index(drop=True)
                    except Exception:  # noqa: S110
                        # Fall back to JSONL scan
                        pass
        except ImportError:
            # Parquet not available, skip
            pass

        files_rel = self._engine._repo.list_files(version_id=self._version_id)

        # Try file-level pruning using file_stats (F14)
        pruned_files: set[str] | None = None
        if field_filter is not None:
            pruned_files = self._try_file_prune(field_filter)

        # Filter the file list if pruning found candidates
        if pruned_files is not None:
            files_rel = [p for p in files_rel if p in pruned_files]
            if not files_rel:
                return _empty_search_df()

        files_abs = [self._engine._workspace.to_abs(p) for p in files_rel]

        # Build row_indices_per_file if needed
        row_indices_per_file: dict[int, set[int]] | None = None
        if row_indices is not None:
            # Build a map from file_path to list of local row indices
            sources = self._engine._repo.list_row_sources(version_id=self._version_id)
            file_to_global: dict[str, list[tuple[int, int]]] = {p: [] for p in files_rel}
            for rs in sources:
                if rs.file_path in file_to_global:
                    file_to_global[rs.file_path].append(
                        (rs.row_idx, len(file_to_global[rs.file_path]))
                    )
            # Build reverse lookup: global row idx -> (file_idx, file_row_idx)
            global_to_file: dict[int, tuple[int, int]] = {}
            for file_idx, file_path in enumerate(files_rel):
                for global_row_idx, local_row_idx in file_to_global[file_path]:
                    global_to_file[global_row_idx] = (file_idx, local_row_idx)
            # Build per-file allowed row indices
            row_indices_per_file = {}
            for global_row in row_indices:
                file_idx, file_row_idx = global_to_file.get(global_row, (-1, -1))
                if file_idx == -1:
                    continue
                if file_idx not in row_indices_per_file:
                    row_indices_per_file[file_idx] = set()
                row_indices_per_file[file_idx].add(file_row_idx)

        try:
            result = self._engine._duckdb.scan_jsonl(
                files=files_abs,
                field_filter=field_filter,
                row_indices=row_indices,
                row_indices_per_file=row_indices_per_file,
                limit=limit,
            )
        except EngineError:
            raise
        df = result.df
        # Translate the per-file row_idx into the global logical row_idx
        # using the row_sources mapping. The DuckDB scan returns
        # (file_idx, file_row_idx, data); we map file_row_idx -> global
        # row_idx via the file's starting offset in the global ordering.
        if df.empty:
            return _empty_search_df()
        global_indices = self._resolve_global_row_idx(df, files_rel=files_rel)
        df = df.assign(row_idx=global_indices)
        df = df[["row_idx", "data"]]
        return df.reset_index(drop=True)

    def _try_file_prune(self, filter: FieldFilter | FilterCombination) -> set[str] | None:
        """Try to prune files using file_stats. Returns pruned file set or None."""
        if isinstance(filter, FilterCombination):
            # For OR, we can't prune safely; for AND, try each filter and intersect
            if filter.kind == "or":
                return None
            pruned: set[str] | None = None
            for f in filter.filters:
                sub_pruned = self._try_file_prune(f)
                if sub_pruned is None:
                    continue
                if pruned is None:
                    pruned = sub_pruned
                else:
                    pruned = pruned & sub_pruned
            return pruned

        # Single FieldFilter - check if we have file_stats for it
        file_stats = self._engine._repo.list_file_stats(version_id=self._version_id)
        fields_with_stats = {s.field_path for s in file_stats}
        if filter.path not in fields_with_stats:
            return None

        # We have stats - try pruning
        exact_value: Any = None
        min_value: Any = None
        max_value: Any = None
        if filter.op == FilterOp.EQ:
            exact_value = filter.value
        elif filter.op == FilterOp.GT or filter.op == FilterOp.GE:
            min_value = filter.value
        elif filter.op == FilterOp.LT or filter.op == FilterOp.LE:
            max_value = filter.value

        if exact_value is not None or min_value is not None or max_value is not None:
            return self._engine._repo.prune_files_for_field(
                version_id=self._version_id,
                field_path=filter.path,
                exact_value=exact_value,
                min_value=min_value,
                max_value=max_value,
            )

        return None

    def _resolve_global_row_idx(
        self, df: pd.DataFrame, files_rel: list[str] | None = None
    ) -> list[int]:
        """Map per-file (file_idx, file_row_idx) to the global logical row_idx."""
        if files_rel is None:
            files_rel = self._engine._repo.list_files(version_id=self._version_id)
        # file_idx → list of global row_idx
        sources = self._engine._repo.list_row_sources(version_id=self._version_id)
        per_file_global: dict[str, list[int]] = {p: [] for p in files_rel}
        for rs in sources:
            if rs.file_path in per_file_global:
                per_file_global[rs.file_path].append(rs.row_idx)
        per_file_lookup: list[list[int]] = [per_file_global[p] for p in files_rel]

        file_indices = df["file_idx"].tolist()
        row_indices = df["row_idx"].tolist()
        if len(file_indices) != len(row_indices):
            raise MetaError(
                "scan result column length mismatch",
                table="<scan>",
                file_count=len(file_indices),
                row_count=len(row_indices),
            )
        out: list[int] = []
        for fidx, frow in zip(file_indices, row_indices, strict=True):
            order = per_file_lookup[int(fidx)]
            out.append(order[int(frow)])
        return out

    # ----- annotations -----

    def tag(self, row_idx: int | list[int], tag: str | list[str]) -> None:
        """Attach one or more tags to one or more rows (F3).

        Idempotent: re-tagging the same (row, tag) is a no-op. Tag
        values are NFC-normalized at write time.
        """
        rows = _coerce_int_list(row_idx, name="row_idx")
        tags = _coerce_str_list(tag, name="tag")
        self._assert_row_indices(rows)
        for v in tags:
            _validate_tag_value(v, max_bytes=self._engine._settings.tag_value_max_bytes)
        norm_tags = [_normalise_tag(v) for v in tags]
        for r in rows:
            for v in norm_tags:
                self._engine._repo.upsert_tag(
                    version_id=self._version_id,
                    user_id=self._engine.user_id,
                    row_idx=r,
                    value=v,
                )

    def remove_tag(
        self,
        row_idx: int | list[int],
        tag: str | list[str] | None = None,
    ) -> int:
        """Remove tags from rows (F3). Returns the number of removed annotations.

        If *tag* is None, all tags on the rows are removed. Otherwise only
        the listed tags are removed.
        """
        rows = _coerce_int_list(row_idx, name="row_idx")
        self._assert_row_indices(rows)
        if tag is None:
            total = 0
            for r in rows:
                total += self._engine._repo.delete_tag(
                    version_id=self._version_id,
                    user_id=self._engine.user_id,
                    row_idx=r,
                    value=None,
                )
            return total
        tags = _coerce_str_list(tag, name="tag")
        norm_tags = [_normalise_tag(v) for v in tags]
        total = 0
        for r in rows:
            for v in norm_tags:
                total += self._engine._repo.delete_tag(
                    version_id=self._version_id,
                    user_id=self._engine.user_id,
                    row_idx=r,
                    value=v,
                )
        return total

    def tags(
        self,
        row_idx: int | None = None,
        *,
        user_id: str | None = None,
    ) -> list[tuple[int, str]]:
        """Return ``(row_idx, tag)`` tuples, optionally filtered (F3 / F11).

        If user_id is None (default), only returns tags belonging to the
        current engine's user. Pass a specific user_id to see another user's
        tags, or pass the special sentinel "*" to see tags from all users.
        """
        lookup_user: str | None = self._engine.user_id if user_id is None else user_id
        if lookup_user == "*":
            lookup_user = None
        anns = self._engine._repo.list_annotations(
            version_id=self._version_id,
            user_id=lookup_user,
            row_idx=row_idx,
            kind="tag",
        )
        return [(ann.row_idx, ann.value) for ann in anns]

    def note(self, row_idx: int, body: str) -> int:
        """Attach a note body to *row_idx* (F4). Returns the new annotation id."""
        self._assert_row_indices([row_idx])
        _validate_note_value(body, max_bytes=self._engine._settings.note_value_max_bytes)
        return self._engine._repo.insert_note(
            version_id=self._version_id,
            user_id=self._engine.user_id,
            row_idx=row_idx,
            value=unicodedata.normalize("NFC", body),
        )

    def notes(
        self,
        row_idx: int | None = None,
        *,
        user_id: str | None = None,
    ) -> list[tuple[int, int, str]]:
        """Return ``(id, row_idx, body)`` tuples for notes, optionally filtered (F4 / F11).

        If user_id is None (default), only returns notes belonging to the
        current engine's user. Pass a specific user_id to see another user's
        notes, or pass the special sentinel "*" to see notes from all users.
        """
        lookup_user: str | None = self._engine.user_id if user_id is None else user_id
        if lookup_user == "*":
            lookup_user = None
        anns = self._engine._repo.list_annotations(
            version_id=self._version_id,
            user_id=lookup_user,
            row_idx=row_idx,
            kind="note",
        )
        return [(ann.id, ann.row_idx, ann.value) for ann in anns]

    # ----- advanced search (F12) -----

    def search_with_filter(
        self,
        filter: FieldFilter | FilterCombination,
        *,
        limit: int | None = None,
        use_index: bool = True,
    ) -> pd.DataFrame:
        """Search using advanced filters (F12: regex, range, IN, boolean).

        If use_index is True and the filtered field has an index, the index
        will be used to prune rows before scanning.

        Example::

            from dreamdata import range_filter, regex_filter, and_filter

            ds.search_with_filter(range_filter("score", 0.8, 1.0))
            ds.search_with_filter(regex_filter("title", "^A"))
            ds.search_with_filter(and_filter(
                range_filter("score", 0.8, 1.0),
                regex_filter("title", "^A")
            ))
        """
        # Try index pruning if available
        row_indices: set[int] | None = None
        if use_index:
            row_indices = self._try_index_lookup(filter)

        return self._run_scan(field_filter=filter, row_indices=row_indices, limit=limit)

    def _try_index_lookup(self, filter: FieldFilter | FilterCombination) -> set[int] | None:
        """Try to use field_index to pre-filter rows. Returns None if no index."""
        if isinstance(filter, FilterCombination):
            # For combinations, try to find a single indexed field filter to use
            for f in filter.filters:
                if isinstance(f, FieldFilter):
                    result = self._try_index_lookup(f)
                    if result is not None:
                        return result
            return None

        # Single FieldFilter
        indexed_fields = self._engine._repo.list_indexed_fields(version_id=self._version_id)
        if filter.path not in indexed_fields:
            return None

        # Can use index for equality, IN, and range
        if filter.op == FilterOp.EQ:
            return self._engine._repo.row_indices_for_field_value(
                version_id=self._version_id,
                field_path=filter.path,
                value=filter.value,
            )
        elif filter.op == FilterOp.IN:
            assert isinstance(filter.value, (list, tuple))
            return self._engine._repo.row_indices_for_field_in(
                version_id=self._version_id,
                field_path=filter.path,
                values=list(filter.value),
            )
        elif filter.op in (FilterOp.GT, FilterOp.GE, FilterOp.LT, FilterOp.LE):
            min_val = filter.value if filter.op in (FilterOp.GT, FilterOp.GE) else None
            max_val = filter.value if filter.op in (FilterOp.LT, FilterOp.LE) else None
            return self._engine._repo.row_indices_for_field_range(
                version_id=self._version_id,
                field_path=filter.path,
                min_value=min_val,
                max_value=max_val,
                include_min=filter.op != FilterOp.GT,
                include_max=filter.op != FilterOp.LT,
            )

        return None

    # ----- index management (F13, F14, F15) -----

    def create_index(self, field_path: str) -> IndexInfo:
        """Create an index on the given field (F13).

        Indexes speed up searches on that field by allowing pruning before scan.

        Returns IndexInfo with the number of rows indexed.
        """
        _ = parse_field_path(field_path)

        # Delete existing index if present
        self._engine._repo.delete_field_index(version_id=self._version_id, field_path=field_path)

        # Scan all rows and collect field values
        files_rel = self._engine._repo.list_files(version_id=self._version_id)
        files_abs = [self._engine._workspace.to_abs(p) for p in files_rel]

        # Build a map from file_idx to file_path
        file_idx_to_path = {i: p for i, p in enumerate(files_rel)}

        # Build row_idx lookup first
        sources = self._engine._repo.list_row_sources(version_id=self._version_id)
        per_file_global: dict[str, list[int]] = {p: [] for p in files_rel}
        for rs in sources:
            per_file_global[rs.file_path].append(rs.row_idx)
        per_file_lookup: list[list[int]] = [per_file_global[p] for p in files_rel]

        # Now scan and collect values
        def index_rows() -> Iterator[tuple[int, Any]]:
            for file_idx, file_path in enumerate(files_abs):
                global_row_indices = per_file_lookup[file_idx]
                with file_path.open("rb") as fh:
                    for file_row_idx, line_bytes in enumerate(fh):
                        line = line_bytes.rstrip(b"\r\n")
                        if not line:
                            continue
                        value = json.loads(line)
                        tokens = parse_field_path(field_path)
                        leaf = traverse_field_path(value, tokens)
                        # Store NULL as None; missing becomes NULL too
                        stored_val = None if is_missing(leaf) else leaf
                        global_row_idx = global_row_indices[file_row_idx]
                        yield (global_row_idx, stored_val)

        row_count = self._engine._repo.bulk_insert_field_index(
            version_id=self._version_id,
            field_path=field_path,
            rows=index_rows(),
        )

        return IndexInfo(field_path=field_path, row_count=row_count)

    def drop_index(self, field_path: str) -> int:
        """Drop an index on the given field (F15).

        Returns the number of index rows deleted.
        """
        return self._engine._repo.delete_field_index(
            version_id=self._version_id, field_path=field_path
        )

    def list_indexes(self) -> list[IndexInfo]:
        """List all indexes for this dataset (F13)."""
        fields = self._engine._repo.list_indexed_fields(version_id=self._version_id)
        return [IndexInfo(field_path=f, row_count=-1) for f in fields]

    # ----- Phase 3: versioning (F16-F22) -----

    def list_versions(self) -> list[VersionMeta]:
        """F16: list all versions of this dataset, ordered by version number ascending."""
        return self._engine._version_manager.list_versions(dataset_name=self._dataset_name)

    def append(self, files: list[Path] | list[str]) -> Dataset:
        """F18: append new rows to the dataset, creating a new version.

        Returns a new Dataset handle bound to the new version.
        """
        file_paths = _normalise_files(files)
        ds, new_v = self._engine._version_manager.append(
            dataset_name=self._dataset_name,
            new_files=file_paths,
            parent_version_number=self._version_number,
        )
        # Refresh inferred fields
        ds_meta, _ = self._engine._repo.get_dataset_by_name(name=ds.name)
        return Dataset(
            engine=self._engine,
            dataset_id=ds.id,
            dataset_name=ds.name,
            version_id=new_v.id,
            version_number=new_v.version_number,
            row_count=new_v.row_count,
            inferred_fields=ds_meta.inferred_fields,
        )

    def map(self, func: Callable[[object], object]) -> Dataset:
        """F19: transform each row, creating a new version with copy-on-write.

        The function takes a row (dict) and returns a transformed row (dict).
        Returns a new Dataset handle bound to the new version.
        """
        ds, new_v = self._engine._version_manager.map(
            dataset_name=self._dataset_name,
            func=func,
            parent_version_number=self._version_number,
        )
        ds_meta, _ = self._engine._repo.get_dataset_by_name(name=ds.name)
        return Dataset(
            engine=self._engine,
            dataset_id=ds.id,
            dataset_name=ds.name,
            version_id=new_v.id,
            version_number=new_v.version_number,
            row_count=new_v.row_count,
            inferred_fields=ds_meta.inferred_fields,
        )

    def filter_map(self, func: Callable[[object], object | None]) -> Dataset:
        """F20: filter and transform rows, creating a new version.

        The function takes a row (dict) and returns either:
        - A transformed row (dict) to keep
        - None to omit the row from the new version

        Returns a new Dataset handle bound to the new version.
        """
        ds, new_v = self._engine._version_manager.filter_map(
            dataset_name=self._dataset_name,
            func=func,
            parent_version_number=self._version_number,
        )
        ds_meta, _ = self._engine._repo.get_dataset_by_name(name=ds.name)
        return Dataset(
            engine=self._engine,
            dataset_id=ds.id,
            dataset_name=ds.name,
            version_id=new_v.id,
            version_number=new_v.version_number,
            row_count=new_v.row_count,
            inferred_fields=ds_meta.inferred_fields,
        )

    # ----- Phase 4: Parquet cache (F23-F26) -----

    def refresh_parquet_cache(self, *, field_path: str | None = None) -> ParquetCacheInfo:
        """F23: manually refresh or create a Parquet cache.

        If field_path is None, caches all rows (full-scan cache).
        If field_path is provided, creates a columnar cache for that field.

        Requires pyarrow to be installed. Install with: pip install 'dreamdata[parquet]'
        """
        return self._engine._parquet_manager.refresh_parquet_cache(
            version_id=self._version_id,
            field_path=field_path,
        )

    def list_parquet_caches(self) -> list[ParquetCacheInfo]:
        """F24: list existing Parquet caches for this version."""
        return self._engine._parquet_manager.list_parquet_caches(version_id=self._version_id)

    # ----- internal -----

    def _assert_row_indices(self, rows: list[int]) -> None:
        for r in rows:
            if r < 0 or r >= self._row_count:
                raise RowIndexOutOfRange(row_idx=r, row_count=self._row_count)


def _coerce_int_list(v: int | list[int], *, name: str) -> list[int]:
    if isinstance(v, int):
        return [v]
    if isinstance(v, list) and all(isinstance(x, int) for x in v):
        return list(v)
    raise SdkError(f"{name} must be int or list[int]", name=name)


def _coerce_str_list(v: str | list[str], *, name: str) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return list(v)
    raise SdkError(f"{name} must be str or list[str]", name=name)


def _validate_tag_value(value: str, *, max_bytes: int) -> None:
    if not isinstance(value, str):
        raise TagValueInvalid(value=str(value), reason="tag must be a string")
    if "\x00" in value:
        raise TagValueInvalid(value=value, reason="null byte in tag value")
    if len(value.encode("utf-8")) > max_bytes:
        raise TagValueInvalid(
            value=value,
            reason=f"tag exceeds {max_bytes}-byte limit",
        )
    norm = unicodedata.normalize("NFC", value)
    if norm != value:
        # Accept either form on input; store normalised form
        pass


def _normalise_tag(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _validate_note_value(value: str, *, max_bytes: int) -> None:
    if not isinstance(value, str):
        raise NoteValueInvalid(value=str(value), reason="note must be a string")
    if "\x00" in value:
        raise NoteValueInvalid(value=value, reason="null byte in note body")
    if len(value.encode("utf-8")) > max_bytes:
        raise NoteValueInvalid(
            value=value,
            reason=f"note exceeds {max_bytes}-byte limit",
        )


def _empty_search_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["row_idx", "data"])
