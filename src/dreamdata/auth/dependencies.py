"""FastAPI dependencies for auth and permissions."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dreamdata.auth.core import APIKeyHelper, PasswordHelper, TokenHelper
from dreamdata.auth.repository import AuthRepository, UserRow
from dreamdata.config import Settings
from dreamdata.meta.connection import MetaConnection
from dreamdata.meta.repository import MetaRepository

# Permission level type
PermissionLevel = Literal["owner", "read_write", "read_only"]
UserRole = Literal["admin", "user"]

# Security scheme for Bearer tokens
security = HTTPBearer(auto_error=False)

# Global helpers (initialized once per app)
_token_helper: TokenHelper | None = None
_password_helper: PasswordHelper | None = None
_api_key_helper: APIKeyHelper | None = None
_settings: Settings | None = None


def init_auth_helpers(settings: Settings) -> None:
    """Initialize auth helpers with settings."""
    global _token_helper, _password_helper, _api_key_helper, _settings
    _settings = settings
    secret_key = getattr(settings, "jwt_secret_key", "dev-secret-key-change-in-production")
    _token_helper = TokenHelper(str(secret_key))
    _password_helper = PasswordHelper()
    _api_key_helper = APIKeyHelper()


def get_token_helper() -> TokenHelper:
    """Get token helper."""
    if _token_helper is None:
        raise RuntimeError("init_auth_helpers not called")
    return _token_helper


def get_password_helper() -> PasswordHelper:
    """Get password helper."""
    if _password_helper is None:
        raise RuntimeError("init_auth_helpers not called")
    return _password_helper


def get_api_key_helper() -> APIKeyHelper:
    """Get API key helper."""
    if _api_key_helper is None:
        raise RuntimeError("init_auth_helpers not called")
    return _api_key_helper


def get_auth_repository(
    meta_conn: MetaConnection,
) -> AuthRepository:
    """Get AuthRepository instance."""
    return AuthRepository(meta_conn)


# ============================================
# User extraction dependencies
# ============================================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_api_key: str | None = Header(None),
) -> UserRow:
    """
    Get current authenticated user.
    Supports both Bearer token (JWT) and X-API-Key header.
    Raises 401 if not authenticated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    from dreamdata.api.dependencies import get_meta_conn_for_api
    from dreamdata.auth.repository import AuthRepository

    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    # Try Bearer token first
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
        token_helper = get_token_helper()
        result = token_helper.verify_access_token(token)
        if result:
            user_id, _, _ = result
            user = auth_repo.get_user_by_id(user_id)
            if user and user.is_active:
                auth_repo.update_last_login(user_id)
                return user

    # Try API key
    if x_api_key:
        api_key_helper = get_api_key_helper()
        if api_key_helper.is_valid_api_key_format(x_api_key):
            key_prefix, _ = api_key_helper.hash_api_key(x_api_key)
            candidates = auth_repo.get_api_key_by_prefix(key_prefix)
            for candidate in candidates:
                if not candidate.is_active:
                    continue
                if candidate.expires_at and candidate.expires_at < datetime.now(UTC):
                    continue
                # Compare hashes
                if hashlib.sha256(x_api_key.encode("utf-8")).digest() == candidate.key_hash:
                    user = auth_repo.get_user_by_id(candidate.user_id)
                    if user and user.is_active:
                        auth_repo.touch_api_key(candidate.id)
                        return user

    raise credentials_exception


async def get_current_user_or_anonymous(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_api_key: str | None = Header(None),
    x_user_id: str | None = Header(None),
) -> UserRow | str:
    """
    Get current user, or fallback to anonymous/compat mode.
    Supports legacy X-User-ID header for backward compatibility.
    Returns UserRow if authenticated, str user_id otherwise.
    """
    try:
        return await get_current_user(credentials, x_api_key)
    except HTTPException:
        # Not authenticated, use legacy user_id or "anonymous"
        if x_user_id:
            return x_user_id
        return "anonymous"


async def require_admin(
    current_user: UserRow = Depends(get_current_user),
) -> UserRow:
    """Require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ============================================
# Dataset permission dependencies
# ============================================


async def require_dataset_permission(
    name: str,
    required_levels: list[PermissionLevel],
    current_user: UserRow | str = Depends(get_current_user_or_anonymous),
) -> tuple[Any, Any, str]:
    """
    Require permission for a dataset.
    Returns (dataset_meta, version_meta, permission_level).
    """
    from dreamdata.api.dependencies import get_meta_conn_for_api
    from dreamdata.auth.repository import AuthRepository

    meta_conn = get_meta_conn_for_api()
    meta_repo = MetaRepository(meta_conn)
    auth_repo = AuthRepository(meta_conn)

    # Get dataset
    try:
        ds, v = meta_repo.get_dataset_by_name(name=name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )

    # If user is a string (legacy/anonymous), check if users table exists
    if isinstance(current_user, str):
        # Backward compatibility: if no users exist, allow access
        if auth_repo.count_users() == 0:
            return ds, v, "owner"
        # Otherwise, anonymous has no access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission",
        )

    # Admin bypass
    if current_user.role == "admin":
        return ds, v, "admin"

    # Check permission
    has_access, actual_level = auth_repo.check_permission(
        dataset_id=ds.id,
        user_id=current_user.id,
        required_levels=required_levels,
        user_role=current_user.role,
    )

    if not has_access:
        # Also check if users table is empty (backward compat)
        if auth_repo.count_users() == 0:
            return ds, v, "owner"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission",
        )

    return ds, v, actual_level or "read_only"


def get_legacy_user_id(
    current_user: UserRow | str = Depends(get_current_user_or_anonymous),
) -> str:
    """
    Get legacy string user_id for backward compatibility.
    If authenticated, returns str(user.id), else returns current_user string.
    """
    if isinstance(current_user, UserRow):
        return str(current_user.id)
    return current_user
