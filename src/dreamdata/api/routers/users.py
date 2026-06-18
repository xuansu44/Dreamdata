"""
User management endpoints (admin only).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from dreamdata.api.dependencies import get_meta_conn_for_api, get_settings_for_api
from dreamdata.auth.dependencies import (
    get_current_user,
    get_password_helper,
    init_auth_helpers,
    require_admin,
)
from dreamdata.auth.models import (
    CreateUserRequest,
    MessageResponse,
    UpdateUserRequest,
    User,
)
from dreamdata.auth.repository import AuthRepository, UserRow

router = APIRouter(prefix="/users", tags=["users"])


def ensure_init() -> None:
    """Ensure auth helpers are initialized."""
    settings = get_settings_for_api()
    init_auth_helpers(settings)


@router.get("", response_model=list[User])
async def list_users(
    admin: UserRow = Depends(require_admin),
) -> list[User]:
    """List all users (admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    users = auth_repo.list_users()
    return [
        User(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: UserRow = Depends(get_current_user),
) -> User:
    """Get current user's information."""
    return User(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login_at=current_user.last_login_at,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: int,
    current_user: UserRow = Depends(get_current_user),
) -> User:
    """Get a user's information (self or admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    if user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission",
        )

    user = auth_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return User(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("", response_model=User)
async def create_user(
    request: CreateUserRequest,
    admin: UserRow = Depends(require_admin),
) -> User:
    """Create a new user (admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    # Check if username exists
    if auth_repo.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    # Check if email exists
    if auth_repo.get_user_by_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    password_helper = get_password_helper()
    hashed_pw, salt = password_helper.hash_password(request.password)

    user = auth_repo.create_user(
        username=request.username,
        email=request.email,
        hashed_password=hashed_pw,
        salt=salt,
        role=request.role,
    )

    return User(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.patch("/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    current_user: UserRow = Depends(get_current_user),
) -> User:
    """Update a user (self or admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    if user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission",
        )

    # Check username/email uniqueness if changing
    if request.username and request.username != current_user.username:
        existing = auth_repo.get_user_by_username(request.username)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

    if request.email and request.email != current_user.email:
        existing = auth_repo.get_user_by_email(request.email)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )

    # Only admin can change role or is_active
    role = request.role if current_user.role == "admin" else None
    is_active = request.is_active if current_user.role == "admin" else None

    updated = auth_repo.update_user(
        user_id=user_id,
        username=request.username,
        email=request.email,
        role=role,
        is_active=is_active,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return User(
        id=updated.id,
        username=updated.username,
        email=updated.email,
        role=updated.role,
        is_active=updated.is_active,
        last_login_at=updated.last_login_at,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    admin: UserRow = Depends(require_admin),
) -> MessageResponse:
    """Delete a user (admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)

    user = auth_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Can't delete yourself
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    auth_repo.delete_user(user_id)
    return MessageResponse(message="User deleted successfully")
