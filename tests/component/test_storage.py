"""L2 — Storage layer against the real filesystem."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamdata.errors import FileNotReadable
from dreamdata.storage import (
    Workspace,
    iter_jsonl_offsets,
    parse_jsonl_line,
)


def test_workspace_ensure_creates_root(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    ws.ensure()
    assert (tmp_path / "ws").exists()
    assert (tmp_path / "ws" / ".engine").exists()
    assert (tmp_path / "ws" / ".engine" / ".write-test").exists()


def test_workspace_dataset_dirs(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.dataset_dir("alpha") == tmp_path / "alpha"
    assert ws.dataset_version_dir("alpha", 1) == tmp_path / "alpha" / "v1"
    assert ws.dataset_data_dir("alpha", 1) == tmp_path / "alpha" / "v1" / "data"


def test_iter_jsonl_offsets_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotReadable):
        list(iter_jsonl_offsets(tmp_path / "missing.jsonl"))


def test_iter_jsonl_offsets_directory_not_file(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    with pytest.raises(FileNotReadable):
        list(iter_jsonl_offsets(d))


def test_parse_jsonl_line_for_valid_input(tmp_path: Path) -> None:
    f = tmp_path / "a.jsonl"
    f.write_text("")
    val = parse_jsonl_line(f, '{"a": 1, "b": "x"}', byte_offset=0)
    assert val == {"a": 1, "b": "x"}


def test_iter_jsonl_offsets_preserves_logical_byte_offsets_for_complex_unicode(
    tmp_path: Path,
) -> None:
    rows = [
        {"text": "hello"},
        {"text": "你好"},
        {"text": "🚀emoji"},
    ]
    f = tmp_path / "u.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    scans = list(iter_jsonl_offsets(f))
    assert len(scans) == 3
    # Verify byte offsets match what wc-style measurement would produce.
    expected_offset = 0
    for i, scan in enumerate(scans):
        assert scan.byte_offset == expected_offset
        assert scan.line == json.dumps(rows[i])
        expected_offset += scan.byte_length + scan.line_ending_bytes


def test_workspace_to_abs_to_rel_roundtrip(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    rel = "ds/v1/data/a.jsonl"
    abs_path = ws.to_abs(rel)
    assert ws.to_rel(abs_path) == rel


def test_workspace_to_abs_rejects_symlink_escape(tmp_path: Path) -> None:
    """Symlinks pointing outside the workspace must be rejected."""
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.jsonl").write_text("x")

    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    inside = ws_root / "in.jsonl"
    try:
        inside.symlink_to(outside / "secret.jsonl")
    except OSError:
        pytest.skip("symlink creation not supported on this OS")
    ws = Workspace(ws_root)
    with pytest.raises(Exception):
        ws.to_abs("in.jsonl")
