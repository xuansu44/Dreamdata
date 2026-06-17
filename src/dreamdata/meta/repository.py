"""Typed metadata repository — the only surface for PostgreSQL access.

Each method returns a frozen dataclass; raw dict rows never escape this
module. All SQL uses psycopg v3 ``%s`` parameters and ``sql.Identifier``
for table/column names (which cannot be parameterised).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from psycopg import sql
from psycopg.types.json import Jsonb

from dreamdata.errors import (
    DatasetAlreadyExists,
    DatasetNotFound,
    MetadataConstraintViolation,
    MetadataWriteFailed,
)
from dreamdata.meta.connection import MetaConnection

AnnotationKind = Literal["tag", "note"]


@dataclass(slots=True, frozen=True)
class DatasetMeta:
    """One row from ``datasets``."""

    id: int
    name: str
    current_version_id: int | None
    inferred_fields: list[str]
    created_at: Any


@dataclass(slots=True, frozen=True)
class DatasetVersionMeta:
    """One row from ``dataset_versions``."""

    id: int
    dataset_id: int
    version_number: int
    parent_version_id: int | None
    row_count: int
    created_at: Any


@dataclass(slots=True, frozen=True)
class RowSourceRow:
    """One row from ``row_sources`` (a logical row's physical location)."""

    version_id: int
    row_idx: int
    source_version_id: int
    file_path: str
    byte_offset: int
    byte_length: int


@dataclass(slots=True, frozen=True)
class AnnotationRow:
    """One row from ``user_annotations``."""

    id: int
    version_id: int
    user_id: str
    row_idx: int
    kind: AnnotationKind
    value: str
    created_at: Any


@dataclass(slots=True, frozen=True)
class FileStatRow:
    """One row from ``file_stats``."""

    version_id: int
    file_path: str
    field_path: str
    min_value: Any
    max_value: Any
    row_count: int


@dataclass(slots=True, frozen=True)
class FieldIndexRow:
    """One row from ``field_index`` (indexed field value -> row_idx mapping)."""

    version_id: int
    field_path: str
    row_idx: int
    value: Any


@dataclass(slots=True, frozen=True)
class IndexInfo:
    """Summary info about a created index."""

    version_id: int
    field_path: str
    row_count: int


class MetaRepository:
    """CRUD surface over the dreamdata metadata schema."""

    SCHEMA_VERSION = 1

    def __init__(self, conn: MetaConnection) -> None:
        self._conn = conn

    # -------------------------------------------------------------- datasets

    def insert_dataset(
        self,
        *,
        name: str,
        inferred_fields: list[str],
    ) -> tuple[DatasetMeta, DatasetVersionMeta]:
        """Create a dataset row and its implicit v1 version in one transaction.

        Raises :class:`DatasetAlreadyExists` on name collision. The returned
        dataset's ``current_version_id`` points at the new version row.
        """
        with self._conn.transaction() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "INSERT INTO {tbl} (name, inferred_fields) VALUES (%s, %s) "
                            "RETURNING id, name, current_version_id, inferred_fields, created_at"
                        ).format(tbl=sql.Identifier("datasets")),
                        (name, Jsonb(inferred_fields)),
                    )
                    ds_row = cur.fetchone()
            except Exception as exc:
                if "datasets_name_key" in str(exc):
                    raise DatasetAlreadyExists(name=name) from exc
                raise MetadataWriteFailed(table="datasets", reason=str(exc)) from exc
            if ds_row is None:
                raise MetadataWriteFailed(table="datasets", reason="INSERT did not RETURN a row")
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {tbl} (dataset_id, version_number, parent_version_id, row_count) "
                        "VALUES (%s, 1, NULL, 0) "
                        "RETURNING id, dataset_id, version_number, parent_version_id, row_count, created_at"
                    ).format(tbl=sql.Identifier("dataset_versions")),
                    (ds_row["id"],),
                )
                v_row = cur.fetchone()
            if v_row is None:
                raise MetadataWriteFailed(table="dataset_versions", reason="INSERT did not RETURN")
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("UPDATE {tbl} SET current_version_id = %s WHERE id = %s").format(
                        tbl=sql.Identifier("datasets")
                    ),
                    (v_row["id"], ds_row["id"]),
                )
        ds = DatasetMeta(
            id=ds_row["id"],
            name=ds_row["name"],
            current_version_id=v_row["id"],
            inferred_fields=ds_row["inferred_fields"] or [],
            created_at=ds_row["created_at"],
        )
        v = DatasetVersionMeta(
            id=v_row["id"],
            dataset_id=v_row["dataset_id"],
            version_number=v_row["version_number"],
            parent_version_id=v_row["parent_version_id"],
            row_count=v_row["row_count"],
            created_at=v_row["created_at"],
        )
        return ds, v

    def get_dataset_by_name(self, *, name: str) -> tuple[DatasetMeta, DatasetVersionMeta]:
        row = self._conn.fetchone(
            sql.SQL(
                "SELECT d.id AS id, d.name AS name, d.current_version_id AS current_version_id, "
                "       d.inferred_fields AS inferred_fields, d.created_at AS created_at, "
                "       v.id AS v_id, v.dataset_id AS v_dataset_id, "
                "       v.version_number AS v_version_number, v.parent_version_id AS v_parent_version_id, "
                "       v.row_count AS v_row_count, v.created_at AS v_created_at "
                "FROM datasets d LEFT JOIN dataset_versions v ON v.id = d.current_version_id "
                "WHERE d.name = %s"
            ),
            (name,),
        )
        if row is None:
            raise DatasetNotFound(name=name)
        if row["v_id"] is None:
            raise MetadataWriteFailed(
                table="dataset_versions",
                reason=f"dataset {name!r} has no current_version_id",
            )
        return (
            DatasetMeta(
                id=row["id"],
                name=row["name"],
                current_version_id=row["current_version_id"],
                inferred_fields=row["inferred_fields"] or [],
                created_at=row["created_at"],
            ),
            DatasetVersionMeta(
                id=row["v_id"],
                dataset_id=row["v_dataset_id"],
                version_number=row["v_version_number"],
                parent_version_id=row["v_parent_version_id"],
                row_count=row["v_row_count"],
                created_at=row["v_created_at"],
            ),
        )

    def list_datasets(self) -> list[DatasetMeta]:
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT id, name, current_version_id, inferred_fields, created_at "
                "FROM datasets ORDER BY name ASC"
            ),
        )
        return [
            DatasetMeta(
                id=r["id"],
                name=r["name"],
                current_version_id=r["current_version_id"],
                inferred_fields=r["inferred_fields"] or [],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def rename_dataset(self, *, old_name: str, new_name: str) -> DatasetMeta:
        try:
            with self._conn.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "UPDATE {tbl} SET name = %s WHERE name = %s "
                            "RETURNING id, name, current_version_id, inferred_fields, created_at"
                        ).format(tbl=sql.Identifier("datasets")),
                        (new_name, old_name),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            if "datasets_name_key" in str(exc):
                raise DatasetAlreadyExists(name=new_name) from exc
            raise MetadataWriteFailed(table="datasets", reason=str(exc)) from exc
        if row is None:
            raise DatasetNotFound(name=old_name)
        return DatasetMeta(
            id=row["id"],
            name=row["name"],
            current_version_id=row["current_version_id"],
            inferred_fields=row["inferred_fields"] or [],
            created_at=row["created_at"],
        )

    def delete_dataset(self, *, name: str) -> list[str]:
        """Delete a dataset and return the relative file_paths it owned.

        The CASCADE on ``dataset_versions`` propagates to ``row_sources``,
        ``user_annotations``, and ``file_stats``.
        """
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT DISTINCT rs.file_path AS file_path "
                    "FROM datasets d "
                    "JOIN dataset_versions v ON v.dataset_id = d.id "
                    "JOIN row_sources rs ON rs.version_id = v.id "
                    "WHERE d.name = %s"
                ),
                (name,),
            )
            rows = cur.fetchall()
            cur.execute(
                sql.SQL("DELETE FROM {tbl} WHERE name = %s").format(tbl=sql.Identifier("datasets")),
                (name,),
            )
        return sorted({r["file_path"] for r in rows if r["file_path"]})

    def set_row_count(self, *, version_id: int, row_count: int) -> None:
        self._conn.execute(
            sql.SQL("UPDATE {tbl} SET row_count = %s WHERE id = %s").format(
                tbl=sql.Identifier("dataset_versions")
            ),
            (row_count, version_id),
        )

    def update_inferred_fields(self, *, dataset_id: int, inferred_fields: list[str]) -> None:
        self._conn.execute(
            sql.SQL("UPDATE {tbl} SET inferred_fields = %s WHERE id = %s").format(
                tbl=sql.Identifier("datasets")
            ),
            (Jsonb(inferred_fields), dataset_id),
        )

    def update_row_source_paths_prefix(
        self, *, version_id: int, old_prefix: str, new_prefix: str
    ) -> int:
        """Replace ``old_prefix`` with ``new_prefix`` at the start of every
        ``row_sources.file_path`` for *version_id*. Also updates file_stats.

        Used by rename to keep file paths aligned with the moved workspace
        directory. Returns the number of rows updated.
        """
        like = old_prefix + "%"
        total = 0
        with self._conn.transaction() as conn, conn.cursor() as cur:
            # Update row_sources
            cur.execute(
                sql.SQL(
                    "UPDATE {tbl} SET file_path = "
                    "        OVERLAY(file_path PLACING %s FROM 1 FOR LENGTH(%s)) "
                    "WHERE version_id = %s AND file_path LIKE %s"
                ).format(tbl=sql.Identifier("row_sources")),
                (new_prefix, old_prefix, version_id, like),
            )
            total += cur.rowcount or 0
            # Update file_stats
            cur.execute(
                sql.SQL(
                    "UPDATE {tbl} SET file_path = "
                    "        OVERLAY(file_path PLACING %s FROM 1 FOR LENGTH(%s)) "
                    "WHERE version_id = %s AND file_path LIKE %s"
                ).format(tbl=sql.Identifier("file_stats")),
                (new_prefix, old_prefix, version_id, like),
            )
            total += cur.rowcount or 0
            # Update field_index doesn't need file path, it's per row
        return total

    # ------------------------------------------------------------- row_sources

    def bulk_insert_row_sources(
        self, *, version_id: int, rows: Iterator[tuple[int, int, str, int, int]]
    ) -> int:
        """Bulk-insert (row_idx, source_version_id, file_path, byte_offset, byte_length) tuples.

        Returns the number of inserted rows. Uses COPY for throughput.
        """
        count = 0

        def _rows() -> Iterator[tuple[int, int, int, str, int, int]]:
            nonlocal count
            for row_idx, source_version_id, file_path, byte_offset, byte_length in rows:
                count += 1
                yield (version_id, row_idx, source_version_id, file_path, byte_offset, byte_length)

        self._conn.copy_expert(
            sql.SQL(
                "COPY {tbl} (version_id, row_idx, source_version_id, file_path, byte_offset, byte_length) "
                "FROM STDIN"
            ).format(tbl=sql.Identifier("row_sources")),
            _rows(),
        )
        return count

    def list_row_sources(self, *, version_id: int) -> list[RowSourceRow]:
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT version_id, row_idx, source_version_id, file_path, byte_offset, byte_length "
                "FROM {tbl} WHERE version_id = %s ORDER BY row_idx ASC"
            ).format(tbl=sql.Identifier("row_sources")),
            (version_id,),
        )
        return [
            RowSourceRow(
                version_id=r["version_id"],
                row_idx=r["row_idx"],
                source_version_id=r["source_version_id"],
                file_path=r["file_path"],
                byte_offset=r["byte_offset"],
                byte_length=r["byte_length"],
            )
            for r in rows
        ]

    def list_files(self, *, version_id: int) -> list[str]:
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT DISTINCT file_path FROM {tbl} WHERE version_id = %s ORDER BY file_path"
            ).format(tbl=sql.Identifier("row_sources")),
            (version_id,),
        )
        return [r["file_path"] for r in rows]

    # ------------------------------------------------------------- annotations

    def upsert_tag(self, *, version_id: int, user_id: str, row_idx: int, value: str) -> None:
        try:
            self._conn.execute(
                sql.SQL(
                    "INSERT INTO {tbl} (version_id, user_id, row_idx, kind, value) "
                    "VALUES (%s, %s, %s, 'tag', %s) "
                    "ON CONFLICT (version_id, user_id, row_idx, kind, value) DO NOTHING"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, user_id, row_idx, value),
            )
        except Exception as exc:
            if "value_too_long" in str(exc) or "value_exceeds" in str(exc):
                raise MetadataConstraintViolation(
                    constraint="user_annotations_value_length",
                    detail=str(exc),
                ) from exc
            raise MetadataWriteFailed(table="user_annotations", reason=str(exc)) from exc

    def delete_tag(self, *, version_id: int, user_id: str, row_idx: int, value: str | None) -> int:
        if value is None:
            with self._conn.transaction() as conn, conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "DELETE FROM {tbl} WHERE version_id = %s AND user_id = %s "
                        "AND row_idx = %s AND kind = 'tag'"
                    ).format(tbl=sql.Identifier("user_annotations")),
                    (version_id, user_id, row_idx),
                )
                return cur.rowcount or 0
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "DELETE FROM {tbl} WHERE version_id = %s AND user_id = %s "
                    "AND row_idx = %s AND kind = 'tag' AND value = %s"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, user_id, row_idx, value),
            )
            return cur.rowcount or 0

    def insert_note(self, *, version_id: int, user_id: str, row_idx: int, value: str) -> int:
        try:
            with self._conn.transaction() as conn, conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {tbl} (version_id, user_id, row_idx, kind, value) "
                        "VALUES (%s, %s, %s, 'note', %s) RETURNING id"
                    ).format(tbl=sql.Identifier("user_annotations")),
                    (version_id, user_id, row_idx, value),
                )
                row = cur.fetchone()
        except Exception as exc:
            raise MetadataWriteFailed(table="user_annotations", reason=str(exc)) from exc
        return int(row["id"]) if row else -1

    def list_annotations(
        self,
        *,
        version_id: int,
        user_id: str | None = None,
        row_idx: int | None = None,
        kind: AnnotationKind | None = None,
    ) -> list[AnnotationRow]:
        """List annotations, optionally filtered.

        Phase-1 semantics: when *user_id* is None, no filter is applied
        (MVP is single-user — isolation arrives in phase 2). The SDK
        passes ``user_id=None`` for read paths and the calling user's id
        for write paths.
        """
        clauses = ["version_id = %s"]
        params: list[Any] = [version_id]
        if user_id is not None:
            clauses.append("user_id = %s")
            params.append(user_id)
        if row_idx is not None:
            clauses.append("row_idx = %s")
            params.append(row_idx)
        if kind is not None:
            clauses.append("kind = %s")
            params.append(kind)
        where = sql.SQL(" AND ").join(sql.SQL(c) for c in clauses)
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT id, version_id, user_id, row_idx, kind, value, created_at "
                "FROM {tbl} WHERE {where} ORDER BY row_idx ASC, id ASC"
            ).format(tbl=sql.Identifier("user_annotations"), where=where),
            tuple(params),
        )
        return [
            AnnotationRow(
                id=r["id"],
                version_id=r["version_id"],
                user_id=r["user_id"],
                row_idx=r["row_idx"],
                kind=r["kind"],
                value=r["value"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def row_indices_for_tag(self, *, version_id: int, user_id: str | None, value: str) -> list[int]:
        if user_id is None:
            rows = self._conn.fetchall(
                sql.SQL(
                    "SELECT DISTINCT row_idx FROM {tbl} "
                    "WHERE version_id = %s AND kind = 'tag' AND value = %s "
                    "ORDER BY row_idx"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, value),
            )
        else:
            rows = self._conn.fetchall(
                sql.SQL(
                    "SELECT DISTINCT row_idx FROM {tbl} "
                    "WHERE version_id = %s AND user_id = %s AND kind = 'tag' AND value = %s "
                    "ORDER BY row_idx"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, user_id, value),
            )
        return [r["row_idx"] for r in rows]

    def row_indices_for_tags_any(
        self, *, version_id: int, user_id: str | None, values: list[str]
    ) -> set[int]:
        if not values:
            return set()
        if user_id is None:
            rows = self._conn.fetchall(
                sql.SQL(
                    "SELECT DISTINCT row_idx FROM {tbl} "
                    "WHERE version_id = %s AND kind = 'tag' AND value = ANY(%s)"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, list(values)),
            )
        else:
            rows = self._conn.fetchall(
                sql.SQL(
                    "SELECT DISTINCT row_idx FROM {tbl} "
                    "WHERE version_id = %s AND user_id = %s AND kind = 'tag' AND value = ANY(%s)"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, user_id, list(values)),
            )
        return {r["row_idx"] for r in rows}

    def count_annotations(self, *, version_id: int, kind: AnnotationKind | None = None) -> int:
        if kind is None:
            row = self._conn.fetchone(
                sql.SQL("SELECT COUNT(*) AS n FROM {tbl} WHERE version_id = %s").format(
                    tbl=sql.Identifier("user_annotations")
                ),
                (version_id,),
            )
        else:
            row = self._conn.fetchone(
                sql.SQL(
                    "SELECT COUNT(*) AS n FROM {tbl} WHERE version_id = %s AND kind = %s"
                ).format(tbl=sql.Identifier("user_annotations")),
                (version_id, kind),
            )
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------- file_stats

    def bulk_upsert_file_stats(
        self,
        *,
        version_id: int,
        rows: Iterator[tuple[str, str, Any, Any, int]],
    ) -> int:
        """Upsert ``(file_path, field_path, min, max, row_count)`` rows.

        Used at registration time to record per-file min/max for top-level
        scalar fields.
        """
        count = 0

        def _rows() -> Iterator[tuple[int, str, str, Any, Any, int]]:
            nonlocal count
            for file_path, field_path, mn, mx, rc in rows:
                count += 1
                yield (version_id, file_path, field_path, Jsonb(mn), Jsonb(mx), rc)

        with self._conn.transaction() as conn:
            with conn.cursor() as cc:
                with cc.copy(
                    sql.SQL(
                        "COPY {tbl} (version_id, file_path, field_path, min_value, max_value, row_count) "
                        "FROM STDIN"
                    ).format(tbl=sql.Identifier("file_stats"))
                ) as cp:
                    for row in _rows():
                        cp.write_row(row)
        return count

    def list_file_stats(self, *, version_id: int) -> list[FileStatRow]:
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT version_id, file_path, field_path, min_value, max_value, row_count "
                "FROM {tbl} WHERE version_id = %s ORDER BY file_path, field_path"
            ).format(tbl=sql.Identifier("file_stats")),
            (version_id,),
        )
        return [
            FileStatRow(
                version_id=r["version_id"],
                file_path=r["file_path"],
                field_path=r["field_path"],
                min_value=r["min_value"],
                max_value=r["max_value"],
                row_count=r["row_count"],
            )
            for r in rows
        ]

    # -------------------------------------------------------------- field_index

    def bulk_insert_field_index(
        self,
        *,
        version_id: int,
        field_path: str,
        rows: Iterator[tuple[int, Any]],
    ) -> int:
        """Bulk-insert (row_idx, value) tuples into field_index for a version + field.

        Returns the number of inserted rows. Uses COPY for throughput.
        """
        count = 0

        def _rows() -> Iterator[tuple[int, str, int, Any]]:
            nonlocal count
            for row_idx, value in rows:
                count += 1
                yield (version_id, field_path, row_idx, Jsonb(value))

        self._conn.copy_expert(
            sql.SQL("COPY {tbl} (version_id, field_path, row_idx, value) FROM STDIN").format(
                tbl=sql.Identifier("field_index")
            ),
            _rows(),
        )
        return count

    def delete_field_index(self, *, version_id: int, field_path: str) -> int:
        """Delete all field_index entries for a version + field.

        Returns the number of deleted rows.
        """
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM {tbl} WHERE version_id = %s AND field_path = %s").format(
                    tbl=sql.Identifier("field_index")
                ),
                (version_id, field_path),
            )
            return cur.rowcount or 0

    def list_indexed_fields(self, *, version_id: int) -> list[str]:
        """Return the list of field paths that have indexes for this version."""
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT DISTINCT field_path FROM {tbl} WHERE version_id = %s ORDER BY field_path"
            ).format(tbl=sql.Identifier("field_index")),
            (version_id,),
        )
        return [r["field_path"] for r in rows]

    def row_indices_for_field_value(
        self,
        *,
        version_id: int,
        field_path: str,
        value: Any,
    ) -> set[int]:
        """Return row_idx where the indexed field equals value."""
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT row_idx FROM {tbl} "
                "WHERE version_id = %s AND field_path = %s AND value = %s::jsonb"
            ).format(tbl=sql.Identifier("field_index")),
            (version_id, field_path, Jsonb(value)),
        )
        return {r["row_idx"] for r in rows}

    def row_indices_for_field_in(
        self,
        *,
        version_id: int,
        field_path: str,
        values: list[Any],
    ) -> set[int]:
        """Return row_idx where the indexed field is in the value list."""
        if not values:
            return set()
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT row_idx FROM {tbl} "
                "WHERE version_id = %s AND field_path = %s AND value = ANY(%s::jsonb[])"
            ).format(tbl=sql.Identifier("field_index")),
            (version_id, field_path, [Jsonb(v) for v in values]),
        )
        return {r["row_idx"] for r in rows}

    def row_indices_for_field_range(
        self,
        *,
        version_id: int,
        field_path: str,
        min_value: Any | None = None,
        max_value: Any | None = None,
        include_min: bool = True,
        include_max: bool = True,
    ) -> set[int]:
        """Return row_idx where the indexed field is in a range."""
        clauses = ["version_id = %s", "field_path = %s"]
        params: list[Any] = [version_id, field_path]

        if min_value is not None:
            op = ">=" if include_min else ">"
            clauses.append(f"value {op} %s::jsonb")
            params.append(Jsonb(min_value))

        if max_value is not None:
            op = "<=" if include_max else "<"
            clauses.append(f"value {op} %s::jsonb")
            params.append(Jsonb(max_value))

        where = sql.SQL(" AND ").join(sql.SQL(c) for c in clauses)
        rows = self._conn.fetchall(
            sql.SQL("SELECT row_idx FROM {tbl} WHERE {where}").format(
                tbl=sql.Identifier("field_index"),
                where=where,
            ),
            tuple(params),
        )
        return {r["row_idx"] for r in rows}

    def prune_files_for_field(
        self,
        *,
        version_id: int,
        field_path: str,
        min_value: Any | None = None,
        max_value: Any | None = None,
        exact_value: Any | None = None,
    ) -> set[str]:
        """Return file_paths that *might* contain matches (prune impossible files).

        Uses file_stats.min/max to skip files where the filter is guaranteed to miss.
        If exact_value is provided, min/max are ignored.
        """
        clauses = ["version_id = %s", "field_path = %s"]
        params: list[Any] = [version_id, field_path]

        if exact_value is not None:
            # Exact match: file's min <= value <= max
            clauses.append("min_value <= %s::jsonb")
            clauses.append("max_value >= %s::jsonb")
            params.extend([Jsonb(exact_value), Jsonb(exact_value)])
        else:
            if min_value is not None:
                clauses.append("max_value >= %s::jsonb")
                params.append(Jsonb(min_value))
            if max_value is not None:
                clauses.append("min_value <= %s::jsonb")
                params.append(Jsonb(max_value))

        where = sql.SQL(" AND ").join(sql.SQL(c) for c in clauses)
        rows = self._conn.fetchall(
            sql.SQL("SELECT DISTINCT file_path FROM {tbl} WHERE {where}").format(
                tbl=sql.Identifier("file_stats"),
                where=where,
            ),
            tuple(params),
        )
        return {r["file_path"] for r in rows}

    # -------------------------------------------------------------- housekeeping

    def truncate_all(self) -> None:
        """Truncate every metadata table. Used by the test session fixture."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            # First check what tables exist
            cur.execute(sql.SQL("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            existing = {row["tablename"] for row in cur.fetchall()}

            # Build the truncate statement with only existing tables
            tables = []
            if "user_annotations" in existing:
                tables.append(sql.Identifier("user_annotations"))
            if "row_sources" in existing:
                tables.append(sql.Identifier("row_sources"))
            if "file_stats" in existing:
                tables.append(sql.Identifier("file_stats"))
            if "field_index" in existing:
                tables.append(sql.Identifier("field_index"))
            if "parquet_caches" in existing:
                tables.append(sql.Identifier("parquet_caches"))
            if "dataset_versions" in existing:
                tables.append(sql.Identifier("dataset_versions"))
            if "datasets" in existing:
                tables.append(sql.Identifier("datasets"))

            if tables:
                cur.execute(
                    sql.SQL("TRUNCATE {tables} RESTART IDENTITY CASCADE").format(
                        tables=sql.SQL(", ").join(tables)
                    )
                )

    def ping(self) -> bool:
        row = self._conn.fetchone(sql.SQL("SELECT 1 AS v"))
        return bool(row and row["v"] == 1)

    def bulk_insert_annotations(
        self,
        *,
        rows: Iterator[tuple[int, str, int, str, str]],
    ) -> int:
        """Bulk insert annotations for F22 tag/index inheritance."""
        count = 0
        def _row_iter() -> Iterator[tuple[int, str, int, str, str]]:
            nonlocal count
            for version_id, user_id, row_idx, kind, value in rows:
                count += 1
                yield (version_id, user_id, row_idx, kind, value)
        with self._conn.transaction() as conn:
            with conn.cursor() as cur:
                with cur.copy(
                    sql.SQL("COPY user_annotations (version_id, user_id, row_idx, kind, value) FROM STDIN")
                ) as copy:
                    for row in _row_iter():
                        copy.write_row(row)
        return count

    def insert_parquet_cache(
        self,
        *,
        version_id: int,
        field_path: str | None,
        cache_file_path: str,
        cache_kind: str,
        row_count: int,
        file_count: int,
    ) -> int:
        """Insert a Parquet cache entry."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO parquet_caches (version_id, field_path, cache_file_path, cache_kind, row_count, file_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
                ),
                (version_id, field_path, cache_file_path, cache_kind, row_count, file_count),
            )
            r = cur.fetchone()
            return int(r["id"]) if r else -1

    def list_parquet_caches(self, *, version_id: int) -> list[tuple[int, str | None, str, str, int, int, Any, Any]]:
        """List Parquet caches for a version."""
        # First check if the table exists
        with self._conn.connection.cursor() as cur:
            cur.execute(sql.SQL("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'parquet_caches'"))
            if not cur.fetchone():
                return []
        # Table exists, query it
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT id, field_path, cache_file_path, cache_kind, row_count, file_count, created_at, last_used_at "
                "FROM parquet_caches WHERE version_id = %s ORDER BY created_at DESC"
            ),
            (version_id,),
        )
        return [
            (r["id"], r["field_path"], r["cache_file_path"], r["cache_kind"],
             r["row_count"], r["file_count"], r["created_at"], r["last_used_at"])
            for r in rows
        ]

    def delete_parquet_cache(self, *, cache_id: int) -> int:
        """Delete a Parquet cache entry."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM parquet_caches WHERE id = %s"),
                (cache_id,),
            )
            return cur.rowcount or 0

    def touch_parquet_cache(self, *, cache_id: int) -> None:
        """Update last_used_at for a cache."""
        self._conn.execute(
            sql.SQL("UPDATE parquet_caches SET last_used_at = now() WHERE id = %s"),
            (cache_id,),
        )

    def delete_parquet_caches_for_version(self, *, version_id: int) -> int:
        """Delete all caches for a version."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM parquet_caches WHERE version_id = %s"),
                (version_id,),
            )
            return cur.rowcount or 0
