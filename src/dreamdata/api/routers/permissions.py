"""
Permission management endpoints.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from dreamdata.api.dependencies import get_meta_conn_for_api, get_settings_for_api
from dreamdata.auth.dependencies import get_current_user, init_auth_helpers
from dreamdata.auth.models import (
    DatasetPermission,
    GrantPermissionRequest,
    MessageResponse,
    UpdatePermissionRequest,
)
from dreamdata.auth.repository import AuthRepository, UserRow
from dreamdata.meta.repository import MetaRepository

router = APIRouter(prefix="/permissions", tags=["permissions"])


def ensure_init() -> None:
    """Ensure auth helpers are initialized."""
    settings = get_settings_for_api()
    init_auth_helpers(settings)


def check_dataset_owner(
    name: str,
    current_user: UserRow,
    auth_repo: AuthRepository,
    meta_repo: MetaRepository,
) -> tuple[Any, Any]:
    """Check if current user is owner/admin of dataset."""
    ds, v = meta_repo.get_dataset_by_name(name=name)

    # Admin bypass
    if current_user.role == "admin":
        return ds, v

    # Check owner permission
    perm = auth_repo.get_dataset_permission(ds.id, current_user.id)
    if not perm or perm.permission_level != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required",
        )

    return ds, v


@router.get("/datasets/{name}", response_model=list[DatasetPermission])
async def list_dataset_permissions(
    name: str,
    current_user: UserRow = Depends(get_current_user),
) -> list[DatasetPermission]:
    """List all permissions for a dataset (owner/admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)
    meta_repo = MetaRepository(meta_conn)

    ds, _ = check_dataset_owner(name, current_user, auth_repo, meta_repo)

    perms = auth_repo.get_user_permissions_for_dataset(ds.id)

    result = []
    for p in perms:
        user = auth_repo.get_user_by_id(p.user_id)
        result.append(
            DatasetPermission(
                id=p.id,
                dataset_id=p.dataset_id,
                user_id=p.user_id,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                user=user,
            )
        )
    return result


@router.post("/datasets/{name}", response_model=DatasetPermission)
async def grant_permission(
    name: str,
    request: GrantPermissionRequest,
    current_user: UserRow = Depends(get_current_user),
) -> DatasetPermission:
    """Grant or update a dataset permission (owner/admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)
    meta_repo = MetaRepository(meta_conn)

    ds, _ = check_dataset_owner(name, current_user, auth_repo, meta_repo)

    # Check if user exists
    user = auth_repo.get_user_by_id(request.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    perm = auth_repo.grant_permission(
        dataset_id=ds.id,
        user_id=user.id,
        permission_level=request.permission_level,
        granted_by=current_user.id,
        expires_at=request.expires_at,
    )

    return DatasetPermission(
        id=perm.id,
        dataset_id=perm.dataset_id,
        user_id=perm.user_id,
        permission_level=perm.permission_level,
        granted_by=perm.granted_by,
        granted_at=perm.granted_at,
        expires_at=perm.expires_at,
        user=user,
    )


@router.patch("/datasets/{name}/users/{user_id}", response_model=DatasetPermission)
async def update_permission(
    name: str,
    user_id: int,
    request: UpdatePermissionRequest,
    current_user: UserRow = Depends(get_current_user),
) -> DatasetPermission:
    """Update a dataset permission (owner/admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)
    meta_repo = MetaRepository(meta_conn)

    ds, _ = check_dataset_owner(name, current_user, auth_repo, meta_repo)

    perm = auth_repo.update_permission_level(
        dataset_id=ds.id,
        user_id=user_id,
        permission_level=request.permission_level,
        expires_at=request.expires_at,
    )

    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found",
        )

    user = auth_repo.get_user_by_id(user_id)
    return DatasetPermission(
        id=perm.id,
        dataset_id=perm.dataset_id,
        user_id=perm.user_id,
        permission_level=perm.permission_level,
        granted_by=perm.granted_by,
        granted_at=perm.granted_at,
        expires_at=perm.expires_at,
        user=user,
    )


@router.delete("/datasets/{name}/users/{user_id}", response_model=MessageResponse)
async def revoke_permission(
    name: str,
    user_id: int,
    current_user: UserRow = Depends(get_current_user),
) -> MessageResponse:
    """Revoke a dataset permission (owner/admin only)."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)
    meta_repo = MetaRepository(meta_conn)

    ds, _ = check_dataset_owner(name, current_user, auth_repo, meta_repo)

    revoked = auth_repo.revoke_permission(ds.id, user_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found",
        )

    return MessageResponse(message="Permission revoked successfully")


@router.get("/me/datasets", response_model=list[dict[str, Any]])
async def get_my_datasets(
    current_user: UserRow = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get all datasets current user has permission for."""
    ensure_init()
    meta_conn = get_meta_conn_for_api()
    auth_repo = AuthRepository(meta_conn)
    meta_repo = MetaRepository(meta_conn)

    # Get all datasets
    datasets = meta_repo.list_datasets()

    # Get user's permissions
    user_ds_ids = auth_repo.get_datasets_for_user(current_user.id)
    user_perm_map = {ds_id: level for ds_id, _, level in user_ds_ids}

    result = []
    for ds in datasets:
        # Admin has access to all
        if current_user.role == "admin":
            result.append(
                {
                    "id": ds.id,
                    "name": ds.name,
                    "permission_level": "admin",
                    "current_version_id": ds.current_version_id,
                }
            )
            continue

        # Check if user has permission
        if ds.id in user_perm_map:
            result.append(
                {
                    "id": ds.id,
                    "name": ds.name,
                    "permission_level": user_perm_map[ds.id],
                    "current_version_id": ds.current_version_id,
                }
            )

    return result
