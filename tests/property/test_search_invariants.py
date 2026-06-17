"""L4 — Property-based tests with Hypothesis.

Invariants under test:
- register(files) → row_sources count == sum(line counts
- tag(rows) → search(tag) returns exactly those rows
- combined_search(field, tag) == field_search ∩ tag_search (set equality)
- delete(name) → no metadata references it; filesystem dir removed
- rename(old) → search(old) raises; search(new) returns same rows
- overwrite → tag count == 0, note count == 0
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dreamdata.errors import DatasetNotFound
from dreamdata.sdk import Engine


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _fresh_name() -> str:
    return f"p_{uuid.uuid4().hex[:12]}"


# Strategies ------------------------------------------------------------

_safe_names = st.from_regex(r"^[a-zA-Z0-9_]{1,8}$", fullmatch=True)
# Exclude surrogates AND null bytes — PostgreSQL JSONB rejects .
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
    min_size=0,
    max_size=20,
)
_safe_field_values = st.one_of(
    st.integers(min_value=0, max_value=10_000),
    _safe_text,
    st.booleans(),
)


@st.composite
def simple_rows(draw, min_size: int = 0, max_size: int = 30) -> list[dict]:
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    rows: list[dict] = []
    for i in range(n):
        row = {
            "id": i,
            "name": draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5)),
            "v": draw(_safe_field_values),
        }
        rows.append(row)
    return rows


@st.composite
def tagged_dataset(draw):
    rows = draw(simple_rows(min_size=1, max_size=20))
    if not rows:
        return rows, set(), "x"
    n = len(rows)
    indices = draw(
        st.lists(st.integers(min_value=0, max_value=n - 1), min_size=0, max_size=n, unique=True)
    )
    tag = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5))
    return rows, set(indices), tag


# Tests -----------------------------------------------------------------


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=25)
@given(rows=simple_rows(min_size=1, max_size=20))
def test_register_row_count_invariant(engine: Engine, tmp_path: Path, rows: list[dict]) -> None:
    """row_sources count == sum of file line counts."""
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    ds = engine.register_dataset(_fresh_name(), [src])
    assert ds.row_count == len(rows)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=20)
@given(data=tagged_dataset())
def test_tag_search_returns_exactly_tagged_rows(
    engine: Engine, tmp_path: Path, data: tuple
) -> None:
    """tag(rows) → search(tag) returns exactly those rows."""
    rows, indices, tag = data
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    name = _fresh_name()
    ds = engine.register_dataset(name, [src])
    if not indices:
        return
    ds.tag(list(indices), tag)
    df = ds.search_by_tag(tag)
    found_indices = set(df["row_idx"].tolist())
    assert found_indices == set(indices)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=20)
@given(data=tagged_dataset())
def test_combined_search_is_intersection(engine: Engine, tmp_path: Path, data: tuple) -> None:
    """combined_search(field, tag) == field_search ∩ tag_search."""
    rows, indices, tag = data
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    name = _fresh_name()
    ds = engine.register_dataset(name, [src])
    if not indices:
        return
    ds.tag(list(indices), tag)
    field_set = set(ds.search_by_field("v", rows[0]["v"])["row_idx"].tolist())
    tag_set = set(ds.search_by_tag(tag)["row_idx"].tolist())
    combined = set(ds.search(field_path="v", field_value=rows[0]["v"], tag=tag)["row_idx"].tolist())
    assert combined == field_set & tag_set


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=15)
@given(rows=simple_rows(min_size=1, max_size=10))
def test_rename_preserves_data(engine: Engine, tmp_path: Path, rows: list[dict]) -> None:
    """rename(old) → search(old) raises; search(new) returns same rows."""
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    name = _fresh_name()
    ds = engine.register_dataset(name, [src])
    before_ids = [r["id"] for r in ds.scan()["data"]]
    new_name = name + "_new"
    new_ds = engine.rename_dataset(name, new_name)
    after_ids = [r["id"] for r in new_ds.scan()["data"]]
    assert before_ids == after_ids
    with pytest.raises(DatasetNotFound):
        engine.open_dataset(name)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=15)
@given(rows=simple_rows(min_size=1, max_size=10))
def test_overwrite_loses_annotations(engine: Engine, tmp_path: Path, rows: list[dict]) -> None:
    """overwrite → tag count == 0, note count == 0."""
    src1 = _write_jsonl(tmp_path / "a.jsonl", rows)
    name = _fresh_name()
    ds = engine.register_dataset(name, [src1])
    ds.tag(0, "t")
    ds.note(0, "n")
    src2 = _write_jsonl(tmp_path / "b.jsonl", rows)
    ds2 = engine.register_dataset(name, [src2], overwrite=True)
    assert ds2.tags() == []
    assert ds2.notes() == []


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=15)
@given(rows=simple_rows(min_size=1, max_size=10))
def test_delete_removes_everything(engine: Engine, tmp_path: Path, rows: list[dict]) -> None:
    """delete(name) → no metadata references it; filesystem dir removed."""
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    name = _fresh_name()
    engine.register_dataset(name, [src])
    assert (engine.workspace_root / name).exists()
    engine.delete_dataset(name)
    assert name not in engine.list_datasets()
    assert not (engine.workspace_root / name).exists()
    with pytest.raises(DatasetNotFound):
        engine.open_dataset(name)


@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    max_examples=15,
)
@given(name=_safe_names)
def test_invalid_dataset_name_rejected(engine: Engine, tmp_path: Path, name: str) -> None:
    """Valid names per the charset should round-trip through register + delete."""
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    # When the random name collides with an existing dataset (rare but possible),
    # delete first so the test is deterministic across Hypothesis examples.
    try:
        engine.delete_dataset(name)
    except DatasetNotFound:
        pass
    ds = engine.register_dataset(name, [src])
    assert ds.name == name
    engine.delete_dataset(name)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=15)
@given(rows=simple_rows(min_size=1, max_size=5))
def test_search_field_value_not_present_returns_empty(
    engine: Engine, tmp_path: Path, rows: list[dict]
) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", rows)
    ds = engine.register_dataset(_fresh_name(), [src])
    df = ds.search_by_field("id", 9_999_999)
    assert df.empty
