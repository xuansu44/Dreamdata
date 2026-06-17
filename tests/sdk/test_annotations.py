"""L3 SDK integration — F3 tag + F4 note."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.errors import RowIndexOutOfRange, TagValueInvalid
from dreamdata.sdk import Engine


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _build(engine: Engine, tmp_path: Path, unique_name: str, n: int = 5) -> object:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": i} for i in range(n)])
    return engine.register_dataset(unique_name, [src])


def test_tag_single_row_single_value(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag(0, "good")
    tags = ds.tags()
    assert tags == [(0, "good")]


def test_tag_multiple_rows_multiple_values(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag([0, 1, 2], ["a", "b"])
    pairs = set(ds.tags())
    assert pairs == {
        (0, "a"),
        (0, "b"),
        (1, "a"),
        (1, "b"),
        (2, "a"),
        (2, "b"),
    }


def test_tag_is_idempotent(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag(0, "x")
    ds.tag(0, "x")
    assert ds.tags() == [(0, "x")]


def test_tag_filter_by_row(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag([0, 1, 2], "t")
    assert ds.tags(row_idx=1) == [(1, "t")]


def test_remove_tag_specific_value(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag(0, ["a", "b"])
    n = ds.remove_tag(0, "a")
    assert n == 1
    assert ds.tags(row_idx=0) == [(0, "b")]


def test_remove_tag_all_values(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    ds.tag(0, ["a", "b"])
    n = ds.remove_tag(0)
    assert n == 2
    assert ds.tags(row_idx=0) == []


def test_tag_out_of_range_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name, n=3)
    with pytest.raises(RowIndexOutOfRange):
        ds.tag(5, "x")
    with pytest.raises(RowIndexOutOfRange):
        ds.tag(-1, "x")


def test_tag_value_normalised_to_nfc(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Tag values stored as NFC unicode normal form."""
    ds = _build(engine, tmp_path, unique_name)
    # NFD form of "é" — e + combining acute
    nfd = "é"
    ds.tag(0, nfd)
    stored = ds.tags(row_idx=0)
    assert stored == [(0, "é")]
    # NFC normalised


def test_tag_value_rejects_too_long(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    too_long = "x" * (ds._engine._settings.tag_value_max_bytes + 1)
    with pytest.raises(TagValueInvalid):
        ds.tag(0, too_long)


def test_tag_value_rejects_null_byte(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    with pytest.raises(TagValueInvalid):
        ds.tag(0, "bad\x00value")


def test_note_single_row(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    nid = ds.note(0, "first note")
    assert nid > 0
    notes = ds.notes()
    assert notes == [(nid, 0, "first note")]


def test_note_filter_by_row(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    n1 = ds.note(0, "first")
    n2 = ds.note(1, "second")
    notes = ds.notes(row_idx=1)
    assert notes == [(n2, 1, "second")]


def test_note_supports_unicode(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name)
    nid = ds.note(0, "你好世界")
    notes = ds.notes()
    assert notes == [(nid, 0, "你好世界")]


def test_note_out_of_range_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    ds = _build(engine, tmp_path, unique_name, n=3)
    with pytest.raises(RowIndexOutOfRange):
        ds.note(5, "x")


def test_annotation_isolation_by_user_id(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Annotations for one user do not leak to another."""
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    ds = engine.register_dataset(unique_name, [src])
    ds.tag(0, "user_a_tag")

    # Switch user
    from dreamdata.config import Settings
    from dreamdata.sdk import Engine as EngineCls

    other_settings = Settings(
        database_url=engine._settings.database_url.get_secret_value(),
        workspace_path=engine._settings.workspace_path,
        user_id=engine._settings.user_id + "_other",
    )
    other_engine = EngineCls(settings=other_settings)
    try:
        ds_other = other_engine.open_dataset(unique_name)
        # Phase 2: user isolation is enabled — other user CANNOT see the tag
        # unless they explicitly request all users with user_id="*"
        assert ds_other.tags() == []
        # But they CAN see it with user_id="*"
        assert ds_other.tags(user_id="*") == [(0, "user_a_tag")]
    finally:
        other_engine.close()
