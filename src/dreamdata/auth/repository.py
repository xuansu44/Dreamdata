"""AuthRepository - PostgreSQL access for users and permissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg import sql

from dreamdata.errors import MetadataWriteFailed
from dreamdata.meta.connection import MetaConnection

UserRole = Literal["admin", "user"]
PermissionLevel = Literal["owner", "read_write", "read_only"]


@dataclass(slots=True, frozen=True)
class UserRow:
    """One row from users table."""

    id: int
    username: str
    email: str
    hashed_password: bytes
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class APIKeyRow:
    """One row from api_keys table."""

    id: int
    user_id: int
    key_prefix: str
    name: str | None
    scopes: list[str] | None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    is_active: bool


@dataclass(slots=True, frozen=True)
class APIKeyRowWithHash(APIKeyRow):
    """API key row including the hash (for verification only)."""

    key_hash: bytes


@dataclass(slots=True, frozen=True)
class DatasetPermissionRow:
    """One row from dataset_permissions table."""

    id: int
    dataset_id: int
    user_id: int
    permission_level: PermissionLevel
    granted_by: int | None
    granted_at: datetime
    expires_at: datetime | None


class AuthRepository:
    """Repository for user and permission operations."""

    def __init__(self, conn: MetaConnection) -> None:
        self._conn = conn

    def _ensure_table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self._conn.connection.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = %s"),
                (table_name,),
            )
            return cur.fetchone() is not None

    # ============================================
    # User operations
    # ============================================

    def count_users(self) -> int:
        """Count the number of users in the system."""
        if not self._ensure_table_exists("users"):
            return 0
        row = self._conn.fetchone(sql.SQL("SELECT COUNT(*) AS n FROM users"))
        return int(row["n"]) if row else 0

    def create_user(
        self,
        *,
        username: str,
        email: str,
        hashed_password: bytes,
        salt: bytes,  # noqa: ARG002
        role: UserRole,
    ) -> UserRow:
        """Create a new user."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO users (username, email, hashed_password, role, is_active) "
                    "VALUES (%s, %s, %s, %s, true) "
                    "RETURNING id, username, email, hashed_password, role, is_active, last_login_at, created_at, updated_at"
                ),
                (username, email, hashed_password, role),
            )
            row = cur.fetchone()
        if row is None:
            raise MetadataWriteFailed(table="users", reason="INSERT did not return a row")
        return UserRow(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            role=row["role"],
            is_active=row["is_active"],
            last_login_at=row["last_login_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_user_by_username(self, username: str) -> UserRow | None:
        """Get a user by username."""
        if not self._ensure_table_exists("users"):
            return None
        row = self._conn.fetchone(sql.SQL("SELECT * FROM users WHERE username = %s"), (username,))
        if row is None:
            return None
        return UserRow(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            role=row["role"],
            is_active=row["is_active"],
            last_login_at=row["last_login_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_user_by_email(self, email: str) -> UserRow | None:
        """Get a user by email."""
        if not self._ensure_table_exists("users"):
            return None
        row = self._conn.fetchone(sql.SQL("SELECT * FROM users WHERE email = %s"), (email,))
        if row is None:
            return None
        return UserRow(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            role=row["role"],
            is_active=row["is_active"],
            last_login_at=row["last_login_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_user_by_id(self, user_id: int) -> UserRow | None:
        """Get a user by ID."""
        if not self._ensure_table_exists("users"):
            return None
        row = self._conn.fetchone(sql.SQL("SELECT * FROM users WHERE id = %s"), (user_id,))
        if row is None:
            return None
        return UserRow(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            role=row["role"],
            is_active=row["is_active"],
            last_login_at=row["last_login_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_user_password(
        self,
        *,
        user_id: int,
        hashed_password: bytes,
        salt: bytes,  # noqa: ARG002
    ) -> None:
        """Update a user's password."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE users SET hashed_password = %s, updated_at = now() WHERE id = %s"),
                (hashed_password, user_id),
            )

    def update_last_login(self, user_id: int) -> None:
        """Update the last_login_at timestamp for a user."""
        self._conn.execute(
            sql.SQL("UPDATE users SET last_login_at = now() WHERE id = %s"),
            (user_id,),
        )

    def update_user(
        self,
        *,
        user_id: int,
        username: str | None = None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserRow | None:
        """Update user information."""
        updates = []
        params: list[Any] = []
        if username is not None:
            updates.append("username = %s")
            params.append(username)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if role is not None:
            updates.append("role = %s")
            params.append(role)
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
        if not updates:
            return self.get_user_by_id(user_id)

        updates.append("updated_at = now()")
        params.append(user_id)

        with self._conn.transaction() as conn, conn.cursor() as cur:
            query = sql.SQL("UPDATE users SET {} WHERE id = %s RETURNING *").format(
                sql.SQL(", ").join(sql.SQL(u) for u in updates)
            )
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        if row is None:
            return None
        return UserRow(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            role=row["role"],
            is_active=row["is_active"],
            last_login_at=row["last_login_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_users(self) -> list[UserRow]:
        """List all users."""
        if not self._ensure_table_exists("users"):
            return []
        rows = self._conn.fetchall(sql.SQL("SELECT * FROM users ORDER BY username"))
        return [
            UserRow(
                id=r["id"],
                username=r["username"],
                email=r["email"],
                hashed_password=r["hashed_password"],
                role=r["role"],
                is_active=r["is_active"],
                last_login_at=r["last_login_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def deactivate_user(self, user_id: int) -> None:
        """Deactivate a user account."""
        self._conn.execute(
            sql.SQL("UPDATE users SET is_active = false, updated_at = now() WHERE id = %s"),
            (user_id,),
        )

    def delete_user(self, user_id: int) -> None:
        """Delete a user (cascades to permissions and API keys)."""
        self._conn.execute(sql.SQL("DELETE FROM users WHERE id = %s"), (user_id,))

    # ============================================
    # API key operations
    # ============================================

    def create_api_key(
        self,
        *,
        user_id: int,
        key_hash: bytes,
        key_prefix: str,
        name: str | None = None,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> APIKeyRow:
        """Create a new API key."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO api_keys (user_id, key_hash, key_prefix, name, scopes, expires_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "RETURNING id, user_id, key_prefix, name, scopes, expires_at, last_used_at, created_at, is_active"
                ),
                (user_id, key_hash, key_prefix, name, scopes, expires_at),
            )
            row = cur.fetchone()
        if row is None:
            raise MetadataWriteFailed(table="api_keys", reason="INSERT did not return a row")
        return APIKeyRow(
            id=row["id"],
            user_id=row["user_id"],
            key_prefix=row["key_prefix"],
            name=row["name"],
            scopes=row["scopes"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
            is_active=row["is_active"],
        )

    def get_api_key_by_prefix(self, key_prefix: str) -> list[APIKeyRowWithHash]:
        """Get API keys by prefix (for verification)."""
        if not self._ensure_table_exists("api_keys"):
            return []
        rows = self._conn.fetchall(
            sql.SQL("SELECT * FROM api_keys WHERE key_prefix = %s AND is_active = true"),
            (key_prefix,),
        )
        return [
            APIKeyRowWithHash(
                id=r["id"],
                user_id=r["user_id"],
                key_prefix=r["key_prefix"],
                key_hash=r["key_hash"],
                name=r["name"],
                scopes=r["scopes"],
                expires_at=r["expires_at"],
                last_used_at=r["last_used_at"],
                created_at=r["created_at"],
                is_active=r["is_active"],
            )
            for r in rows
        ]

    def list_api_keys_for_user(self, user_id: int) -> list[APIKeyRow]:
        """List all API keys for a user."""
        if not self._ensure_table_exists("api_keys"):
            return []
        rows = self._conn.fetchall(
            sql.SQL("SELECT * FROM api_keys WHERE user_id = %s ORDER BY created_at DESC"),
            (user_id,),
        )
        return [
            APIKeyRow(
                id=r["id"],
                user_id=r["user_id"],
                key_prefix=r["key_prefix"],
                name=r["name"],
                scopes=r["scopes"],
                expires_at=r["expires_at"],
                last_used_at=r["last_used_at"],
                created_at=r["created_at"],
                is_active=r["is_active"],
            )
            for r in rows
        ]

    def revoke_api_key(self, api_key_id: int, user_id: int) -> bool:
        """Revoke an API key. Returns True if a key was revoked."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE api_keys SET is_active = false WHERE id = %s AND user_id = %s"),
                (api_key_id, user_id),
            )
            return cur.rowcount > 0

    def touch_api_key(self, api_key_id: int) -> None:
        """Update the last_used_at timestamp for an API key."""
        self._conn.execute(
            sql.SQL("UPDATE api_keys SET last_used_at = now() WHERE id = %s"),
            (api_key_id,),
        )

    # ============================================
    # Permission operations
    # ============================================

    def get_dataset_permission(self, dataset_id: int, user_id: int) -> DatasetPermissionRow | None:
        """Get a user's permission for a dataset."""
        if not self._ensure_table_exists("dataset_permissions"):
            return None
        row = self._conn.fetchone(
            sql.SQL("SELECT * FROM dataset_permissions WHERE dataset_id = %s AND user_id = %s"),
            (dataset_id, user_id),
        )
        if row is None:
            return None
        return DatasetPermissionRow(
            id=row["id"],
            dataset_id=row["dataset_id"],
            user_id=row["user_id"],
            permission_level=row["permission_level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
            expires_at=row["expires_at"],
        )

    def get_user_permissions_for_dataset(self, dataset_id: int) -> list[DatasetPermissionRow]:
        """Get all permissions for a dataset."""
        if not self._ensure_table_exists("dataset_permissions"):
            return []
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT * FROM dataset_permissions WHERE dataset_id = %s ORDER BY permission_level, granted_at"
            ),
            (dataset_id,),
        )
        return [
            DatasetPermissionRow(
                id=r["id"],
                dataset_id=r["dataset_id"],
                user_id=r["user_id"],
                permission_level=r["permission_level"],
                granted_by=r["granted_by"],
                granted_at=r["granted_at"],
                expires_at=r["expires_at"],
            )
            for r in rows
        ]

    def get_datasets_for_user(self, user_id: int) -> list[tuple[int, int, str]]:
        """Get all datasets a user has access to. Returns list of (dataset_id, dataset_version_id, permission_level)."""
        if not self._ensure_table_exists("dataset_permissions"):
            return []
        rows = self._conn.fetchall(
            sql.SQL(
                "SELECT p.dataset_id, d.current_version_id, p.permission_level "
                "FROM dataset_permissions p "
                "JOIN datasets d ON d.id = p.dataset_id "
                "WHERE p.user_id = %s "
                "ORDER BY d.name"
            ),
            (user_id,),
        )
        return [
            (
                int(r["dataset_id"]),
                int(r["current_version_id"]) if r["current_version_id"] is not None else -1,
                r["permission_level"],
            )
            for r in rows
        ]

    def grant_permission(
        self,
        *,
        dataset_id: int,
        user_id: int,
        permission_level: PermissionLevel,
        granted_by: int,
        expires_at: datetime | None = None,
    ) -> DatasetPermissionRow:
        """Grant or update a dataset permission."""
        now = datetime.now(UTC)
        with self._conn.transaction() as conn, conn.cursor() as cur:
            # Try insert, if conflict then update
            cur.execute(
                sql.SQL(
                    "INSERT INTO dataset_permissions "
                    "(dataset_id, user_id, permission_level, granted_by, expires_at) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (dataset_id, user_id) DO UPDATE SET "
                    "permission_level = EXCLUDED.permission_level, "
                    "granted_by = EXCLUDED.granted_by, "
                    "expires_at = EXCLUDED.expires_at "
                    "RETURNING *"
                ),
                (dataset_id, user_id, permission_level, granted_by, expires_at),
            )
            row = cur.fetchone()

        if row is None:
            raise MetadataWriteFailed(
                table="dataset_permissions", reason="INSERT/UPDATE did not return a row"
            )
        return DatasetPermissionRow(
            id=row["id"],
            dataset_id=row["dataset_id"],
            user_id=row["user_id"],
            permission_level=row["permission_level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
            expires_at=row["expires_at"],
        )

    def revoke_permission(self, dataset_id: int, user_id: int) -> bool:
        """Revoke a user's permission for a dataset. Returns True if revoked."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM dataset_permissions WHERE dataset_id = %s AND user_id = %s"),
                (dataset_id, user_id),
            )
            return cur.rowcount > 0

    def update_permission_level(
        self,
        dataset_id: int,
        user_id: int,
        permission_level: PermissionLevel,
        expires_at: datetime | None = None,
    ) -> DatasetPermissionRow | None:
        """Update a permission level."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            if expires_at is not None:
                cur.execute(
                    sql.SQL(
                        "UPDATE dataset_permissions "
                        "SET permission_level = %s, expires_at = %s "
                        "WHERE dataset_id = %s AND user_id = %s "
                        "RETURNING *"
                    ),
                    (permission_level, expires_at, dataset_id, user_id),
                )
            else:
                cur.execute(
                    sql.SQL(
                        "UPDATE dataset_permissions SET permission_level = %s "
                        "WHERE dataset_id = %s AND user_id = %s "
                        "RETURNING *"
                    ),
                    (permission_level, dataset_id, user_id),
                )
            row = cur.fetchone()
        if row is None:
            return None
        return DatasetPermissionRow(
            id=row["id"],
            dataset_id=row["dataset_id"],
            user_id=row["user_id"],
            permission_level=row["permission_level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
            expires_at=row["expires_at"],
        )

    def check_permission(
        self,
        dataset_id: int,
        user_id: int,
        required_levels: list[PermissionLevel],
        user_role: UserRole | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if a user has the required permission level for a dataset.
        Admin users automatically have access.
        Returns (has_access, actual_level).
        """
        # Admin bypass
        if user_role == "admin":
            return True, "admin"

        perm = self.get_dataset_permission(dataset_id, user_id)
        if perm is None:
            # Check if expired
            return False, None

        if perm.expires_at and perm.expires_at < datetime.now(UTC):
            return False, None

        level_order = {"read_only": 0, "read_write": 1, "owner": 2}
        user_level = level_order.get(perm.permission_level, -1)
        min_required = min(level_order.get(level, 999) for level in required_levels)

        if user_level >= min_required:
            return True, perm.permission_level
        return False, perm.permission_level

    def truncate_all(self) -> None:
        """Truncate all auth tables (for testing)."""
        with self._conn.transaction() as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            existing = {row["tablename"] for row in cur.fetchall()}
            tables = []
            for t in [
                "password_reset_tokens",
                "dataset_permissions",
                "api_keys",
                "users",
            ]:
                if t in existing:
                    tables.append(sql.Identifier(t))
            if tables:
                cur.execute(
                    sql.SQL("TRUNCATE {tables} RESTART IDENTITY CASCADE").format(
                        tables=sql.SQL(", ").join(tables)
                    )
                )
