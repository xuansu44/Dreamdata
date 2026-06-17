"""L3 SDK integration — F1 register + F2 list/info + F8 delete."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from dreamdata.errors import (
    DatasetAlreadyExists,
    DatasetNameInvalid,
    DatasetNotFound,
    RegistrationFileError,
)
from dreamdata.sdk import Engine


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def test_register_single_file(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}, {"id": 2}])
    ds = engine.register_dataset(unique_name, [src])
    assert ds.name == unique_name
    assert ds.version_number == 1
    assert ds.row_count == 3


def test_register_multiple_files(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 2}, {"id": 3}, {"id": 4}])
    ds = engine.register_dataset(unique_name, [src1, src2])
    assert ds.row_count == 5


def test_register_copies_files_into_workspace(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = _write_jsonl(tmp_path / "src.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    staged = engine.workspace_root / unique_name / "v1" / "data" / "src.jsonl"
    assert staged.exists()


def test_register_does_not_modify_original_file(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Architectural invariant: original JSONL is never modified in place."""
    src = _write_jsonl(tmp_path / "src.jsonl", [{"id": 0}, {"id": 1}])
    original_sha = _sha256(src)
    original_mtime = src.stat().st_mtime_ns
    original_mode = stat.S_IMODE(src.stat().st_mode)
    engine.register_dataset(unique_name, [src])
    assert _sha256(src) == original_sha
    assert src.stat().st_mtime_ns == original_mtime
    assert stat.S_IMODE(src.stat().st_mode) == original_mode


def test_register_invalid_name_raises(engine: Engine, tmp_path: Path) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    for bad in ["", "../x", "a/b", "a b", "a" * 200, "a\x00b"]:
        with pytest.raises(DatasetNameInvalid):
            engine.register_dataset(bad, [src])


def test_register_duplicate_name_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    with pytest.raises(DatasetAlreadyExists):
        engine.register_dataset(unique_name, [src])


def test_register_with_overwrite_replaces_dataset(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """F10: overwrite = delete + re-register; tags/notes lost."""
    src1 = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    src2 = _write_jsonl(tmp_path / "b.jsonl", [{"id": 100}, {"id": 101}, {"id": 102}])
    ds1 = engine.register_dataset(unique_name, [src1])
    ds1.tag(0, "x")
    ds2 = engine.register_dataset(unique_name, [src2], overwrite=True)
    assert ds2.row_count == 3
    # tags from previous registration are gone
    assert ds2.tags() == []


def test_register_with_overwrite_when_absent_is_just_register(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    ds = engine.register_dataset(unique_name, [src], overwrite=True)
    assert ds.row_count == 1


def test_register_missing_file_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [tmp_path / "missing.jsonl"])


def test_register_directory_raises(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [d])


def test_register_empty_file_list_raises(engine: Engine, unique_name: str) -> None:
    with pytest.raises(Exception):
        engine.register_dataset(unique_name, [])


def test_register_duplicate_filename_raises(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    d1 = tmp_path / "d1"
    d1.mkdir()
    d2 = tmp_path / "d2"
    d2.mkdir()
    src1 = _write_jsonl(d1 / "same.jsonl", [{"id": 0}])
    src2 = _write_jsonl(d2 / "same.jsonl", [{"id": 1}])
    with pytest.raises(Exception):
        engine.register_dataset(unique_name, [src1, src2])


def test_register_invalid_jsonl_aborts(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = tmp_path / "bad.jsonl"
    src.write_text('{"ok": 1}\n{bad json}\n{"ok": 2}\n', encoding="utf-8")
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])
    # On failure, the dataset metadata must not exist.
    assert unique_name not in engine.list_datasets()


def test_register_failure_leaves_no_workspace_dir(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = tmp_path / "bad.jsonl"
    src.write_text('{"ok": 1}\n{bad}\n', encoding="utf-8")
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])
    assert not (engine.workspace_root / unique_name).exists()


def test_list_datasets_sorted(engine: Engine, tmp_path: Path) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset("zeta", [src])
    engine.register_dataset("alpha", [src])
    engine.register_dataset("mid", [src])
    assert engine.list_datasets() == ["alpha", "mid", "zeta"]


def test_info_returns_metadata(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    engine.register_dataset(unique_name, [src])
    info = engine.info(unique_name)
    assert info.name == unique_name
    assert info.row_count == 2
    assert info.file_count == 1
    assert info.version_number == 1


def test_open_dataset_round_trip(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    ds = engine.open_dataset(unique_name)
    assert ds.name == unique_name
    assert ds.row_count == 1


def test_open_missing_dataset_raises(engine: Engine, unique_name: str) -> None:
    with pytest.raises(DatasetNotFound):
        engine.open_dataset(unique_name)


def test_delete_dataset_removes_everything(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}, {"id": 1}])
    ds = engine.register_dataset(unique_name, [src])
    ds.tag(0, "x")
    staged = engine.workspace_root / unique_name
    assert staged.exists()
    engine.delete_dataset(unique_name)
    assert unique_name not in engine.list_datasets()
    assert not staged.exists()


def test_delete_missing_dataset_raises(engine: Engine, unique_name: str) -> None:
    with pytest.raises(DatasetNotFound):
        engine.delete_dataset(unique_name)


def test_inferred_fields_captured(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write_jsonl(
        tmp_path / "a.jsonl",
        [
            {"id": 0, "messages": [{"role": "user"}]},
            {"id": 1, "messages": [{"role": "assistant"}]},
        ],
    )
    ds = engine.register_dataset(unique_name, [src])
    inferred = set(ds.inferred_fields)
    assert "id" in inferred
    assert "messages" in inferred
    assert "messages.0.role" in inferred


def test_paths_stored_relative_to_workspace(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Architectural invariant: stored paths are relative to WORKSPACE_PATH."""
    src = _write_jsonl(tmp_path / "a.jsonl", [{"id": 0}])
    engine.register_dataset(unique_name, [src])
    from dreamdata.meta.connection import MetaConnection
    from dreamdata.meta.repository import MetaRepository

    conn = MetaConnection(engine._settings.database_url.get_secret_value())
    try:
        repo = MetaRepository(conn)
        ds, v = repo.get_dataset_by_name(name=unique_name)
        for rs in repo.list_row_sources(version_id=v.id):
            assert not rs.file_path.startswith("/")
            assert rs.file_path == f"{unique_name}/v1/data/a.jsonl"
    finally:
        conn.close()
