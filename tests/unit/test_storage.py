"""L1 — Storage paths and JSONL scan (pure-function layer)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.errors import WorkspaceMisconfigured
from dreamdata.storage.jsonl import iter_jsonl_offsets, parse_jsonl_line
from dreamdata.storage.paths import (
    Workspace,
    dataset_data_dir_rel,
    dataset_dir_rel,
    dataset_version_dir_rel,
    relative_to_workspace,
    resolve_in_workspace,
)


def test_dataset_dir_rel_helpers() -> None:
    assert dataset_dir_rel("ds") == "ds"
    assert dataset_version_dir_rel("ds", 1) == "ds/v1"
    assert dataset_data_dir_rel("ds", 1) == "ds/v1/data"


def test_workspace_rejects_relative_root() -> None:
    with pytest.raises(WorkspaceMisconfigured):
        Workspace(Path("relative/path"))


def test_workspace_resolve_and_reject_path_traversal(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    inside = ws.to_abs("ds/v1/data/a.jsonl")
    assert inside == (tmp_path / "ds" / "v1" / "data" / "a.jsonl").resolve()

    with pytest.raises(WorkspaceMisconfigured):
        ws.to_abs("../escape.jsonl")


def test_workspace_rejects_absolute_input(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(WorkspaceMisconfigured):
        ws.to_abs("/etc/passwd")


def test_workspace_rejects_null_byte(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(WorkspaceMisconfigured):
        ws.to_abs("a\x00b.jsonl")


def test_workspace_to_rel(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    abs_path = tmp_path / "ds" / "v1" / "data" / "a.jsonl"
    abs_path.parent.mkdir(parents=True)
    abs_path.write_text("x")
    rel = ws.to_rel(abs_path)
    assert rel == "ds/v1/data/a.jsonl"


def test_workspace_to_rel_rejects_outside(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    other = tmp_path.parent / "elsewhere"
    other.mkdir(exist_ok=True)
    (other / "f").write_text("x")
    with pytest.raises(WorkspaceMisconfigured):
        ws.to_rel(other / "f")


def test_iter_jsonl_offsets_basic(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    scans = list(iter_jsonl_offsets(f))
    assert [s.row_idx for s in scans] == [0, 1, 2]
    assert scans[0].byte_offset == 0
    assert scans[0].byte_length == len(b'{"a":1}')
    assert scans[0].line_ending_bytes == 1
    assert scans[1].byte_offset == scans[0].byte_offset + scans[0].byte_length + 1


def test_iter_jsonl_offsets_handles_no_trailing_newline(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text('{"a":1}\n{"a":2}', encoding="utf-8")
    scans = list(iter_jsonl_offsets(f))
    assert len(scans) == 2
    assert scans[1].line_ending_bytes == 0


def test_iter_jsonl_offsets_handles_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text("", encoding="utf-8")
    scans = list(iter_jsonl_offsets(f))
    assert scans == []


def test_iter_jsonl_offsets_rejects_non_utf8(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_bytes(b'{"a":1}\n\xff fe\n')
    with pytest.raises(Exception):
        list(iter_jsonl_offsets(f, strict=True))


def test_parse_jsonl_line_invalid(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text("", encoding="utf-8")
    with pytest.raises(Exception):
        parse_jsonl_line(f, "{bad}", byte_offset=0)


def test_iter_jsonl_offsets_reports_correct_offsets_for_unicode(tmp_path: Path) -> None:
    payload = {"text": "你好, 世界!"}
    f = tmp_path / "u.jsonl"
    f.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    scans = list(iter_jsonl_offsets(f))
    assert len(scans) == 1
    assert scans[0].byte_length == len(json.dumps(payload).encode("utf-8"))


def test_resolve_in_workspace_helper(tmp_path: Path) -> None:
    rel = "ds/v1/data/a.jsonl"
    abs_path = resolve_in_workspace(tmp_path, rel)
    assert abs_path == (tmp_path / rel).resolve(strict=False)


def test_relative_to_workspace_helper(tmp_path: Path) -> None:
    abs_path = tmp_path / "x.jsonl"
    abs_path.write_text("x")
    rel = relative_to_workspace(tmp_path, abs_path)
    assert rel == "x.jsonl"
