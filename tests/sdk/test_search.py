"""L3 SDK integration — F5/F6/F7 search paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.sdk import Engine


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _build_dataset(
    engine: Engine,
    tmp_path: Path,
    unique_name: str,
    rows: list[dict],
    src_filename: str = "a.jsonl",
) -> object:
    src = _write_jsonl(tmp_path / src_filename, rows)
    return engine.register_dataset(unique_name, [src])


def test_scan_returns_all_rows(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": i} for i in range(5)])
    df = ds.scan()
    assert len(df) == 5
    assert list(df.columns) == ["row_idx", "data"]
    assert list(df["row_idx"]) == [0, 1, 2, 3, 4]
    assert [r["id"] for r in df["data"]] == [0, 1, 2, 3, 4]


def test_scan_preserves_global_row_idx_across_files(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 2}, {"id": 3}])
    ds = engine.register_dataset(unique_name, [src1, src2])
    df = ds.scan()
    assert list(df["row_idx"]) == [0, 1, 2, 3]
    assert [r["id"] for r in df["data"]] == [0, 1, 2, 3]


def test_search_by_field_top_level_int(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [{"id": 0}, {"id": 1}, {"id": 2}, {"id": 1}],
    )
    df = ds.search_by_field("id", 1)
    assert len(df) == 2
    assert [r["id"] for r in df["data"]] == [1, 1]


def test_search_by_field_top_level_string(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [{"name": "alice"}, {"name": "bob"}, {"name": "alice"}],
    )
    df = ds.search_by_field("name", "alice")
    assert len(df) == 2


def test_search_by_field_top_level_bool(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [{"ok": True}, {"ok": False}, {"ok": True}],
    )
    df = ds.search_by_field("ok", True)
    assert len(df) == 2


def test_search_by_field_nested_path(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [
            {"id": 0, "messages": [{"role": "user"}]},
            {"id": 1, "messages": [{"role": "assistant"}]},
            {"id": 2, "messages": [{"role": "user"}]},
        ],
    )
    df = ds.search_by_field("messages.0.role", "user")
    assert [r["id"] for r in df["data"]] == [0, 2]


def test_search_by_field_returns_empty_for_unmatched(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": 0}])
    df = ds.search_by_field("id", 99)
    assert df.empty


def test_search_by_field_with_unicode_value(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [{"text": "你好"}, {"text": "世界"}, {"text": "你好"}],
    )
    df = ds.search_by_field("text", "你好")
    assert len(df) == 2


def test_search_by_tag_returns_tagged_rows(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": i} for i in range(5)])
    ds.tag([0, 2, 4], "hot")
    df = ds.search_by_tag("hot")
    assert [r["id"] for r in df["data"]] == [0, 2, 4]


def test_search_by_tag_returns_empty_when_no_match(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": 0}])
    df = ds.search_by_tag("missing-tag")
    assert df.empty


def test_combined_search_field_and_tag_intersection(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """F7: combined_search == field_search ∩ tag_search."""
    rows = [{"id": i, "v": "x" if i % 2 == 0 else "y"} for i in range(10)]
    ds = _build_dataset(engine, tmp_path, unique_name, rows)
    # tag rows 0..4 with 't'
    ds.tag([0, 1, 2, 3, 4], "t")

    field_only = ds.search_by_field("v", "x")
    tag_only = ds.search_by_tag("t")
    combined = ds.search(field_path="v", field_value="x", tag="t")

    assert {r["id"] for r in field_only["data"]} == {0, 2, 4, 6, 8}
    assert {r["id"] for r in tag_only["data"]} == {0, 1, 2, 3, 4}
    assert {r["id"] for r in combined["data"]} == {0, 2, 4}


def test_combined_search_with_tag_only(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": i} for i in range(5)])
    ds.tag([1, 3], "t")
    df = ds.search(tag="t")
    assert {r["id"] for r in df["data"]} == {1, 3}


def test_combined_search_with_field_only(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(
        engine,
        tmp_path,
        unique_name,
        [{"id": 0, "v": "a"}, {"id": 1, "v": "b"}, {"id": 2, "v": "a"}],
    )
    df = ds.search(field_path="v", field_value="a")
    assert {r["id"] for r in df["data"]} == {0, 2}


def test_combined_search_rejects_empty_filter(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": 0}])
    with pytest.raises(Exception):
        ds.search()


def test_search_limit_caps_results(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build_dataset(engine, tmp_path, unique_name, [{"id": i} for i in range(10)])
    df = ds.scan(limit=3)
    assert len(df) == 3


def test_search_global_row_idx_alignment_with_row_sources(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Architectural invariant: scan row_idx == row_sources.row_idx, sorted."""
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 2}])
    ds = engine.register_dataset(unique_name, [src1, src2])
    df = ds.scan()
    assert list(df["row_idx"]) == [0, 1, 2]
