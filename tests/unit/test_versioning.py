"""Unit tests for versioning core pure functions (L1).

Tests:
- _canonical_json_hash
- _safe_min/_safe_max
- _accumulate_min_max
- _scan_files_for_registration
"""

import json
import tempfile
from pathlib import Path

import pytest

from dreamdata.versioning.core import (
    _accumulate_min_max,
    _canonical_json_hash,
    _safe_max,
    _safe_min,
    _scan_files_for_registration,
)


class TestCanonicalJsonHash:
    """Tests for _canonical_json_hash."""

    def test_simple_dict_hashes_equal(self):
        """Same dicts with different key orders should have same hash."""
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        h1 = _canonical_json_hash(d1)
        h2 = _canonical_json_hash(d2)
        assert h1 == h2

    def test_nested_dict_order_independent(self):
        """Nested dicts' key order should not matter."""
        d1 = {"outer": {"x": 10, "y": 20}}
        d2 = {"outer": {"y": 20, "x": 10}}
        h1 = _canonical_json_hash(d1)
        h2 = _canonical_json_hash(d2)
        assert h1 == h2

    def test_list_order_matters(self):
        """List order matters for hashing."""
        d1 = {"items": [1, 2, 3]}
        d2 = {"items": [3, 2, 1]}
        h1 = _canonical_json_hash(d1)
        h2 = _canonical_json_hash(d2)
        assert h1 != h2

    def test_unicode_normalisation(self):
        """Unicode strings should be normalised to NFC."""
        s1 = "café"  # e with acute accent as single code point
        s2 = "café"  # e + combining acute accent
        h1 = _canonical_json_hash({"name": s1})
        h2 = _canonical_json_hash({"name": s2})
        assert h1 == h2

    def test_primitive_types(self):
        """Primitive types should hash correctly."""
        # None
        h_none = _canonical_json_hash({"value": None})
        # Bool
        h_true = _canonical_json_hash({"value": True})
        h_false = _canonical_json_hash({"value": False})
        # Int/float
        h_int = _canonical_json_hash({"value": 42})
        h_float = _canonical_json_hash({"value": 42.0})
        # String
        h_str = _canonical_json_hash({"value": "hello"})

        # All should be different
        hashes = [h_none, h_true, h_false, h_int, h_float, h_str]
        assert len(set(hashes)) == len(hashes)

    def test_empty_collections(self):
        """Empty collections should hash correctly."""
        h_empty_dict = _canonical_json_hash({})
        h_empty_list = _canonical_json_hash([])
        h_empty_str = _canonical_json_hash("")
        assert h_empty_dict != h_empty_list
        assert h_empty_dict != h_empty_str


class TestSafeMinMax:
    """Tests for _safe_min and _safe_max."""

    def test_safe_min_same_type(self):
        """_safe_min works with comparable types."""
        assert _safe_min(1, 2) == 1
        assert _safe_min(10, 5) == 5
        assert _safe_min("a", "z") == "a"

    def test_safe_max_same_type(self):
        """_safe_max works with comparable types."""
        assert _safe_max(1, 2) == 2
        assert _safe_max(10, 5) == 10
        assert _safe_max("a", "z") == "z"

    def test_safe_min_incomparable_types(self):
        """_safe_min returns first arg when types are incomparable."""
        assert _safe_min(1, "a") == 1
        assert _safe_min("a", 1) == "a"

    def test_safe_max_incomparable_types(self):
        """_safe_max returns first arg when types are incomparable."""
        assert _safe_max(1, "a") == 1
        assert _safe_max("a", 1) == "a"

    def test_safe_min_with_none(self):
        """_safe_min handles None values."""
        # None vs int (different types)
        assert _safe_min(None, 5) is None
        # None vs None (same type)
        assert _safe_min(None, None) is None


class TestAccumulateMinMax:
    """Tests for _accumulate_min_max."""

    def test_single_row(self):
        """_accumulate_min_max works with single row."""
        row = {"a": 10, "b": "hello"}
        acc: dict[str, tuple[object, object]] = {}
        _accumulate_min_max(row, acc)
        assert acc == {
            "a": (10, 10),
            "b": ("hello", "hello"),
        }

    def test_multiple_rows(self):
        """_accumulate_min_max accumulates min/max across rows."""
        rows = [
            {"a": 10, "b": "banana"},
            {"a": 5, "b": "apple"},
            {"a": 20, "b": "cherry"},
        ]
        acc: dict[str, tuple[object, object]] = {}
        for row in rows:
            _accumulate_min_max(row, acc)
        assert acc == {
            "a": (5, 20),
            "b": ("apple", "cherry"),
        }

    def test_nested_fields(self):
        """_accumulate_min_max handles nested fields."""
        row = {"user": {"age": 25, "name": "Alice"}}
        acc: dict[str, tuple[object, object]] = {}
        _accumulate_min_max(row, acc)
        assert acc == {
            "user.age": (25, 25),
            "user.name": ("Alice", "Alice"),
        }

    def test_skips_none_collections(self):
        """_accumulate_min_max skips None and collections."""
        row = {
            "a": None,
            "b": [1, 2, 3],
            "c": {"x": 10},
            "d": 42,
        }
        acc: dict[str, tuple[object, object]] = {}
        _accumulate_min_max(row, acc)
        # Only "d" is a scalar value
        assert "d" in acc
        assert "a" not in acc
        assert "b" not in acc
        assert "c.x" in acc


class TestScanFilesForRegistration:
    """Tests for _scan_files_for_registration."""

    def test_scan_single_file(self):
        """_scan_files_for_registration scans single JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / "data.jsonl"
            file_path.write_text(
                '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n'
            )
            staged_files = [(file_path, "data.jsonl")]

            total_rows, row_sources, file_stats, sample_rows = _scan_files_for_registration(
                version_id=1,
                staged_files=staged_files,
                sample_size=10,
            )

            assert total_rows == 2
            assert len(row_sources) == 2
            assert len(file_stats) >= 1
            assert len(sample_rows) == 2
            # Check row_sources structure
            assert all(len(rs) == 5 for rs in row_sources)
            # Check file_stats structure
            assert all(len(fs) == 5 for fs in file_stats)

    def test_scan_empty_file(self):
        """_scan_files_for_registration handles empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / "empty.jsonl"
            file_path.write_text("")
            staged_files = [(file_path, "empty.jsonl")]

            total_rows, row_sources, file_stats, sample_rows = _scan_files_for_registration(
                version_id=1,
                staged_files=staged_files,
                sample_size=10,
            )

            assert total_rows == 0
            assert len(row_sources) == 0
            assert len(file_stats) == 0
            assert len(sample_rows) == 0

    def test_sample_size_limit(self):
        """_scan_files_for_registration respects sample_size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            file_path = tmp_path / "many_rows.jsonl"
            # Write 100 rows
            lines = [json.dumps({"id": i, "x": i * 2}) for i in range(100)]
            file_path.write_text("\n".join(lines) + "\n")
            staged_files = [(file_path, "many_rows.jsonl")]

            total_rows, _, _, sample_rows = _scan_files_for_registration(
                version_id=1,
                staged_files=staged_files,
                sample_size=5,
            )

            assert total_rows == 100
            assert len(sample_rows) == 5
