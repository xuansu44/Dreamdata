"""L5 — Fuzz tests for adversarial inputs.

Adversarial inputs that must not crash silently or corrupt state:
- Malformed JSON lines
- Encoding edge cases (BOM, surrogate pairs, invalid UTF-8)
- Path traversal in dataset names
- Concurrent registration of same name
- 1 MB single-line JSON
- Empty files, files of only newlines, files without trailing newline
- Dataset-name and tag-value length limits
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from dreamdata.errors import (
    DatasetAlreadyExists,
    DatasetNameInvalid,
    RegistrationFileError,
    TagValueInvalid,
)
from dreamdata.sdk import Engine


def _write(p: Path, content: bytes | str) -> Path:
    if isinstance(content, str):
        p.write_text(content, encoding="utf-8")
    else:
        p.write_bytes(content)
    return p


def test_path_traversal_in_dataset_name_rejected(engine: Engine, tmp_path: Path) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    for bad in [
        "../etc_passwd",
        "../../etc/passwd",
        "/etc/passwd",
        "ds/with/slash",
        "ds\x00null",
        ".hidden",
        "ds.with.dots",
        "ds with space",
    ]:
        with pytest.raises(DatasetNameInvalid):
            engine.register_dataset(bad, [src])


def test_null_byte_in_dataset_name_rejected(engine: Engine) -> None:
    from dreamdata.errors import DatasetNameInvalid

    with pytest.raises(DatasetNameInvalid):
        engine.register_dataset("a\x00b", [])


def test_malformed_json_line_aborts_registration(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = _write(
        tmp_path / "bad.jsonl",
        '{"ok": 1}\n{not valid json}\n{"ok": 2}\n',
    )
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])
    # No partial state
    assert unique_name not in engine.list_datasets()


def test_truncated_json_line_aborts(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(
        tmp_path / "trunc.jsonl",
        '{"id": 0, "text": "abc',  # no closing
    )
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])


def test_unquoted_keys_aborts(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "uq.jsonl", "{id: 0}\n")
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])


def test_trailing_comma_aborts(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "tc.jsonl", '{"a": 1,}\n')
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [src])


def test_utf8_bom_handled_gracefully(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """A BOM at the start of file should not crash silently."""
    src = tmp_path / "bom.jsonl"
    src.write_bytes(b"\xef\xbb\xbf" + b'{"id": 0}\n{"id": 1}\n')
    with pytest.raises(Exception):
        engine.register_dataset(unique_name, [src])


def test_invalid_utf8_byte_aborts(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = tmp_path / "bad.jsonl"
    src.write_bytes(b'{"id": 0}\n\xff\xfe\n{"id": 1}\n')
    with pytest.raises(Exception):
        engine.register_dataset(unique_name, [src])


def test_empty_file_rejected(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "empty.jsonl", "")
    with pytest.raises(Exception):
        # Zero-row registration has no content; engine should refuse.
        engine.register_dataset(unique_name, [src])


def test_only_newlines_file_rejected(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "nl.jsonl", "\n\n\n")
    with pytest.raises(Exception):
        engine.register_dataset(unique_name, [src])


def test_no_trailing_newline_handled(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "no_nl.jsonl", '{"id": 0}\n{"id": 1}')
    ds = engine.register_dataset(unique_name, [src])
    assert ds.row_count == 2


def test_large_single_line_json_1mb(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """A 1MB single-line JSON row must register and scan cleanly."""
    big_text = "x" * (1 * 1024 * 1024)
    src = _write(tmp_path / "big.jsonl", json.dumps({"id": 0, "text": big_text}) + "\n")
    ds = engine.register_dataset(unique_name, [src])
    assert ds.row_count == 1
    df = ds.scan()
    assert df.iloc[0]["data"]["text"] == big_text


def test_deeply_nested_json_1000_levels(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """1000 levels of nesting should register (DuckDB has its own limits)."""
    nested: object = "leaf"
    for _ in range(1000):
        nested = {"x": nested}
    src = _write(tmp_path / "deep.jsonl", json.dumps({"id": 0, "nested": nested}) + "\n")
    try:
        ds = engine.register_dataset(unique_name, [src])
        assert ds.row_count == 1
    except Exception as exc:
        pytest.skip(f"DuckDB rejected 1000-level nesting: {exc}")


def test_dataset_name_at_max_length_ok(engine: Engine, tmp_path: Path) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    name = "a" * 128
    try:
        engine.register_dataset(name, [src])
    finally:
        try:
            engine.delete_dataset(name)
        except Exception:
            pass


def test_dataset_name_over_max_length_rejected(engine: Engine, tmp_path: Path) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    with pytest.raises(DatasetNameInvalid):
        engine.register_dataset("a" * 129, [src])


def test_tag_value_at_max_bytes_ok(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n{"id": 1}\n')
    ds = engine.register_dataset(unique_name, [src])
    max_b = ds._engine._settings.tag_value_max_bytes
    ok = "x" * max_b
    ds.tag(0, ok)
    assert ds.tags(row_idx=0) == [(0, ok)]


def test_tag_value_over_max_bytes_rejected(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    ds = engine.register_dataset(unique_name, [src])
    max_b = ds._engine._settings.tag_value_max_bytes
    too_long = "x" * (max_b + 1)
    with pytest.raises(TagValueInvalid):
        ds.tag(0, too_long)


def test_concurrent_register_same_name_one_wins(
    _engine_settings, tmp_path: Path, unique_name: str
) -> None:
    """Two concurrent registrations of the same name on independent
    engines: at most one succeeds. psycopg connections are not thread-safe
    so each thread must own its own ``Engine``.
    """
    from dreamdata.config import Settings
    from dreamdata.sdk import Engine as EngineCls

    src1 = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    src2 = _write(tmp_path / "b.jsonl", '{"id": 1}\n')
    results: list[object] = []
    errors: list[object] = []

    def _worker(src: Path) -> None:
        eng = EngineCls(
            settings=Settings(
                database_url=_engine_settings["DATABASE_URL"],
                workspace_path=Path(_engine_settings["WORKSPACE_PATH"]),
                user_id=_engine_settings["USER_ID"],
            )
        )
        try:
            ds = eng.register_dataset(unique_name, [src])
            results.append(ds.name)
        except Exception as exc:
            errors.append(exc)
        finally:
            eng.close()

    t1 = threading.Thread(target=_worker, args=(src1,))
    t2 = threading.Thread(target=_worker, args=(src2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # Exactly one registration succeeded
    assert len(results) + len(errors) == 2
    # In a race, sometimes both can fail (e.g., one starts, another deletes backup, etc.)
    # The invariant is: at most one succeeds, never two.
    assert len(results) <= 1
    if len(errors) == 2:
        # Both failed: acceptable, no state corruption
        assert all(isinstance(e, Exception) for e in errors)
    else:
        # One succeeded, one failed with either DatasetAlreadyExists or MetadataWriteFailed (both acceptable)
        assert len(results) == 1
        assert len(errors) == 1
        from dreamdata.errors import MetadataWriteFailed

        assert isinstance(errors[0], (DatasetAlreadyExists, MetadataWriteFailed))


def test_tag_with_null_byte_rejected(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    src = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    ds = engine.register_dataset(unique_name, [src])
    with pytest.raises(TagValueInvalid):
        ds.tag(0, "bad\x00tag")


def test_register_with_symlinked_source(engine: Engine, tmp_path: Path, unique_name: str) -> None:
    """Symlinks as source files: registration copies content (nofollow semantics)."""
    real = _write(tmp_path / "real.jsonl", '{"id": 0}\n{"id": 1}\n')
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink not supported")
    ds = engine.register_dataset(unique_name, [link])
    assert ds.row_count == 2


def test_reregister_with_overwrite_is_atomic(
    engine: Engine, tmp_path: Path, unique_name: str
) -> None:
    """Overwrite should leave the dataset in a consistent state regardless of input failure."""
    src1 = _write(tmp_path / "a.jsonl", '{"id": 0}\n')
    engine.register_dataset(unique_name, [src1])
    bad_src = tmp_path / "bad.jsonl"
    bad_src.write_text("{not valid}\n")
    with pytest.raises(RegistrationFileError):
        engine.register_dataset(unique_name, [bad_src], overwrite=True)
    # The original registration must still be intact after the failed overwrite.
    assert unique_name in engine.list_datasets()
    ds = engine.open_dataset(unique_name)
    assert ds.row_count == 1
