"""Authentication and permission system for v0.4.0."""

from dreamdata.auth.core import (
    PasswordHelper,
    TokenHelper,
    APIKeyHelper,
)
from dreamdata.auth.models import (
    User,
    APIKey,
    DatasetPermission,
    LoginRequest,
    LoginResponse,
    ChangePasswordRequest,
    CreateAPIKeyRequest,
    CreateUserRequest,
    UpdateUserRequest,
    GrantPermissionRequest,
    UpdatePermissionRequest,
    SetupRequest,
    SetupResponse,
)
from dreamdata.auth.repository import (
    AuthRepository,
    UserRow,
    APIKeyRow,
    DatasetPermissionRow,
)
from dreamdata.auth.dependencies import (
    get_current_user,
    get_current_user_or_anonymous,
    require_admin,
    require_dataset_permission,
    PermissionLevel,
)

__all__ = [
    "PasswordHelper",
    "TokenHelper",
    "APIKeyHelper",
    "User",
    "APIKey",
    "DatasetPermission",
    "LoginRequest",
    "LoginResponse",
    "ChangePasswordRequest",
    "CreateAPIKeyRequest",
    "CreateUserRequest",
    "UpdateUserRequest",
    "GrantPermissionRequest",
    "UpdatePermissionRequest",
    "SetupRequest",
    "SetupResponse",
    "AuthRepository",
    "UserRow",
    "APIKeyRow",
    "DatasetPermissionRow",
    "get_current_user",
    "get_current_user_or_anonymous",
    "require_admin",
    "require_dataset_permission",
    "PermissionLevel",
]
