"""L1 — Error types carry their context fields and never leak secrets."""

from __future__ import annotations

import pytest

from dreamdata.errors import (
    DatasetAlreadyExists,
    DatasetNameInvalid,
    DatasetNotFound,
    DreamDataError,
    EngineError,
    EngineResourceExhausted,
    FieldPathInvalid,
    FileNotReadable,
    FileNotWritable,
    FilterInvalid,
    MetadataConstraintViolation,
    MetadataWriteFailed,
    MetaError,
    NoteValueInvalid,
    RegistrationFileError,
    RowIndexOutOfRange,
    ScanFailed,
    SdkError,
    SettingsInvalid,
    StorageError,
    TagValueInvalid,
    WorkspaceMisconfigured,
)


@pytest.mark.parametrize(
    "exc_cls,kwargs,expected_in_str",
    [
        (DatasetNotFound, {"name": "x"}, "x"),
        (DatasetAlreadyExists, {"name": "y"}, "y"),
        (DatasetNameInvalid, {"name": "../etc/passwd", "reason": "bad"}, "passwd"),
        (FieldPathInvalid, {"path": "a..b", "reason": "empty segment"}, "a..b"),
        (TagValueInvalid, {"value": "too long tag", "reason": "too long"}, "too long"),
        (NoteValueInvalid, {"value": "x" * 5000, "reason": "too long"}, "truncated"),
        (FilterInvalid, {"filter": {"bad": 1}, "reason": "no path"}, "no path"),
        (RowIndexOutOfRange, {"row_idx": 5, "row_count": 3}, "5"),
        (SettingsInvalid, {"errors": ["bad a", "bad b"]}, "bad a"),
        (RegistrationFileError, {"path": "/p", "reason": "missing"}, "missing"),
        (MetadataWriteFailed, {"table": "datasets", "reason": "oops"}, "datasets"),
        (MetadataConstraintViolation, {"constraint": "uniq", "detail": "dup"}, "uniq"),
        (ScanFailed, {"file": "/x", "reason": "boom"}, "/x"),
        (EngineResourceExhausted, {"resource": "memory_limit", "limit": "1GB"}, "1GB"),
        (FileNotReadable, {"path": "/x", "reason": "perm"}, "perm"),
        (FileNotWritable, {"path": "/y", "reason": "no space"}, "no space"),
        (WorkspaceMisconfigured, {"setting": "WORKSPACE_PATH", "expected": "absolute"}, "absolute"),
    ],
)
def test_error_carries_context(exc_cls, kwargs, expected_in_str: str) -> None:
    err = exc_cls(**kwargs)
    assert isinstance(err, DreamDataError)
    assert expected_in_str in str(err)
    ctx = err.context
    for k in kwargs:
        assert k in ctx


def test_error_context_returns_defensive_copy() -> None:
    err = DatasetNotFound(name="x")
    ctx = err.context
    ctx["name"] = "tampered"
    assert err.context["name"] == "x"


def test_tag_value_truncation_keeps_message_bounded() -> None:
    err = TagValueInvalid(value="a" * 10_000, reason="too long")
    s = str(err)
    assert len(s) < 1_000


def test_settings_invalid_aggregates_errors() -> None:
    err = SettingsInvalid(errors=["a", "b", "c"])
    s = str(err)
    assert "a" in s and "b" in s and "c" in s


def test_layer_subclasses_match_class_hierarchy() -> None:
    assert issubclass(SdkError, DreamDataError)
    assert issubclass(MetaError, DreamDataError)
    assert issubclass(EngineError, DreamDataError)
    assert issubclass(StorageError, DreamDataError)
    # public SDK errors are SdkError
    assert issubclass(DatasetNotFound, SdkError)
    assert issubclass(SettingsInvalid, SdkError)
    # operational errors are layer-specific
    assert issubclass(MetadataWriteFailed, MetaError)
    assert issubclass(ScanFailed, EngineError)
    assert issubclass(FileNotReadable, StorageError)
