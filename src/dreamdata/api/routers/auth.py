"""
Authentication endpoints - initial setup, login, password change, API keys.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dreamdata.api.dependencies import get_meta_conn_for_api, get_settings_for_api
from dreamdata.auth.dependencies import (
    get_api_key_helper,
    get_current_user,
    get_password_helper,
    get_token_helper,
    init_auth_helpers,
)
from dreamdata.auth.models import (
    APIKey,
    APIKeyWithSecret,
    ChangePasswordRequest,
    CreateAPIKeyRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    SetupRequest,
    SetupResponse,
    TokenRefreshResponse,
    User,
)
from dreamdata.auth.repository import AuthRepository, UserRow

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupStatusResponse(BaseModel):
    """Response for setup status check."""

    needs_setup: bool


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""

    refresh_token: str


def ensure_init() -> None:
    """Ensure auth helpers are initialized."""
    settings = get_settings_for_api()
    init_auth_helpers(settings)


@router.post("/setup", response_model=SetupResponse)
async def setup(request: SetupRequest) -> SetupResponse:
    """
    Initial setup - create the first admin user.
    Only available if no users exist.
    """
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    # Check if users already exist
    if auth_repo.count_users() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed",
        )

    password_helper = get_password_helper()
    hashed_pw, salt = password_helper.hash_password(request.password)

    user = auth_repo.create_user(
        username=request.username,
        email=request.email,
        hashed_password=hashed_pw,
        salt=salt,
        role="admin",
    )

    return SetupResponse(
        success=True,
        user=User(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Login with username and password.
    Returns access_token (JWT) and refresh_token.
    """
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    user = auth_repo.get_user_by_username(request.username)
    if not user:
        # Try by email
        user = auth_repo.get_user_by_email(request.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    password_helper = get_password_helper()
    if not password_helper.verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token_helper = get_token_helper()
    access_token = token_helper.create_access_token(
        user_id=user.id, username=user.username, role=user.role
    )
    refresh_token = token_helper.create_refresh_token(user_id=user.id)

    auth_repo.update_last_login(user.id)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=token_helper.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh_token,
        user=User(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: UserRow = Depends(get_current_user),
) -> MessageResponse:
    """Change current user's password."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    # Verify current password
    password_helper = get_password_helper()
    user = auth_repo.get_user_by_id(current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not password_helper.verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password incorrect",
        )

    # Update password
    hashed_pw, salt = password_helper.hash_password(request.new_password)
    auth_repo.update_user_password(user_id=user.id, hashed_password=hashed_pw, salt=salt)

    return MessageResponse(message="Password changed successfully")


@router.get("/api-keys", response_model=list[APIKey])
async def list_api_keys(
    current_user: UserRow = Depends(get_current_user),
) -> list[APIKey]:
    """List all API keys for current user."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    keys = auth_repo.list_api_keys_for_user(current_user.id)
    return [
        APIKey(
            id=k.id,
            user_id=k.user_id,
            key_prefix=k.key_prefix,
            name=k.name,
            scopes=k.scopes,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
            is_active=k.is_active,
        )
        for k in keys
    ]


@router.post("/api-keys", response_model=APIKeyWithSecret)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: UserRow = Depends(get_current_user),
) -> APIKeyWithSecret:
    """Create a new API key."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    api_key_helper = get_api_key_helper()
    secret, key_prefix, key_hash = api_key_helper.generate_api_key()

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=request.expires_in_days)

    key = auth_repo.create_api_key(
        user_id=current_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=request.name,
        scopes=None,
        expires_at=expires_at,
    )

    return APIKeyWithSecret(
        id=key.id,
        user_id=key.user_id,
        key_prefix=key.key_prefix,
        name=key.name,
        scopes=key.scopes,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        is_active=key.is_active,
        secret=secret,
    )


@router.delete("/api-keys/{key_id}", response_model=MessageResponse)
async def revoke_api_key(
    key_id: int,
    current_user: UserRow = Depends(get_current_user),
) -> MessageResponse:
    """Revoke an API key."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    revoked = auth_repo.revoke_api_key(key_id, current_user.id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return MessageResponse(message="API key revoked successfully")


@router.get("/setup/status", response_model=SetupStatusResponse)
async def setup_status() -> SetupStatusResponse:
    """Check if initial setup is needed."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    needs_setup = auth_repo.count_users() == 0
    return SetupStatusResponse(needs_setup=needs_setup)


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(request: RefreshTokenRequest) -> TokenRefreshResponse:
    """Refresh access token using a refresh token."""
    ensure_init()
    token_helper = get_token_helper()

    try:
        payload = token_helper.verify_token(request.refresh_token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        token_type = payload.get("type")
        if token_type != "refresh":  # noqa: S105
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        # Verify user still exists and is active
        meta_conn = get_meta_conn_for_api()
        auth_repo = AuthRepository(meta_conn)
        user = auth_repo.get_user_by_id(int(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or disabled",
            )

        # Create new access token
        access_token = token_helper.create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
        )

        return TokenRefreshResponse(
            access_token=access_token,
            token_type="bearer",  # noqa: S106
            expires_in=token_helper.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
