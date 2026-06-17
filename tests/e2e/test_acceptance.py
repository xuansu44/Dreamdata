"""L8 — End-to-end acceptance scenario.

Single pytest scenario covering the full vertical slice:
register → tag → note → field-search → tag-search → combined-search →
rename → overwrite → delete.

This is the "vertical slice works" proof. If this test fails, Phase 1
cannot ship.
"""

from __future__ import annotations

import json
from pathlib import Path

from dreamdata.errors import DatasetNotFound
from dreamdata.sdk import Engine


def _write_jsonl(p: Path, rows: list[dict]) -> Path:
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def test_phase1_acceptance_vertical_slice(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """F1 → F10 vertical slice — the L8 acceptance scenario."""
    # F1: register
    src = _write_jsonl(
        tmp_path / "conversations.jsonl",
        [
            {"id": 0, "messages": [{"role": "user"}, {"role": "assistant"}], "rating": 5},
            {"id": 1, "messages": [{"role": "user"}], "rating": 1},
            {"id": 2, "messages": [{"role": "user"}, {"role": "assistant"}], "rating": 5},
            {"id": 3, "messages": [{"role": "assistant"}], "rating": 3},
            {"id": 4, "messages": [{"role": "user"}, {"role": "assistant"}], "rating": 5},
        ],
    )
    ds = engine.register_dataset(unique_name, [src])
    assert ds.row_count == 5

    # F2: list + info
    assert unique_name in engine.list_datasets()
    info = engine.info(unique_name)
    assert info.row_count == 5
    assert info.file_count == 1
    assert info.version_number == 1

    # F3: tag rows (multiple per row)
    ds.tag([0, 2, 4], "high_quality")
    ds.tag([1, 3], "needs_review")
    ds.tag(0, "favorite")
    tags = ds.tags()
    assert (0, "high_quality") in tags
    assert (0, "favorite") in tags
    assert (1, "needs_review") in tags
    assert len([t for t in tags if t[0] == 0]) == 2  # row 0 has two tags

    # F4: note rows
    nid = ds.note(0, "best conversation")
    ds.note(1, "needs rewrite")
    notes = ds.notes()
    assert len(notes) == 2
    assert any(body == "best conversation" for _, _, body in notes)

    # F5: search by field (top-level + nested)
    df = ds.search_by_field("rating", 5)
    assert {r["id"] for r in df["data"]} == {0, 2, 4}

    df = ds.search_by_field("messages.0.role", "user")
    assert {r["id"] for r in df["data"]} == {0, 1, 2, 4}

    # F6: search by tag
    df = ds.search_by_tag("high_quality")
    assert {r["id"] for r in df["data"]} == {0, 2, 4}
    df = ds.search_by_tag("favorite")
    assert {r["id"] for r in df["data"]} == {0}

    # F7: combined search (field AND tag)
    df = ds.search(field_path="rating", field_value=5, tag="high_quality")
    assert {r["id"] for r in df["data"]} == {0, 2, 4}

    df = ds.search(field_path="messages.0.role", field_value="user", tag="needs_review")
    assert {r["id"] for r in df["data"]} == {1}

    # Cross-check: combined_search == field_search ∩ tag_search
    field_set = {r["id"] for r in ds.search_by_field("rating", 5)["data"]}
    tag_set = {r["id"] for r in ds.search_by_tag("high_quality")["data"]}
    combined_set = {
        r["id"] for r in ds.search(field_path="rating", field_value=5, tag="high_quality")["data"]
    }
    assert combined_set == field_set & tag_set

    # F9: rename
    new_name = unique_name + "_v2"
    renamed = engine.rename_dataset(unique_name, new_name)
    assert renamed.name == new_name
    assert new_name in engine.list_datasets()
    assert unique_name not in engine.list_datasets()
    # Old name lookup must fail
    try:
        engine.open_dataset(unique_name)
        raise AssertionError("expected DatasetNotFound")
    except DatasetNotFound:
        pass
    # Search after rename must still work
    df = renamed.search_by_tag("high_quality")
    assert {r["id"] for r in df["data"]} == {0, 2, 4}

    # F10: overwrite = delete + re-register; tags/notes lost
    src2 = _write_jsonl(
        tmp_path / "fresh.jsonl",
        [{"id": 100}, {"id": 101}],
    )
    ds2 = engine.register_dataset(new_name, [src2], overwrite=True)
    assert ds2.row_count == 2
    assert ds2.tags() == []
    assert ds2.notes() == []

    # F8: delete
    engine.delete_dataset(new_name)
    assert new_name not in engine.list_datasets()
    try:
        engine.open_dataset(new_name)
        raise AssertionError("expected DatasetNotFound")
    except DatasetNotFound:
        pass


def test_architectural_invariants_hold_throughout(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Architectural invariants asserted across a full lifecycle."""
    import hashlib

    src = _write_jsonl(
        tmp_path / "a.jsonl",
        [{"id": 0}, {"id": 1}, {"id": 2}],
    )

    def _sha(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            h.update(fh.read())
        return h.hexdigest()

    original_sha = _sha(src)
    original_mtime = src.stat().st_mtime_ns

    ds = engine.register_dataset(unique_name, [src])
    ds.tag(0, "x")
    ds.note(0, "y")
    df = ds.scan()
    _ = df  # exercise the read path

    # Invariant: original JSONL never modified
    assert _sha(src) == original_sha
    assert src.stat().st_mtime_ns == original_mtime

    # Invariant: paths stored relative to workspace
    from dreamdata.meta.connection import MetaConnection
    from dreamdata.meta.repository import MetaRepository

    conn = MetaConnection(engine._settings.database_url.get_secret_value())
    try:
        repo = MetaRepository(conn)
        _, v = repo.get_dataset_by_name(name=unique_name)
        for rs in repo.list_row_sources(version_id=v.id):
            assert not rs.file_path.startswith("/")
        # Invariant: row_sources count == line count
        assert len(repo.list_row_sources(version_id=v.id)) == 3
    finally:
        conn.close()

    # Invariant: DuckDB never writes business files in workspace
    workspace_files_before = {
        p for p in engine.workspace_root.rglob("*") if p.is_file() and ".engine" not in p.parts
    }
    ds.scan()
    ds.search_by_field("id", 0)
    workspace_files_after = {
        p for p in engine.workspace_root.rglob("*") if p.is_file() and ".engine" not in p.parts
    }
    assert workspace_files_before == workspace_files_after
