"""Typed exception hierarchy for dreamdata.

Root class :class:`DreamDataError` is abstract — never raised directly.
Subclasses carry named context fields so error messages are machine-readable
and free of secrets (``DATABASE_URL``, raw row content, etc.).
"""

from __future__ import annotations

from typing import Any


class DreamDataError(Exception):
    """Abstract root of the dreamdata error hierarchy.

    Never raised directly. Concrete errors subclass :class:`SdkError`,
    :class:`MetaError`, :class:`EngineError`, or :class:`StorageError` and
    carry their own named context fields.
    """

    __slots__ = ("_context",)

    _context: dict[str, Any]

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        object.__setattr__(self, "_context", dict(context))

    @property
    def context(self) -> dict[str, Any]:
        """Return a defensive copy of the error's context fields."""
        return dict(self._context)

    def __str__(self) -> str:
        ctx = ", ".join(f"{k}={v!r}" for k, v in self._context.items() if v is not None)
        if ctx:
            return f"{super().__str__() or self.__class__.__name__} ({ctx})"
        return super().__str__() or self.__class__.__name__


class SdkError(DreamDataError):
    """Public SDK surface error — user-visible."""


class MetaError(DreamDataError):
    """PostgreSQL metadata layer error — operational."""


class EngineError(DreamDataError):
    """DuckDB scan/query layer error — operational."""


class StorageError(DreamDataError):
    """Filesystem layer error — operational."""


# ---------- SdkError subclasses ----------


class DatasetNotFound(SdkError):
    """Raised when a dataset name does not resolve to a registered dataset."""

    def __init__(self, *, name: str | None = None, **context: Any) -> None:
        super().__init__(f"dataset not found: {name!r}", name=name, **context)


class DatasetAlreadyExists(SdkError):
    """Raised when registering a name that is already taken."""

    def __init__(self, *, name: str, **context: Any) -> None:
        super().__init__(f"dataset already exists: {name!r}", name=name, **context)


class DatasetNameInvalid(SdkError):
    """Raised when a dataset name fails the SDK boundary check."""

    def __init__(self, *, name: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"invalid dataset name {name!r}: {reason}", name=name, reason=reason, **context
        )


class FieldPathInvalid(SdkError):
    """Raised when a dotted field path is malformed or out of bounds."""

    def __init__(self, *, path: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"invalid field path {path!r}: {reason}", path=path, reason=reason, **context
        )


class TagValueInvalid(SdkError):
    """Raised when a tag value fails length / unicode / content validation."""

    def __init__(self, *, value: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"invalid tag value: {reason}", value=_truncate(value), reason=reason, **context
        )


class NoteValueInvalid(SdkError):
    """Raised when a note value fails length / content validation."""

    def __init__(self, *, value: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"invalid note value: {reason}", value=_truncate(value), reason=reason, **context
        )


class FilterInvalid(SdkError):
    """Raised when a search filter is structurally or semantically invalid."""

    def __init__(self, *, filter: Any, reason: str, **context: Any) -> None:
        super().__init__(f"invalid filter: {reason}", filter=repr(filter), reason=reason, **context)


class RowIndexOutOfRange(SdkError):
    """Raised when a row index supplied to a row-level operation is out of range."""

    def __init__(self, *, row_idx: int, row_count: int, **context: Any) -> None:
        super().__init__(
            f"row_idx {row_idx} out of range [0, {row_count})",
            row_idx=row_idx,
            row_count=row_count,
            **context,
        )


class SettingsInvalid(SdkError):
    """Raised when :class:`Settings` validation fails at engine construction."""

    def __init__(self, *, errors: list[str], **context: Any) -> None:
        super().__init__(f"settings invalid: {'; '.join(errors)}", errors=list(errors), **context)


class FileAlreadyRegistered(SdkError):
    """Raised when a JSONL file path is supplied twice in one register call."""

    def __init__(self, *, path: str, **context: Any) -> None:
        super().__init__(f"file already in register list: {path!r}", path=path, **context)


class RegistrationFileError(SdkError):
    """Raised when a supplied register file is missing, unreadable, or invalid JSONL."""

    def __init__(self, *, path: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"registration file error {path!r}: {reason}", path=path, reason=reason, **context
        )


# ---------- MetaError subclasses ----------


class MetadataWriteFailed(MetaError):
    """Raised when a metadata write fails inside the PostgreSQL transaction."""

    def __init__(self, *, table: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"metadata write to {table!r} failed: {reason}", table=table, reason=reason, **context
        )


class MetadataConstraintViolation(MetaError):
    """Raised when a metadata operation violates a uniqueness / FK constraint."""

    def __init__(self, *, constraint: str, detail: str, **context: Any) -> None:
        super().__init__(
            f"metadata constraint {constraint!r} violated: {detail}",
            constraint=constraint,
            detail=detail,
            **context,
        )


# ---------- EngineError subclasses ----------


class ScanFailed(EngineError):
    """Raised when DuckDB fails to scan a file or set of files."""

    def __init__(self, *, file: str | list[str], reason: str, **context: Any) -> None:
        super().__init__(f"scan failed for {file!r}: {reason}", file=file, reason=reason, **context)


class EngineResourceExhausted(EngineError):
    """Raised when DuckDB hits a configured resource limit (memory, threads)."""

    def __init__(self, *, resource: str, limit: str, **context: Any) -> None:
        super().__init__(
            f"engine resource {resource!r} exhausted (limit {limit})",
            resource=resource,
            limit=limit,
            **context,
        )


# ---------- StorageError subclasses ----------


class FileNotReadable(StorageError):
    """Raised when a JSONL file cannot be read (missing, permissions, encoding)."""

    def __init__(self, *, path: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"file not readable {path!r}: {reason}", path=path, reason=reason, **context
        )


class FileNotWritable(StorageError):
    """Raised when a workspace write fails."""

    def __init__(self, *, path: str, reason: str, **context: Any) -> None:
        super().__init__(
            f"file not writable {path!r}: {reason}", path=path, reason=reason, **context
        )


class WorkspaceMisconfigured(StorageError):
    """Raised when the workspace path is missing, wrong type, or unsafe."""

    def __init__(self, *, setting: str, expected: str, **context: Any) -> None:
        super().__init__(
            f"workspace misconfigured: {setting} expected {expected}",
            setting=setting,
            expected=expected,
            **context,
        )


def _truncate(value: str, limit: int = 200) -> str:
    """Return a copy of *value* truncated for safe inclusion in error messages."""
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"
