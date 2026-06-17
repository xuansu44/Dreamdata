"""Unit tests for parquet_cache pure functions (L1).

Tests:
- _extract_single_field_path
"""

from dreamdata.engine import FilterOp
from dreamdata.parquet_cache import _extract_single_field_path
from dreamdata.sdk import and_filter, eq_filter, or_filter, range_filter


class TestExtractSingleFieldPath:
    """Tests for _extract_single_field_path."""

    def test_extract_from_single_field_filter(self):
        """Extracts field path from simple FieldFilter."""
        filter = eq_filter("user.id", 123)
        assert _extract_single_field_path(filter) == "user.id"

    def test_returns_none_for_range_filter(self):
        """Returns None for range filter (it's a combination)."""
        filter = range_filter("score", 0.5, 1.0)
        # Range filter becomes AND(GE, LE), so no single field path
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_and_with_single_filter(self):
        """Returns None for AND filter (function only checks len == 1, not recurses)."""
        filter = and_filter([eq_filter("name", "Alice")])
        # Current implementation doesn't recursively check nested combinations
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_or_with_single_filter(self):
        """Returns None for OR filter (function only checks len == 1, not recurses)."""
        filter = or_filter([eq_filter("name", "Alice")])
        # Current implementation doesn't recursively check nested combinations
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_nested_single(self):
        """Returns None for nested combinations."""
        filter = and_filter([or_filter([eq_filter("a.b.c", 42)])])
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_multiple_filters(self):
        """Returns None when multiple filters present."""
        filter = and_filter([eq_filter("a", 1), eq_filter("b", 2)])
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_mixed_combinations(self):
        """Returns None for combinations with multiple different fields."""
        filter = or_filter([eq_filter("x", 1), range_filter("y", 0, 10)])
        assert _extract_single_field_path(filter) is None

    def test_returns_none_for_deep_multiple(self):
        """Returns None for deep nested combinations with multiple fields."""
        filter = and_filter([or_filter([eq_filter("a", 1), eq_filter("b", 2)])])
        assert _extract_single_field_path(filter) is None
