"""L4 — Property-based tests for the field-path parser and traversal."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from dreamdata.errors import FieldPathInvalid
from dreamdata.fields import is_missing, parse_field_path, traverse_field_path

_segment = st.one_of(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
    st.integers(min_value=0, max_value=99).map(str),
)


@settings(max_examples=200)
@given(path=st.text(alphabet="abcdefghijklmnopqrstuvwxyz.", min_size=1, max_size=30))
def test_parse_never_crashes(path: str) -> None:
    try:
        tokens = parse_field_path(path)
        assert isinstance(tokens, list)
    except FieldPathInvalid:
        pass  # expected for malformed inputs


@given(segments=st.lists(_segment, min_size=1, max_size=5))
def test_parse_roundtrip(segments: list[str]) -> None:
    path = ".".join(segments)
    try:
        tokens = parse_field_path(path)
        assert [t.value for t in tokens] == [
            (int(s) if s.isdigit() and (s == "0" or not s.startswith("0")) else s) for s in segments
        ]
    except FieldPathInvalid as exc:
        # zero-padded numerics legitimately fail
        assert "zero-padded" in exc.context.get("reason", "") or "negative" in exc.context.get(
            "reason", ""
        )


@given(
    d=st.dictionaries(
        keys=st.text(min_size=1, max_size=3, alphabet="abc"),
        values=st.integers(min_value=0, max_value=10),
        min_size=0,
        max_size=3,
    )
)
def test_traverse_top_level_keys(d: dict) -> None:
    for key, expected in d.items():
        tokens = parse_field_path(key)
        assert traverse_field_path(d, tokens) == expected


@given(arr=st.lists(st.integers(min_value=0, max_value=10), min_size=0, max_size=5))
def test_traverse_array_indices(arr: list) -> None:
    for i in range(len(arr)):
        tokens = parse_field_path(f"x.{i}")
        wrapped = {"x": arr}
        assert traverse_field_path(wrapped, tokens) == arr[i]
    # out-of-bounds returns missing
    tokens = parse_field_path(f"x.{len(arr) + 5}")
    assert is_missing(traverse_field_path({"x": arr}, tokens))
