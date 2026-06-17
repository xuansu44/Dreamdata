"""field_index table for phase-2 indexing and pruning

Revision ID: 0002_field_index
Revises: 0001_initial
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_field_index"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field_index",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version_id", sa.BigInteger, nullable=False),
        sa.Column("field_path", sa.Text, nullable=False),
        sa.Column("row_idx", sa.BigInteger, nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="field_index_version_fkey",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "version_id", "field_path", "row_idx", name="field_index_version_field_row_unique"
        ),
        comment="Indexed (field_value, row_idx) per version for a chosen field.",
    )
    op.create_index("field_index_version_id_idx", "field_index", ["version_id"])
    op.create_index("field_index_version_field_idx", "field_index", ["version_id", "field_path"])
    op.create_index(
        "field_index_version_field_value_idx",
        "field_index",
        ["version_id", "field_path", "value"],
        postgresql_include=["row_idx"],
    )


def downgrade() -> None:
    op.drop_index("field_index_version_field_value_idx", table_name="field_index")
    op.drop_index("field_index_version_field_idx", table_name="field_index")
    op.drop_index("field_index_version_id_idx", table_name="field_index")
    op.drop_table("field_index")
