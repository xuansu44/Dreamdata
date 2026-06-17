"""L2 — DuckDB engine component tests.

No mocks. DuckDB reads real JSONL files written to ``tmp_path``.
We exercise every public scan path and assert architectural invariants
(no business files written).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.engine import DuckDBEngine, FieldFilter


@pytest.fixture()
def eng() -> DuckDBEngine:
    eng = DuckDBEngine()
    yield eng
    eng.close()


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_scan_full_returns_all_rows(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}, {"id": 2}])
    r = eng.scan_jsonl(files=[f])
    assert r.row_count == 3
    assert [row["id"] for row in r.df["data"]] == [0, 1, 2]


def test_scan_field_filter_top_level(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0}, {"id": 1}, {"id": 2}],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="id", value=1))
    assert r.row_count == 1
    assert r.df.iloc[0]["data"]["id"] == 1


def test_scan_field_filter_nested(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [
            {"id": 0, "messages": [{"role": "user"}]},
            {"id": 1, "messages": [{"role": "assistant"}]},
            {"id": 2, "messages": [{"role": "user"}]},
        ],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="messages.0.role", value="user"))
    assert r.row_count == 2
    assert [row["id"] for row in r.df["data"]] == [0, 2]


def test_scan_field_filter_string_value(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"name": "alice"}, {"name": "bob"}, {"name": "alice"}],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="name", value="alice"))
    assert r.row_count == 2


def test_scan_field_filter_bool_value(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"ok": True}, {"ok": False}, {"ok": True}],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="ok", value=True))
    assert r.row_count == 2


def test_scan_field_filter_int_zero(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0}, {"id": 1}, {"id": 0}],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="id", value=0))
    assert r.row_count == 2


def test_scan_field_filter_value_not_present(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="id", value=99))
    assert r.row_count == 0


def test_scan_row_indices(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": i} for i in range(10)])
    r = eng.scan_jsonl(files=[f], row_indices={0, 5, 9})
    assert r.row_count == 3
    assert [row["id"] for row in r.df["data"]] == [0, 5, 9]


def test_scan_row_indices_empty_returns_empty(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    r = eng.scan_jsonl(files=[f], row_indices=set())
    assert r.row_count == 0


def test_scan_multiple_files_preserves_per_file_row_idx(eng: DuckDBEngine, tmp_path: Path) -> None:
    f1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    f2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 100}])
    r = eng.scan_jsonl(files=[f1, f2])
    assert r.row_count == 3
    # file_idx → row_idx pairs are (0,0), (0,1), (1,0)
    pairs = list(zip(r.df["file_idx"].tolist(), r.df["row_idx"].tolist()))
    assert (0, 0) in pairs
    assert (0, 1) in pairs
    assert (1, 0) in pairs


def test_scan_no_files_returns_empty(eng: DuckDBEngine) -> None:
    r = eng.scan_jsonl(files=[])
    assert r.row_count == 0
    assert list(r.df.columns) == ["file_idx", "row_idx", "data"]


def test_scan_limit(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": i} for i in range(100)])
    r = eng.scan_jsonl(files=[f], limit=5)
    assert r.row_count == 5


def test_scan_combined_filter_and_row_indices(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0, "v": "x"}, {"id": 1, "v": "x"}, {"id": 2, "v": "y"}],
    )
    r = eng.scan_jsonl(
        files=[f],
        field_filter=FieldFilter(path="v", value="x"),
        row_indices={0, 2},
    )
    assert r.row_count == 1
    assert r.df.iloc[0]["data"]["id"] == 0


def test_engine_writes_no_business_files(eng: DuckDBEngine, tmp_path: Path) -> None:
    """Architectural invariant: DuckDB never writes business data."""
    f = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    eng.scan_jsonl(files=[f])
    after = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_engine_handles_missing_field_gracefully(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0}, {"id": 1, "name": "x"}],
    )
    # rows without 'name' should not match filter value 'x'
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="name", value="x"))
    assert r.row_count == 1
    assert r.df.iloc[0]["data"]["id"] == 1


def test_engine_handles_unicode_values(eng: DuckDBEngine, tmp_path: Path) -> None:
    f = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"text": "你好"}, {"text": "世界"}, {"text": "你好"}],
    )
    r = eng.scan_jsonl(files=[f], field_filter=FieldFilter(path="text", value="你好"))
    assert r.row_count == 2
