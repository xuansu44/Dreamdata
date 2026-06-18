"""Settings — the single source of truth for engine configuration.

Loaded from environment via ``pydantic-settings``. Injected into
:class:`dreamdata.sdk.Engine` at construction; never imported as a
module-level singleton.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DATASET_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class Settings(BaseSettings):
    """Configuration for a dreamdata :class:`Engine` instance.

    All fields can be overridden via environment variables matching the
    field name (case-insensitive). Secrets (``database_url``) are stored
    as :class:`pydantic.SecretStr` so their ``repr`` is masked.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr = Field(
        ...,
        description="PostgreSQL connection string, e.g. postgresql://user:pass@localhost:5432/dreamdata.",
    )
    workspace_path: Path = Field(
        ...,
        description="Absolute path to the dataset storage root (JSONL + delta + Parquet cache).",
    )
    user_id: str = Field(
        ...,
        description="Single-user MVP author for annotations. Multi-user isolation arrives in phase 2.",
        min_length=1,
        max_length=128,
    )

    duckdb_memory_limit: str | None = Field(
        default=None,
        description="DuckDB memory budget, e.g. '4GB'. None uses DuckDB's default.",
    )
    duckdb_threads: int | None = Field(
        default=None,
        description="DuckDB worker threads. None uses CPU count.",
        ge=1,
        le=256,
    )

    tag_value_max_bytes: int = Field(
        default=4096,
        description="Maximum UTF-8 encoded byte length for a tag value.",
        ge=1,
        le=64 * 1024,
    )
    note_value_max_bytes: int = Field(
        default=64 * 1024,
        description="Maximum UTF-8 encoded byte length for a note body.",
        ge=1,
        le=1024 * 1024,
    )
    register_field_sample_size: int = Field(
        default=100,
        description="Number of rows to sample per file when inferring fields.",
        ge=1,
        le=10_000,
    )

    log_level: str = Field(default="INFO", description="Root log level.")

    # Auth settings (v0.4.0+)
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("dev-secret-key-change-in-production"),
        description="Secret key for JWT token signing. Set to a strong random value in production.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT signing.",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        description="JWT access token expiration in minutes.",
        ge=1,
        le=1440,
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="JWT refresh token expiration in days.",
        ge=1,
        le=365,
    )

    # Argon2 parameters
    argon2_time_cost: int = Field(
        default=3,
        description="Argon2 time cost (iterations).",
        ge=1,
    )
    argon2_memory_cost: int = Field(
        default=65536,
        description="Argon2 memory cost in KB.",
        ge=8192,
    )
    argon2_parallelism: int = Field(
        default=4,
        description="Argon2 parallelism (threads).",
        ge=1,
    )

    @field_validator("workspace_path")
    @classmethod
    def _workspace_must_be_absolute(cls, v: Path) -> Path:
        if not v.is_absolute():
            raise ValueError(f"workspace_path must be absolute, got {v}")
        return v

    @field_validator("user_id")
    @classmethod
    def _user_id_charset(cls, v: str) -> str:
        if not _DATASET_NAME_RE.match(v):
            raise ValueError(
                "user_id must match ^[a-zA-Z0-9_-]{1,128}$ "
                "(no path traversal, no null bytes, no whitespace)"
            )
        return v

    @field_validator("database_url")
    @classmethod
    def _database_url_scheme(cls, v: SecretStr) -> SecretStr:
        s = v.get_secret_value()
        if not s.startswith(("postgresql://", "postgres://")):
            raise ValueError("database_url must start with postgresql:// or postgres://")
        return v


def is_valid_dataset_name(name: str) -> bool:
    """Return True if *name* matches the safe-charset rule for dataset names."""
    return bool(_DATASET_NAME_RE.match(name))
