"""Alembic environment. Reads ``DATABASE_URL`` from env; sync engine."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure src/ is importable for any model imports (currently unused — we
# manage SQL by hand below, but this keeps the door open for autogenerate).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Override sqlalchemy.url from DATABASE_URL if set. Force the psycopg v3
# dialect — the project uses psycopg[binary] (v3), not psycopg2.
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    if _db_url.startswith("postgres://"):
        _db_url = "postgresql://" + _db_url[len("postgres://") :]
    if _db_url.startswith("postgresql://"):
        _db_url = "postgresql+psycopg://" + _db_url[len("postgresql://") :]
    config.set_main_option("sqlalchemy.url", _db_url)
else:
    # Default to the psycopg v3 driver even when alembic.ini's plain URL is used.
    default = config.get_main_option("sqlalchemy.url") or ""
    if default.startswith("postgresql://"):
        config.set_main_option(
            "sqlalchemy.url",
            "postgresql+psycopg://" + default[len("postgresql://") :],
        )

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
