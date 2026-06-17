"""Read engine — JSONL scan + advanced field filters (phase 2).

Phase-2 strategy: Python JSONL streaming with support for advanced filters
(regex, range, IN, etc.), plus index pruning via file_stats and field_index.

DuckDB will return in later phases for Parquet cache paths.

The DataFrame schema returned to the SDK is always
``(file_idx, row_idx, data)`` where ``data`` is the raw JSON value.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from dreamdata.errors import EngineResourceExhausted, ScanFailed
from dreamdata.fields import is_missing, parse_field_path, traverse_field_path

FilterValue = str | int | float | bool | None


class FilterOp(Enum):
    """Supported filter operations."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    IN = "in"
    NOT_IN = "not_in"
    REGEX = "regex"
    NOT_REGEX = "not_regex"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


@dataclass(slots=True, frozen=True)
class FieldFilter:
    """Filter on a dotted field path. Backward compatible: defaults to equality."""

    path: str
    value: FilterValue | Sequence[FilterValue] | None = None
    op: FilterOp = FilterOp.EQ

    def __post_init__(self) -> None:
        parse_field_path(self.path)
        # Validate op/value compatibility
        if self.op in (FilterOp.IS_NULL, FilterOp.IS_NOT_NULL):
            if self.value is not None:
                raise ValueError(f"{self.op} takes no value")
        elif self.op in (FilterOp.IN, FilterOp.NOT_IN):
            if not isinstance(self.value, (list, tuple)):
                raise ValueError(f"{self.op} requires a list/tuple value")
        elif self.op in (FilterOp.REGEX, FilterOp.NOT_REGEX):
            if not isinstance(self.value, str):
                raise ValueError(f"{self.op} requires a string value")
        # EQ, NE, GT, GE, LT, LE take single values
        elif isinstance(self.value, (list, tuple)):
            raise ValueError(f"{self.op} takes a single value")


@dataclass(slots=True, frozen=True)
class FilterCombination:
    """Boolean combination of filters."""

    kind: str  # "and" or "or"
    filters: Sequence[FieldFilter | FilterCombination]


def eq_filter(path: str, value: FilterValue) -> FieldFilter:
    """Create an equality filter."""
    return FieldFilter(path=path, value=value, op=FilterOp.EQ)


def in_filter(path: str, values: Sequence[FilterValue]) -> FieldFilter:
    """Create an IN filter."""
    return FieldFilter(path=path, value=list(values), op=FilterOp.IN)


def range_filter(
    path: str,
    min_value: FilterValue | None = None,
    max_value: FilterValue | None = None,
    include_min: bool = True,
    include_max: bool = True,
) -> FilterCombination | FieldFilter:
    """Create a range filter (>= min and <= max)."""
    filters: list[FieldFilter] = []
    if min_value is not None:
        op = FilterOp.GE if include_min else FilterOp.GT
        filters.append(FieldFilter(path=path, value=min_value, op=op))
    if max_value is not None:
        op = FilterOp.LE if include_max else FilterOp.LT
        filters.append(FieldFilter(path=path, value=max_value, op=op))
    if len(filters) == 1:
        return filters[0]
    return FilterCombination(kind="and", filters=filters)


def regex_filter(path: str, pattern: str) -> FieldFilter:
    """Create a regex match filter."""
    return FieldFilter(path=path, value=pattern, op=FilterOp.REGEX)


def and_filter(*filters: FieldFilter | FilterCombination) -> FilterCombination:
    """Create an AND combination of filters."""
    return FilterCombination(kind="and", filters=list(filters))


def or_filter(*filters: FieldFilter | FilterCombination) -> FilterCombination:
    """Create an OR combination of filters."""
    return FilterCombination(kind="or", filters=list(filters))


@dataclass(slots=True, frozen=True)
class ScanResult:
    """Materialised scan result."""

    df: pd.DataFrame
    row_count: int


class DuckDBEngine:
    """Read engine — Python JSONL streaming with field-path filters.

    Named ``DuckDBEngine`` for forward-compatibility with the planned
    Phase-2 columnar path; the current implementation uses Python only.
    """

    __slots__ = ("_memory_limit", "_threads")

    def __init__(
        self,
        *,
        memory_limit: str | None = None,
        threads: int | None = None,
    ) -> None:
        # Validate the parameters even though the Python path doesn't use
        # them — keeping the surface stable for Phase 2.
        if memory_limit is not None and not isinstance(memory_limit, str):
            raise EngineResourceExhausted(resource="memory_limit", limit=str(memory_limit))
        if threads is not None and (not isinstance(threads, int) or threads < 1):
            raise EngineResourceExhausted(resource="threads", limit=str(threads))
        self._memory_limit = memory_limit
        self._threads = threads

    def close(self) -> None:
        return None

    @property
    def connection(self) -> Any:
        return None

    def scan_jsonl(
        self,
        *,
        files: list[Path],
        field_filter: FieldFilter | FilterCombination | None = None,
        row_indices: set[int] | None = None,
        row_indices_per_file: dict[int, set[int]] | None = None,
        limit: int | None = None,
    ) -> ScanResult:
        """Scan *files* (absolute paths) and return matched rows.

        The DataFrame schema is always ``(file_idx, row_idx, data)``.
        ``row_idx`` is the per-file logical row index in source order.
        """
        if not files:
            return ScanResult(df=self._empty_frame(), row_count=0)

        out_file_idx: list[int] = []
        out_row_idx: list[int] = []
        out_data: list[Any] = []

        for file_idx, file_path in enumerate(files):
            allowed_rows: set[int] | None = None
            if row_indices is not None:
                allowed_rows = row_indices
            if row_indices_per_file is not None:
                per_file = row_indices_per_file.get(file_idx)
                if per_file is None:
                    continue
                allowed_rows = per_file if allowed_rows is None else (allowed_rows & per_file)

            try:
                with file_path.open("rb") as fh:
                    for row_idx, line_bytes in enumerate(fh):
                        if allowed_rows is not None and row_idx not in allowed_rows:
                            continue
                        line = line_bytes.rstrip(b"\r\n")
                        if not line:
                            continue
                        try:
                            value = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ScanFailed(file=str(file_path), reason=str(exc)) from exc
                        if field_filter is not None:
                            if not self._matches_filter(value, field_filter):
                                continue
                        out_file_idx.append(file_idx)
                        out_row_idx.append(row_idx)
                        out_data.append(value)
                        if limit is not None and len(out_row_idx) >= int(limit):
                            return self._build_result(out_file_idx, out_row_idx, out_data)
            except OSError as exc:
                raise ScanFailed(file=str(file_path), reason=str(exc)) from exc

        return self._build_result(out_file_idx, out_row_idx, out_data)

    def _matches_filter(self, value: object, filter: FieldFilter | FilterCombination) -> bool:
        """Return True if the value matches the filter."""
        if isinstance(filter, FilterCombination):
            if filter.kind == "and":
                return all(self._matches_filter(value, f) for f in filter.filters)
            elif filter.kind == "or":
                return any(self._matches_filter(value, f) for f in filter.filters)
            else:
                raise ValueError(f"Unknown combination kind: {filter.kind}")

        # Single FieldFilter
        tokens = parse_field_path(filter.path)
        leaf = traverse_field_path(value, tokens)
        missing = is_missing(leaf)

        if filter.op == FilterOp.EQ:
            return not missing and leaf == filter.value
        elif filter.op == FilterOp.NE:
            return not missing and leaf != filter.value
        elif filter.op == FilterOp.GT:
            if missing or filter.value is None:
                return False
            try:
                return bool(leaf > filter.value)  # type: ignore[operator]
            except TypeError:
                return False
        elif filter.op == FilterOp.GE:
            if missing or filter.value is None:
                return False
            try:
                return bool(leaf >= filter.value)  # type: ignore[operator]
            except TypeError:
                return False
        elif filter.op == FilterOp.LT:
            if missing or filter.value is None:
                return False
            try:
                return bool(leaf < filter.value)  # type: ignore[operator]
            except TypeError:
                return False
        elif filter.op == FilterOp.LE:
            if missing or filter.value is None:
                return False
            try:
                return bool(leaf <= filter.value)  # type: ignore[operator]
            except TypeError:
                return False
        elif filter.op == FilterOp.IN:
            if missing:
                return False
            assert isinstance(filter.value, (list, tuple))
            return leaf in filter.value
        elif filter.op == FilterOp.NOT_IN:
            if missing:
                return True
            assert isinstance(filter.value, (list, tuple))
            return leaf not in filter.value
        elif filter.op == FilterOp.REGEX:
            if missing or not isinstance(leaf, str):
                return False
            assert isinstance(filter.value, str)
            try:
                return bool(re.search(filter.value, leaf))
            except re.error:
                return False
        elif filter.op == FilterOp.NOT_REGEX:
            if missing or not isinstance(leaf, str):
                return True
            assert isinstance(filter.value, str)
            try:
                return not bool(re.search(filter.value, leaf))
            except re.error:
                return True
        elif filter.op == FilterOp.IS_NULL:
            return leaf is None or missing
        elif filter.op == FilterOp.IS_NOT_NULL:
            return not (leaf is None or missing)
        else:
            raise ValueError(f"Unknown filter op: {filter.op}")

    def _build_result(
        self,
        file_indices: list[int],
        row_indices: list[int],
        data: list[Any],
    ) -> ScanResult:
        if not row_indices:
            return ScanResult(df=self._empty_frame(), row_count=0)
        df = pd.DataFrame(
            {
                "file_idx": file_indices,
                "row_idx": row_indices,
                "data": data,
            }
        )
        df["file_idx"] = df["file_idx"].astype("int64")
        df["row_idx"] = df["row_idx"].astype("int64")
        return ScanResult(df=df, row_count=len(df))

    def _empty_frame(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["file_idx", "row_idx", "data"])
