"""L1 — Settings validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dreamdata.config import Settings, is_valid_dataset_name


def test_settings_minimal_ok() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/d",
        workspace_path=Path("/tmp/ws"),
        user_id="tester",
    )
    assert s.database_url.get_secret_value() == "postgresql://u:p@localhost:5432/d"
    assert s.workspace_path == Path("/tmp/ws")
    assert s.user_id == "tester"


def test_settings_rejects_relative_workspace() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://u:p@localhost:5432/d",
            workspace_path=Path("relative/path"),
            user_id="tester",
        )


def test_settings_rejects_bad_user_id_charset() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://u:p@localhost:5432/d",
            workspace_path=Path("/tmp/ws"),
            user_id="../etc/passwd",
        )


def test_settings_rejects_bad_database_url_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="mysql://u:p@localhost/d",
            workspace_path=Path("/tmp/ws"),
            user_id="tester",
        )


def test_settings_secret_repr_is_masked() -> None:
    s = Settings(
        database_url="postgresql://u:super-secret@localhost:5432/d",
        workspace_path=Path("/tmp/ws"),
        user_id="tester",
    )
    r = repr(s.database_url)
    assert "super-secret" not in r


@pytest.mark.parametrize(
    "name,ok",
    [
        ("a", True),
        ("a_b-c", True),
        ("A1-B2_c3", True),
        ("a" * 128, True),
        ("", False),
        ("a" * 129, False),
        ("a.b", False),
        ("a/b", False),
        ("a b", False),
        ("../x", False),
        ("a\x00b", False),
    ],
)
def test_dataset_name_charset(name: str, ok: bool) -> None:
    assert is_valid_dataset_name(name) == ok
