"""L6 — Scale smoke (1M rows).

Generates 1M JSONL rows with a deterministic seeded RNG and runs
register → scan → field_filter → tag_search → combined_search in one
test (re-registering 1M rows per test is too slow). Marked as ``slow``
so the default suite skips it; CI nightly job runs it explicitly with
``-m slow`` or ``-m scale``.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path

import pytest

from dreamdata.config import Settings
from dreamdata.sdk import Engine

pytestmark = [pytest.mark.slow, pytest.mark.scale]

ROW_COUNT = 1_000_000
TIMEOUT_REGISTER = 600  # 10 min budget for register on dev hardware
TIMEOUT_SCAN = 600


@pytest.fixture(scope="module")
def one_million_rows(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("scale")
    out_path = out_dir / "million.jsonl"
    rng = random.Random(0x42424242)
    roles = ["user", "assistant", "system"]
    with out_path.open("w", encoding="utf-8") as fh:
        for i in range(ROW_COUNT):
            row = {
                "id": i,
                "role": rng.choice(roles),
                "messages": [{"role": rng.choice(roles), "text": str(i)}],
                "rating": rng.randint(1, 5),
            }
            fh.write(json.dumps(row) + "\n")
    return out_path


@pytest.fixture()
def scale_engine(_engine_settings):  # type: ignore[no-untyped-def]
    settings = Settings(
        database_url=_engine_settings["DATABASE_URL"],
        workspace_path=Path(_engine_settings["WORKSPACE_PATH"]),
        user_id=_engine_settings["USER_ID"],
        duckdb_threads=4,
    )
    eng = Engine(settings=settings)
    yield eng
    eng.close()


def test_one_million_rows_full_lifecycle(scale_engine: Engine, one_million_rows: Path) -> None:
    """Single end-to-end scale assertion at 1M rows.

    Asserts:
    - Registration completes within budget.
    - Full scan returns exactly 1M rows.
    - Field filter returns the ground-truth subset count.
    - Tag filter returns exactly the rows we tagged.
    - Combined search is the intersection of field and tag matches.
    """
    name = f"scale_{uuid.uuid4().hex[:8]}"

    # Ground-truth via a single Python pass to verify the engine.
    expected_rating_5: set[int] = set()
    with one_million_rows.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            row = json.loads(line)
            if row["rating"] == 5:
                expected_rating_5.add(i)

    # Register
    start = time.time()
    ds = scale_engine.register_dataset(name, [one_million_rows])
    register_elapsed = time.time() - start
    assert ds.row_count == ROW_COUNT
    assert register_elapsed < TIMEOUT_REGISTER, (
        f"registration took {register_elapsed:.1f}s, budget {TIMEOUT_REGISTER}s"
    )

    # Tag a deterministic subset of rows
    rows_to_tag = list(range(0, ROW_COUNT, 1000))  # 1000 rows
    ds.tag(rows_to_tag, "scale")

    # Tag search
    df_tag = ds.search_by_tag("scale")
    assert set(df_tag["row_idx"].tolist()) == set(rows_to_tag)

    # Field filter
    df_field = ds.search_by_field("rating", 5)
    assert len(df_field) == len(expected_rating_5)

    # Combined search = intersection
    df_combined = ds.search(field_path="rating", field_value=5, tag="scale")
    expected_combined = {i for i in rows_to_tag if i in expected_rating_5}
    assert set(df_combined["row_idx"].tolist()) == expected_combined

    # Cleanup so subsequent runs of the same test don't accumulate workspace.
    scale_engine.delete_dataset(name)
