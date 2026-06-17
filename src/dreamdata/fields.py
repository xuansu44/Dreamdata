"""Field-path parser and field inference helpers.

Field paths use dotted notation with numeric array indices::

    messages.0.role
    metadata.source
    tags.5

This module owns the parser and the JSON-value traversal logic. The
parser is strict — invalid paths raise :class:`FieldPathInvalid` with a
specific reason so callers can surface the failure to the user.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from dreamdata.errors import FieldPathInvalid


@dataclass(slots=True, frozen=True)
class PathToken:
    """One token in a parsed field path."""

    kind: str  # "key" or "index"
    value: str | int


def parse_field_path(path: str) -> list[PathToken]:
    """Parse a dotted field path into tokens.

    >>> parse_field_path("messages.0.role")
    [PathToken('key', 'messages'), PathToken('index', 0), PathToken('key', 'role')]

    Raises :class:`FieldPathInvalid` on:
    - empty path
    - leading/trailing dot
    - empty segment
    - non-numeric segment used as an array index on a non-array value
      (detected at traversal time, not here)
    - negative or zero-padded numeric segments ("0" is fine, "00" is not)
    """
    if not isinstance(path, str) or path == "":
        raise FieldPathInvalid(path=str(path), reason="empty field path")
    if path.startswith(".") or path.endswith("."):
        raise FieldPathInvalid(path=path, reason="leading or trailing dot")
    if "\x00" in path:
        raise FieldPathInvalid(path=path, reason="null byte in path")

    tokens: list[PathToken] = []
    for segment in path.split("."):
        if segment == "":
            raise FieldPathInvalid(path=path, reason="empty path segment")
        if segment.lstrip("-").isdigit():
            if segment.startswith("-"):
                raise FieldPathInvalid(path=path, reason=f"negative array index {segment!r}")
            if len(segment) > 1 and segment.startswith("0"):
                raise FieldPathInvalid(path=path, reason=f"zero-padded array index {segment!r}")
            tokens.append(PathToken(kind="index", value=int(segment)))
        else:
            tokens.append(PathToken(kind="key", value=segment))
    return tokens


def traverse_field_path(value: object, tokens: list[PathToken]) -> object:
    """Walk *value* following *tokens*. Return ``_MISSING`` if any step misses.

    Raises :class:`FieldPathInvalid` on a type mismatch (e.g. indexing a
    non-list, indexing with a string key on a list).
    """
    current: object = value
    for tok in tokens:
        if current is None:
            return _MISSING
        if tok.kind == "index":
            if not isinstance(current, list):
                raise FieldPathInvalid(
                    path=".".join(str(t.value) for t in tokens),
                    reason=f"array index {tok.value!r} on non-list field (got {type(current).__name__})",
                )
            idx = int(tok.value)
            if idx < 0 or idx >= len(current):
                return _MISSING
            current = current[idx]
        else:  # key
            if not isinstance(current, dict):
                raise FieldPathInvalid(
                    path=".".join(str(t.value) for t in tokens),
                    reason=f"key access {tok.value!r} on non-object field (got {type(current).__name__})",
                )
            key = str(tok.value)
            if key not in current:
                return _MISSING
            current = current[key]
    return current


class _Missing:
    """Sentinel returned by :func:`traverse_field_path` when the path misses."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"

    def __bool__(self) -> bool:
        return False


_MISSING = _Missing()


def is_missing(value: object) -> bool:
    """True if *value* is the traversal-missing sentinel."""
    return value is _MISSING


def infer_fields(sample_rows: list[object], *, max_array_walk: int = 50) -> list[str]:
    """Return the union of field paths observed in *sample_rows*.

    Walks each row's JSON structure. Arrays are walked by indexing into
    the first ``max_array_walk`` elements; the discovered child paths use
    numeric indices (``messages.0.role``, ``messages.1.role``) but at the
    schema level we union by ``messages.N.role``-style template — callers
    treat arrays as positionally-addressable.

    Output is sorted lexicographically for deterministic storage.
    """
    discovered: set[str] = set()
    for row in sample_rows:
        _walk_value(row, prefix="", discovered=discovered, max_array_walk=max_array_walk)
    return sorted(discovered)


def _walk_value(
    value: object,
    *,
    prefix: str,
    discovered: set[str],
    max_array_walk: int,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            discovered.add(child_path)
            _walk_value(
                child,
                prefix=child_path,
                discovered=discovered,
                max_array_walk=max_array_walk,
            )
    elif isinstance(value, list):
        for i, child in enumerate(value[:max_array_walk]):
            child_path = f"{prefix}.{i}"
            discovered.add(child_path)
            _walk_value(
                child,
                prefix=child_path,
                discovered=discovered,
                max_array_walk=max_array_walk,
            )


def to_jsonb_literal(value: object) -> str:
    """Render *value* as a PostgreSQL jsonb literal (``$N`` parameter handled by caller).

    Used by ``meta/`` to write ``field_index.value`` and ``file_stats.min_value``.
    Returns the JSON-serialised form; the caller passes it via the parameter
    array as a string and casts ``::jsonb`` at the SQL site.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def iter_top_level_scalar_fields(inferred: list[str]) -> Iterator[str]:
    """Yield only top-level scalar field paths (no ``.`` in them) from *inferred*."""
    for p in inferred:
        if "." not in p:
            yield p


def collect_scalar_fields(value: object, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (field_path, value) for all scalar fields in a value.

    Used for file_stats collection.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            field_path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (str, int, float, bool)) or v is None:
                yield (field_path, v)
            elif isinstance(v, (dict, list)):
                yield from collect_scalar_fields(v, field_path)
    elif isinstance(value, list):
        # For arrays, we only index the first N elements?
        # For now, just skip arrays for file stats
        pass


_ = Any  # keep Any import for typing re-export
