"""L1 — Field-path parser and traversal."""

from __future__ import annotations

import pytest

from dreamdata.errors import FieldPathInvalid
from dreamdata.fields import (
    infer_fields,
    is_missing,
    parse_field_path,
    traverse_field_path,
)


@pytest.mark.parametrize(
    "path,expected_kinds",
    [
        ("a", [("key", "a")]),
        ("a.b", [("key", "a"), ("key", "b")]),
        ("a.0.b", [("key", "a"), ("index", 0), ("key", "b")]),
        ("messages.0.role", [("key", "messages"), ("index", 0), ("key", "role")]),
        ("tags.5", [("key", "tags"), ("index", 5)]),
        ("metadata.source.url", [("key", "metadata"), ("key", "source"), ("key", "url")]),
    ],
)
def test_parse_valid_paths(path: str, expected_kinds: list[tuple[str, object]]) -> None:
    tokens = parse_field_path(path)
    assert [(t.kind, t.value) for t in tokens] == expected_kinds


@pytest.mark.parametrize(
    "bad_path,reason_match",
    [
        ("", "empty"),
        (".", "leading or trailing"),
        (".a", "leading or trailing"),
        ("a.", "leading or trailing"),
        ("a..b", "empty path segment"),
        ("a.-1", "negative array index"),
        ("a.01", "zero-padded"),
        ("a\x00b", "null byte"),
    ],
)
def test_parse_invalid_paths(bad_path: str, reason_match: str) -> None:
    with pytest.raises(FieldPathInvalid) as exc_info:
        parse_field_path(bad_path)
    assert reason_match in exc_info.value.context["reason"]


def test_traverse_top_level_key() -> None:
    tokens = parse_field_path("id")
    assert traverse_field_path({"id": 7}, tokens) == 7


def test_traverse_nested_keys() -> None:
    tokens = parse_field_path("metadata.source")
    assert traverse_field_path({"metadata": {"source": "x"}}, tokens) == "x"


def test_traverse_array_index() -> None:
    tokens = parse_field_path("messages.0.role")
    obj = {"messages": [{"role": "user"}, {"role": "assistant"}]}
    assert traverse_field_path(obj, tokens) == "user"


def test_traverse_missing_key_returns_missing_sentinel() -> None:
    tokens = parse_field_path("a.b.c")
    assert is_missing(traverse_field_path({"a": {}}, tokens))


def test_traverse_missing_array_index_returns_missing_sentinel() -> None:
    tokens = parse_field_path("a.5")
    assert is_missing(traverse_field_path({"a": [0, 1]}, tokens))


def test_traverse_null_intermediate_returns_missing() -> None:
    tokens = parse_field_path("a.b")
    assert is_missing(traverse_field_path({"a": None}, tokens))


def test_traverse_index_into_non_list_raises() -> None:
    tokens = parse_field_path("a.0")
    with pytest.raises(FieldPathInvalid) as exc_info:
        traverse_field_path({"a": "not-a-list"}, tokens)
    assert "non-list" in exc_info.value.context["reason"]


def test_traverse_key_into_non_dict_raises() -> None:
    tokens = parse_field_path("a.b")
    with pytest.raises(FieldPathInvalid) as exc_info:
        traverse_field_path({"a": ["not-a-dict"]}, tokens)
    assert "non-object" in exc_info.value.context["reason"]


def test_infer_fields_top_level_only() -> None:
    rows = [{"id": 0, "name": "x"}, {"id": 1, "name": "y", "extra": True}]
    inferred = infer_fields(rows)
    assert inferred == ["extra", "id", "name"]


def test_infer_fields_nested_with_array_index() -> None:
    rows = [
        {
            "messages": [
                {"role": "user", "text": "hi"},
                {"role": "assistant", "text": "hello"},
            ]
        }
    ]
    inferred = infer_fields(rows)
    assert "messages" in inferred
    assert "messages.0" in inferred
    assert "messages.1" in inferred
    assert "messages.0.role" in inferred
    assert "messages.0.text" in inferred
    assert "messages.1.role" in inferred


def test_infer_fields_handles_empty_and_missing_gracefully() -> None:
    rows: list[object] = [{}, {"a": None}, {"b": []}]
    inferred = infer_fields(rows)
    assert "a" in inferred
    assert "b" in inferred
