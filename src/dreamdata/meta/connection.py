"""psycopg v3 connection wrapper for the meta layer.

One :class:`MetaConnection` per :class:`dreamdata.sdk.Engine`. The wrapper
owns the lifecycle (open in constructor, close in ``close()``) and exposes
a small surface for the repository: ``execute``, ``executemany``,
``fetchone``, ``fetchall``, ``copy``.

All SQL here uses psycopg v3's parameter binding (``%s``) — no f-strings.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from dreamdata.errors import MetadataWriteFailed


class MetaConnection:
    """Holds one psycopg v3 connection bound to a single Engine instance."""

    __slots__ = ("_conn",)

    def __init__(self, database_url: str) -> None:
        try:
            # autocommit=True so single-statement writes (tag, note, etc.)
            # commit immediately and become visible to other connections
            # (the SDK facade can be called from multiple Engine instances
            # in the same process). Multi-statement operations wrap their
            # work in `with conn.transaction():` to keep atomicity.
            self._conn = psycopg.connect(
                database_url,
                autocommit=True,
                row_factory=dict_row,
                prepare_threshold=10,
            )
        except psycopg.OperationalError as exc:
            raise MetadataWriteFailed(table="<connect>", reason=str(exc)) from exc

    @property
    def connection(self) -> psycopg.Connection[dict[str, Any]]:
        return self._conn

    def close(self) -> None:
        if not self._conn.closed:
            self._conn.close()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        """Yield the underlying connection inside a transaction.

        Commits on normal exit; rolls back on exception. The connection's
        autocommit is False so psycopg implicitly starts a transaction on
        the first statement — this context manager just controls the
        boundary.
        """
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def execute(
        self,
        query: sql.Composed | sql.SQL | str,
        params: tuple[Any, ...] = (),
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(query, params)

    def executemany(
        self,
        query: sql.Composed | sql.SQL | str,
        params_batch: Iterator[tuple[Any, ...]] | list[tuple[Any, ...]],
    ) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(query, params_batch)

    def fetchone(
        self,
        query: sql.Composed | sql.SQL | str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def fetchall(
        self,
        query: sql.Composed | sql.SQL | str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def copy_expert(
        self,
        copy_statement: sql.Composed | sql.SQL | str,
        rows: Iterator[tuple[Any, ...]],
    ) -> None:
        """Bulk-COPY *rows* using *copy_statement* (e.g. ``COPY tbl (...) FROM STDIN``).

        Values are JSON-encoded by psycopg for jsonb columns via :class:`Jsonb`.
        The caller is responsible for serialising the row tuples accordingly.
        """
        try:
            with self._conn.cursor() as cur, cur.copy(copy_statement) as cp:
                for row in rows:
                    cp.write_row(row)
        except psycopg.Error as exc:
            raise MetadataWriteFailed(
                table="<copy>",
                reason=f"{type(exc).__name__}: {exc}",
            ) from exc


def as_jsonb(value: object) -> Jsonb:
    """Wrap *value* for psycopg to render as a ``::jsonb`` parameter."""
    return Jsonb(value)
