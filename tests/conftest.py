"""Shared pytest fixtures.

- Every test session uses the dedicated ``dreamdata_test`` PostgreSQL
  database. Tables are truncated once per test session.
- Each test gets its own workspace under ``tmp_path`` and its own
  ``USER_ID`` derived from a UUID so concurrent test runs do not collide.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

# Default to the dreamdata_test DB. Tests that need a different database
# can override via environment.
os.environ.setdefault("DATABASE_URL", "postgresql://yanhaolin@localhost:5432/dreamdata_test")


@pytest.fixture(scope="session")
def _database_url() -> str:
    url = os.environ["DATABASE_URL"]
    if not url:
        raise RuntimeError("DATABASE_URL must be set for the test session")
    return url


@pytest.fixture(scope="session")
def _engine_settings(
    _database_url: str, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[dict[str, str]]:
    workspace = tmp_path_factory.mktemp("workspace-")
    user_id = f"tester-{uuid.uuid4().hex[:8]}"
    env = {
        "DATABASE_URL": _database_url,
        "WORKSPACE_PATH": str(workspace),
        "USER_ID": user_id,
        "LOG_LEVEL": "WARNING",
        "DUCKDB_THREADS": "2",
    }
    old_env = dict(os.environ)
    os.environ.update(env)
    yield env
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture()
def engine(_engine_settings: dict[str, str]) -> Iterator[object]:
    """A fresh Engine per test, sharing the session DB but isolated by user_id + workspace."""
    from dreamdata.config import Settings
    from dreamdata.sdk import Engine

    settings = Settings(
        database_url=_engine_settings["DATABASE_URL"],
        workspace_path=Path(_engine_settings["WORKSPACE_PATH"]),
        user_id=_engine_settings["USER_ID"],
    )
    eng = Engine(settings=settings)
    yield eng
    eng.close()


@pytest.fixture()
def unique_name() -> str:
    return f"ds_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


@pytest.fixture()
def write_jsonl(tmp_path: Path):
    def _write(name: str, rows: list[dict] | list[str]) -> Path:
        path = tmp_path / name
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                if isinstance(row, str):
                    fh.write(row + "\n")
                else:
                    import json as _json

                    fh.write(_json.dumps(row) + "\n")
        return path

    return _write


@pytest.fixture(autouse=True)
def _truncate_db(_engine_settings: dict[str, str]) -> Iterator[None]:
    """Truncate metadata tables before each test so state never leaks between tests."""
    from dreamdata.meta.connection import MetaConnection
    from dreamdata.meta.repository import MetaRepository

    conn = MetaConnection(_engine_settings["DATABASE_URL"])
    repo = MetaRepository(conn)
    try:
        repo.truncate_all()
    finally:
        conn.close()
    yield
