"""L3 SDK integration — F9 rename + F10 overwrite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.errors import DatasetAlreadyExists, DatasetNotFound
from dreamdata.sdk import Engine


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def test_rename_dataset(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    engine.register_dataset(unique_name, [src])
    new_name = unique_name + "_renamed"
    ds = engine.rename_dataset(unique_name, new_name)
    assert ds.name == new_name
    assert unique_name not in engine.list_datasets()
    assert new_name in engine.list_datasets()


def test_rename_moves_workspace_dir(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    old_dir = engine.workspace_root / unique_name
    assert old_dir.exists()
    new_name = unique_name + "_renamed"
    engine.rename_dataset(unique_name, new_name)
    new_dir = engine.workspace_root / new_name
    assert new_dir.exists()
    assert not old_dir.exists()


def test_rename_preserves_search(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0, "v": "x"}, {"id": 1, "v": "y"}],
    )
    ds = engine.register_dataset(unique_name, [src])
    ds.tag(0, "t")
    new_name = unique_name + "_new"
    new_ds = engine.rename_dataset(unique_name, new_name)
    # Search by field
    df = new_ds.search_by_field("v", "x")
    assert len(df) == 1
    assert df.iloc[0]["data"]["id"] == 0
    # Search by tag — tags inherited
    df = new_ds.search_by_tag("t")
    assert len(df) == 1


def test_rename_to_existing_name_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    other = unique_name + "_other"
    engine.register_dataset(other, [src])
    with pytest.raises(DatasetAlreadyExists):
        engine.rename_dataset(unique_name, other)


def test_rename_missing_dataset_raises(engine: Engine, unique_name: str) -> None:
    with pytest.raises(DatasetNotFound):
        engine.rename_dataset(unique_name, unique_name + "_x")


def test_rename_invalid_name_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    with pytest.raises(Exception):
        engine.rename_dataset(unique_name, "../bad")


def test_rename_same_name_is_noop(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    ds = engine.rename_dataset(unique_name, unique_name)
    assert ds.name == unique_name


def test_overwrite_loses_tags_and_notes(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """F10: overwrite = delete + re-register; tags/notes lost."""
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    ds = engine.register_dataset(unique_name, [src1])
    ds.tag(0, "x")
    ds.note(0, "y")

    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 0}, {"id": 1}])
    ds2 = engine.register_dataset(unique_name, [src2], overwrite=True)

    assert ds2.tags() == []
    assert ds2.notes() == []
    assert ds2.row_count == 2


def test_overwrite_with_different_row_count(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": i} for i in range(5)])
    engine.register_dataset(unique_name, [src1])
    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": i} for i in range(10)])
    ds2 = engine.register_dataset(unique_name, [src2], overwrite=True)
    assert ds2.row_count == 10
