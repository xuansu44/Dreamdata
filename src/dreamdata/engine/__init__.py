"""Engine layer — DuckDB wrapper for read-only JSONL scans.

DuckDB never writes business data. The engine takes a list of file paths
(absolute) and a filter spec, returns a ``pandas.DataFrame``. Caller is
responsible for resolving metadata → file list; the engine is dumb about
dataset semantics.
"""

from dreamdata.engine.duckdb_engine import (
    DuckDBEngine,
    FieldFilter,
    FilterCombination,
    FilterOp,
    FilterValue,
    and_filter,
    eq_filter,
    in_filter,
    or_filter,
    range_filter,
    regex_filter,
)

__all__ = [
    "DuckDBEngine",
    "FieldFilter",
    "FilterCombination",
    "FilterOp",
    "FilterValue",
    "and_filter",
    "eq_filter",
    "in_filter",
    "or_filter",
    "range_filter",
    "regex_filter",
]
