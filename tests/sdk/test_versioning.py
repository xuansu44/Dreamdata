"""L3 SDK integration tests for Phase 3: versioning (F16-F22) and Phase 4: Parquet cache (F23-F26)."""

import importlib
import json
from pathlib import Path

import pytest

from dreamdata.sdk import Engine


def _pyarrow_available() -> bool:
    try:
        return importlib.util.find_spec("pyarrow") is not None
    except ModuleNotFoundError:
        return False


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_list_versions(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test F16: list_versions lists all versions of a dataset."""
    src = _write_jsonl(
        tmp_path / "v1.jsonl", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    )
    ds = engine.register_dataset(unique_name, [src])

    # Initial version
    versions = ds.list_versions()
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert versions[0].row_count == 2

    # Create a second version
    append_file = _write_jsonl(tmp_path / "append.jsonl", [{"id": 3, "name": "Charlie"}])
    ds_v2 = ds.append([append_file])

    # Verify both versions are listed
    versions = ds_v2.list_versions()
    assert len(versions) == 2
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2


def test_append_creates_new_version(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test F18: append creates a new version with inherited + new rows."""
    src = _write_jsonl(
        tmp_path / "data.jsonl", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    )
    ds = engine.register_dataset(unique_name, [src])
    assert ds.version_number == 1
    assert ds.row_count == 2

    # Append new rows
    append_file = _write_jsonl(
        tmp_path / "append.jsonl", [{"id": 3, "name": "Charlie"}, {"id": 4, "name": "David"}]
    )
    ds_v2 = ds.append([append_file])

    # Verify new version
    assert ds_v2.version_number == 2
    assert ds_v2.row_count == 4

    # Verify all rows are present
    df = ds_v2.scan()
    assert len(df) == 4
    ids = [r["id"] for r in df["data"]]
    assert set(ids) == {1, 2, 3, 4}


def test_append_with_multiple_files(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test append with multiple files at once."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1, "name": "Alice"}])
    ds = engine.register_dataset(unique_name, [src])

    append1 = _write_jsonl(tmp_path / "append1.jsonl", [{"id": 2, "name": "Bob"}])
    append2 = _write_jsonl(tmp_path / "append2.jsonl", [{"id": 3, "name": "Charlie"}])

    ds_v2 = ds.append([append1, append2])
    assert ds_v2.row_count == 3


def test_append_duplicate_filename_rejected(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Test append rejects duplicate filenames."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1}])
    ds = engine.register_dataset(unique_name, [src])

    append_dir = tmp_path / "append"
    append_dir.mkdir()
    file1 = append_dir / "data.jsonl"
    file2 = append_dir / "subdir" / "data.jsonl"
    file2.parent.mkdir()
    file1.write_text('{"id": 2}\n')
    file2.write_text('{"id": 3}\n')

    with pytest.raises(ValueError, match="Duplicate filename"):
        ds.append([file1, file2])


def test_map_transforms_rows(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test F19: map transforms each row and creates new version."""
    src = _write_jsonl(
        tmp_path / "data.jsonl", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    )
    ds = engine.register_dataset(unique_name, [src])

    # Transform rows by adding a prefix
    def add_prefix(row: dict) -> dict:
        return {**row, "name": "PREFIX_" + row["name"], "transformed": True}

    ds_v2 = ds.map(add_prefix)

    # Verify transformation
    assert ds_v2.version_number == 2
    df = ds_v2.scan()
    assert len(df) == 2

    for row in df["data"]:
        assert row.get("transformed") is True
        assert row["name"].startswith("PREFIX_")


def test_map_function_error_handling(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test map handles function errors gracefully."""
    src = _write_jsonl(
        tmp_path / "data.jsonl", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    )
    ds = engine.register_dataset(unique_name, [src])

    # Function that fails for specific rows
    def flaky_func(row: dict) -> dict:
        if row.get("id") == 2:
            raise ValueError("Oops")
        row["ok"] = True
        return row

    # This shouldn't raise; it should handle errors
    ds_v2 = ds.map(flaky_func)
    df = ds_v2.scan()
    assert len(df) == 2


def test_filter_map_filters_and_transforms(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Test F20: filter_map filters and transforms rows."""
    src = _write_jsonl(
        tmp_path / "data.jsonl",
        [
            {"id": 1, "name": "Alice", "score": 85},
            {"id": 2, "name": "Bob", "score": 70},
            {"id": 3, "name": "Charlie", "score": 95},
            {"id": 4, "name": "David", "score": 60},
        ],
    )
    ds = engine.register_dataset(unique_name, [src])

    # Filter only high-score students, and transform
    def only_high_scores(row: dict) -> dict | None:
        if row.get("score", 0) < 80:
            return None
        return {**row, "honor": True}

    ds_v2 = ds.filter_map(only_high_scores)

    # Verify filtering worked
    assert ds_v2.row_count == 2
    df = ds_v2.scan()
    assert len(df) == 2

    ids = [r["id"] for r in df["data"]]
    assert set(ids) == {1, 3}
    for row in df["data"]:
        assert row.get("honor") is True


def test_filter_map_filter_out_all(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test filter_map filtering out all rows."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1}, {"id": 2}])
    ds = engine.register_dataset(unique_name, [src])

    def filter_all(_row: dict) -> None:
        return None

    ds_v2 = ds.filter_map(filter_all)
    assert ds_v2.row_count == 0


def test_map_version_chain(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test multiple operations create a proper version chain."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1, "count": 10}])
    ds = engine.register_dataset(unique_name, [src])

    # v1 -> v2 (append)
    append_file = _write_jsonl(tmp_path / "append.jsonl", [{"id": 2, "count": 20}])
    ds_v2 = ds.append([append_file])

    # v2 -> v3 (map)
    ds_v3 = ds_v2.map(lambda row: {**row, "double": row["count"] * 2})

    # Verify versions
    versions = ds_v3.list_versions()
    assert len(versions) == 3
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2
    assert versions[2].version_number == 3


@pytest.mark.skipif(not _pyarrow_available(), reason="pyarrow not installed")
def test_refresh_parquet_cache(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test F23: refresh_parquet_cache creates a Parquet cache."""
    src = _write_jsonl(
        tmp_path / "data.jsonl",
        [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ],
    )
    ds = engine.register_dataset(unique_name, [src])

    # Create full cache
    cache_info = ds.refresh_parquet_cache()
    assert cache_info.cache_kind == "full"
    assert "cache_file_path" in repr(cache_info)


@pytest.mark.skipif(not _pyarrow_available(), reason="pyarrow not installed")
def test_list_parquet_caches(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test F24: list_parquet_caches lists existing Parquet caches."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1, "name": "Alice"}])
    ds = engine.register_dataset(unique_name, [src])

    # Initially no caches
    caches = ds.list_parquet_caches()
    assert len(caches) == 0

    # Create a cache
    ds.refresh_parquet_cache()

    # List caches
    caches = ds.list_parquet_caches()
    assert len(caches) == 1


def test_append_empty_file(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Test append with empty files (no-op, just inherits parent rows)."""
    src = _write_jsonl(tmp_path / "data.jsonl", [{"id": 1}])
    ds = engine.register_dataset(unique_name, [src])

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("")

    # Append should succeed and just create a new version with same rows
    ds_v2 = ds.append([empty_file])
    assert ds_v2.version_number == 2
    assert ds_v2.row_count == 1
    df = ds_v2.scan()
    assert len(df) == 1
    assert df["data"][0]["id"] == 1
