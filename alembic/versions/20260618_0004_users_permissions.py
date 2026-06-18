"""users and permissions tables for phase-6 auth system

Revision ID: 0004_users_permissions
Revises: 0003_parquet_caches
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_users_permissions"
down_revision: str | None = "0003_parquet_caches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("hashed_password", sa.LargeBinary, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("role IN ('admin', 'user')", name="users_role_check"),
        comment="User accounts for phase-6 auth system.",
    )
    op.create_index("users_username_idx", "users", ["username"])
    op.create_index("users_email_idx", "users", ["email"])
    op.create_index("users_role_idx", "users", ["role"])

    # API keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("key_hash", sa.LargeBinary, nullable=False),
        sa.Column("key_prefix", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="api_keys_user_fkey", ondelete="CASCADE"
        ),
        comment="API keys for programmatic access.",
    )
    op.create_index("api_keys_user_id_idx", "api_keys", ["user_id"])
    op.create_index("api_keys_key_prefix_idx", "api_keys", ["key_prefix"])
    op.create_index(
        "api_keys_active_idx",
        "api_keys",
        ["user_id", "is_active"],
        postgresql_where=sa.text("is_active"),
    )

    # Dataset permissions table
    op.create_table(
        "dataset_permissions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("dataset_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("permission_level", sa.Text, nullable=False),
        sa.Column("granted_by", sa.BigInteger, nullable=True),
        sa.Column(
            "granted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="permissions_dataset_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="permissions_user_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="permissions_granted_by_fkey", ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "permission_level IN ('owner', 'read_write', 'read_only')",
            name="permissions_level_check",
        ),
        sa.UniqueConstraint("dataset_id", "user_id", name="permissions_dataset_user_key"),
        comment="Dataset access control permissions.",
    )
    op.create_index("permissions_dataset_idx", "dataset_permissions", ["dataset_id"])
    op.create_index("permissions_user_idx", "dataset_permissions", ["user_id"])
    op.create_index("permissions_level_idx", "dataset_permissions", ["permission_level"])

    # Password reset tokens table
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        sa.Column("token_prefix", sa.Text, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="reset_tokens_user_fkey", ondelete="CASCADE"
        ),
        comment="Password reset tokens (optional for v0.4.1).",
    )
    op.create_index("reset_tokens_user_idx", "password_reset_tokens", ["user_id"])
    op.create_index("reset_tokens_prefix_idx", "password_reset_tokens", ["token_prefix"])


def downgrade() -> None:
    op.drop_index("reset_tokens_prefix_idx", table_name="password_reset_tokens")
    op.drop_index("reset_tokens_user_idx", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("permissions_level_idx", table_name="dataset_permissions")
    op.drop_index("permissions_user_idx", table_name="dataset_permissions")
    op.drop_index("permissions_dataset_idx", table_name="dataset_permissions")
    op.drop_table("dataset_permissions")
    op.drop_index("api_keys_active_idx", table_name="api_keys")
    op.drop_index("api_keys_key_prefix_idx", table_name="api_keys")
    op.drop_index("api_keys_user_id_idx", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("users_role_idx", table_name="users")
    op.drop_index("users_email_idx", table_name="users")
    op.drop_index("users_username_idx", table_name="users")
    op.drop_table("users")
