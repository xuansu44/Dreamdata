"""initial metadata schema (datasets, dataset_versions, row_sources, user_annotations, file_stats)

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "DO $$ BEGIN CREATE TYPE annotation_kind AS ENUM ('tag', 'note'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("current_version_id", sa.BigInteger, nullable=True),
        sa.Column(
            "inferred_fields",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="datasets_name_key"),
        sa.ForeignKeyConstraint(
            ["current_version_id"],
            ["dataset_versions.id"],
            name="datasets_current_version_fkey",
            use_alter=True,
        ),
        comment="One row per registered dataset (top-level handle).",
    )

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("dataset_id", sa.BigInteger, nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("parent_version_id", sa.BigInteger, nullable=True),
        sa.Column("row_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name="dataset_versions_dataset_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"], ["dataset_versions.id"], name="dataset_versions_parent_fkey"
        ),
        sa.UniqueConstraint(
            "dataset_id", "version_number", name="dataset_versions_dataset_version_unique"
        ),
        comment="One row per version of a dataset. MVP: exactly one row (v1) per dataset.",
    )

    op.create_table(
        "row_sources",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version_id", sa.BigInteger, nullable=False),
        sa.Column("row_idx", sa.BigInteger, nullable=False),
        sa.Column("source_version_id", sa.BigInteger, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("byte_offset", sa.BigInteger, nullable=False),
        sa.Column("byte_length", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="row_sources_version_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["dataset_versions.id"], name="row_sources_source_version_fkey"
        ),
        sa.UniqueConstraint("version_id", "row_idx", name="row_sources_version_row_unique"),
        comment="Maps each logical row index in a version to its physical location.",
    )
    op.create_index("row_sources_version_id_idx", "row_sources", ["version_id"])
    op.create_index("row_sources_file_path_idx", "row_sources", ["file_path"])

    op.create_table(
        "user_annotations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("row_idx", sa.BigInteger, nullable=False),
        sa.Column(
            "kind", postgresql.ENUM(name="annotation_kind", create_type=False), nullable=False
        ),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="user_annotations_version_fkey",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "version_id",
            "user_id",
            "row_idx",
            "kind",
            "value",
            name="user_annotations_tag_unique",
        ),
        comment="Tags and notes attached to logical rows.",
    )
    op.create_index("user_annotations_version_idx", "user_annotations", ["version_id"])
    op.create_index(
        "user_annotations_tag_idx",
        "user_annotations",
        ["version_id", "user_id", "kind", "value"],
    )

    op.create_table(
        "file_stats",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("version_id", sa.BigInteger, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("field_path", sa.Text, nullable=False),
        sa.Column("min_value", postgresql.JSONB, nullable=True),
        sa.Column("max_value", postgresql.JSONB, nullable=True),
        sa.Column("row_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name="file_stats_version_fkey",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("version_id", "file_path", "field_path", name="file_stats_unique"),
        comment="Per-file per-field statistics for pruning (MVP: top-level scalars only).",
    )
    op.create_index("file_stats_version_idx", "file_stats", ["version_id"])


def downgrade() -> None:
    op.drop_index("file_stats_version_idx", table_name="file_stats")
    op.drop_table("file_stats")
    op.drop_index("user_annotations_tag_idx", table_name="user_annotations")
    op.drop_index("user_annotations_version_idx", table_name="user_annotations")
    op.drop_table("user_annotations")
    op.drop_index("row_sources_file_path_idx", table_name="row_sources")
    op.drop_index("row_sources_version_id_idx", table_name="row_sources")
    op.drop_table("row_sources")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
    op.execute("DROP TYPE IF EXISTS annotation_kind")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
