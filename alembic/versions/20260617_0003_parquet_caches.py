"""parquet_caches table for phase-4 Parquet cache management

Revision ID: 0003_parquet_caches
Revises: 0002_field_index
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_parquet_caches"
down_revision: str | None = "0002_field_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parquet_caches",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version_id", sa.BigInteger, nullable=False),
        sa.Column("field_path", sa.Text, nullable=True),
        sa.Column("cache_file_path", sa.Text, nullable=False),
        sa.Column("cache_kind", sa.Text, nullable=False),
        sa.Column("row_count", sa.BigInteger, nullable=False),
        sa.Column("file_count", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="parquet_caches_version_fkey",
            ondelete="CASCADE",
        ),
        comment="Parquet caches for faster reads (phase 4).",
    )
    op.create_index("parquet_caches_version_id_idx", "parquet_caches", ["version_id"])
    op.create_index("parquet_caches_version_kind_idx", "parquet_caches", ["version_id", "cache_kind"])


def downgrade() -> None:
    op.drop_index("parquet_caches_version_kind_idx", table_name="parquet_caches")
    op.drop_index("parquet_caches_version_id_idx", table_name="parquet_caches")
    op.drop_table("parquet_caches")
