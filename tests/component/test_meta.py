"""L2 — MetaRepository component tests against real PostgreSQL.

No mocks. The session-scoped truncation fixture in conftest.py isolates
tests. We exercise every repository method and verify FK CASCADE on
dataset delete.
"""

from __future__ import annotations

import pytest

from dreamdata.errors import DatasetAlreadyExists, DatasetNotFound
from dreamdata.meta import MetaConnection, MetaRepository


@pytest.fixture()
def repo(_engine_settings):
    conn = MetaConnection(_engine_settings["DATABASE_URL"])
    repo = MetaRepository(conn)
    yield repo
    conn.close()


def test_ping_returns_true_on_real_db(repo: MetaRepository) -> None:
    assert repo.ping() is True


def test_insert_dataset_creates_v1(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=["id", "msg"])
    assert ds.name == "alpha"
    assert ds.inferred_fields == ["id", "msg"]
    assert ds.current_version_id == v.id
    assert v.version_number == 1
    assert v.row_count == 0


def test_insert_dataset_rejects_duplicate_name(repo: MetaRepository) -> None:
    repo.insert_dataset(name="alpha", inferred_fields=[])
    with pytest.raises(DatasetAlreadyExists):
        repo.insert_dataset(name="alpha", inferred_fields=[])


def test_get_dataset_by_name_raises_not_found(repo: MetaRepository) -> None:
    with pytest.raises(DatasetNotFound):
        repo.get_dataset_by_name(name="missing")


def test_list_datasets_sorted(repo: MetaRepository) -> None:
    repo.insert_dataset(name="zeta", inferred_fields=[])
    repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.insert_dataset(name="mid", inferred_fields=[])
    assert [d.name for d in repo.list_datasets()] == ["alpha", "mid", "zeta"]


def test_rename_dataset(repo: MetaRepository) -> None:
    repo.insert_dataset(name="old", inferred_fields=[])
    ds = repo.rename_dataset(old_name="old", new_name="new")
    assert ds.name == "new"
    assert [d.name for d in repo.list_datasets()] == ["new"]


def test_rename_to_existing_name_raises(repo: MetaRepository) -> None:
    repo.insert_dataset(name="a", inferred_fields=[])
    repo.insert_dataset(name="b", inferred_fields=[])
    with pytest.raises(DatasetAlreadyExists):
        repo.rename_dataset(old_name="a", new_name="b")


def test_rename_missing_raises_not_found(repo: MetaRepository) -> None:
    with pytest.raises(DatasetNotFound):
        repo.rename_dataset(old_name="missing", new_name="x")


def test_bulk_insert_row_sources(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    rows = [(i, v.id, "alpha/v1/data/a.jsonl", 10 * i, 8) for i in range(5)]
    inserted = repo.bulk_insert_row_sources(version_id=v.id, rows=iter(rows))
    assert inserted == 5
    listed = repo.list_row_sources(version_id=v.id)
    assert [r.row_idx for r in listed] == [0, 1, 2, 3, 4]
    assert all(r.file_path == "alpha/v1/data/a.jsonl" for r in listed)


def test_list_files_distinct(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    rows = [
        (0, v.id, "alpha/v1/data/a.jsonl", 0, 8),
        (1, v.id, "alpha/v1/data/b.jsonl", 0, 8),
        (2, v.id, "alpha/v1/data/b.jsonl", 8, 8),
    ]
    repo.bulk_insert_row_sources(version_id=v.id, rows=iter(rows))
    files = repo.list_files(version_id=v.id)
    assert files == ["alpha/v1/data/a.jsonl", "alpha/v1/data/b.jsonl"]


def test_tag_upsert_is_idempotent(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="good")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="good")
    rows = repo.list_annotations(version_id=v.id, user_id="u", kind="tag")
    assert len(rows) == 1


def test_tag_distinct_per_value(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="a")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="b")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=1, value="a")
    rows = repo.list_annotations(version_id=v.id, user_id="u", kind="tag")
    assert len(rows) == 3
    rows_for_0 = [r for r in rows if r.row_idx == 0]
    assert {r.value for r in rows_for_0} == {"a", "b"}


def test_row_indices_for_tag(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    for ri in [0, 5, 10]:
        repo.upsert_tag(version_id=v.id, user_id="u", row_idx=ri, value="hot")
    idxs = repo.row_indices_for_tag(version_id=v.id, user_id="u", value="hot")
    assert idxs == [0, 5, 10]


def test_row_indices_for_tags_any(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="a")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=1, value="b")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=2, value="c")
    idxs = repo.row_indices_for_tags_any(version_id=v.id, user_id="u", values=["a", "c"])
    assert idxs == {0, 2}
    empty = repo.row_indices_for_tags_any(version_id=v.id, user_id="u", values=[])
    assert empty == set()


def test_delete_tag(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="a")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="b")
    n = repo.delete_tag(version_id=v.id, user_id="u", row_idx=0, value="a")
    assert n == 1
    remaining = repo.list_annotations(version_id=v.id, user_id="u", row_idx=0, kind="tag")
    assert [r.value for r in remaining] == ["b"]
    n = repo.delete_tag(version_id=v.id, user_id="u", row_idx=0, value=None)
    assert n == 1
    remaining = repo.list_annotations(version_id=v.id, user_id="u", row_idx=0, kind="tag")
    assert remaining == []


def test_insert_note_returns_id(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    nid = repo.insert_note(version_id=v.id, user_id="u", row_idx=0, value="hello")
    assert nid > 0
    notes = repo.list_annotations(version_id=v.id, user_id="u", kind="note")
    assert len(notes) == 1
    assert notes[0].value == "hello"


def test_count_annotations(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="a")
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=1, value="b")
    repo.insert_note(version_id=v.id, user_id="u", row_idx=0, value="x")
    assert repo.count_annotations(version_id=v.id) == 3
    assert repo.count_annotations(version_id=v.id, kind="tag") == 2
    assert repo.count_annotations(version_id=v.id, kind="note") == 1


def test_bulk_upsert_file_stats(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    rows = [
        ("a.jsonl", "id", 0, 10, 11),
        ("a.jsonl", "name", "a", "z", 11),
    ]
    repo.bulk_upsert_file_stats(version_id=v.id, rows=iter(rows))
    listed = repo.list_file_stats(version_id=v.id)
    assert len(listed) == 2


def test_delete_dataset_cascades_to_everything(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=["id"])
    repo.bulk_insert_row_sources(
        version_id=v.id,
        rows=iter([(i, v.id, "alpha/v1/data/a.jsonl", 0, 0) for i in range(3)]),
    )
    repo.upsert_tag(version_id=v.id, user_id="u", row_idx=0, value="t")
    repo.insert_note(version_id=v.id, user_id="u", row_idx=0, value="n")
    rel_files = repo.delete_dataset(name="alpha")
    assert rel_files == ["alpha/v1/data/a.jsonl"]
    # All child rows must be gone via CASCADE.
    assert repo.list_datasets() == []
    assert repo.list_row_sources(version_id=v.id) == []
    assert repo.list_annotations(version_id=v.id, user_id="u") == []
    assert repo.list_file_stats(version_id=v.id) == []


def test_truncate_all_clears_tables(repo: MetaRepository) -> None:
    repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.truncate_all()
    assert repo.list_datasets() == []


def test_set_row_count(repo: MetaRepository) -> None:
    ds, v = repo.insert_dataset(name="alpha", inferred_fields=[])
    repo.set_row_count(version_id=v.id, row_count=42)
    _, v2 = repo.get_dataset_by_name(name="alpha")
    assert v2.row_count == 42
