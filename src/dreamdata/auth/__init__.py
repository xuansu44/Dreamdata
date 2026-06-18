"""Authentication and permission system for v0.4.0."""

from dreamdata.auth.core import (
    APIKeyHelper,
    PasswordHelper,
    TokenHelper,
)
from dreamdata.auth.dependencies import (
    PermissionLevel,
    get_current_user,
    get_current_user_or_anonymous,
    require_admin,
    require_dataset_permission,
)
from dreamdata.auth.models import (
    APIKey,
    ChangePasswordRequest,
    CreateAPIKeyRequest,
    CreateUserRequest,
    DatasetPermission,
    GrantPermissionRequest,
    LoginRequest,
    LoginResponse,
    SetupRequest,
    SetupResponse,
    UpdatePermissionRequest,
    UpdateUserRequest,
    User,
)
from dreamdata.auth.repository import (
    APIKeyRow,
    AuthRepository,
    DatasetPermissionRow,
    UserRow,
)

__all__ = [
    "APIKey",
    "APIKeyHelper",
    "APIKeyRow",
    "AuthRepository",
    "ChangePasswordRequest",
    "CreateAPIKeyRequest",
    "CreateUserRequest",
    "DatasetPermission",
    "DatasetPermissionRow",
    "GrantPermissionRequest",
    "LoginRequest",
    "LoginResponse",
    "PasswordHelper",
    "PermissionLevel",
    "SetupRequest",
    "SetupResponse",
    "TokenHelper",
    "UpdatePermissionRequest",
    "UpdateUserRequest",
    "User",
    "UserRow",
    "get_current_user",
    "get_current_user_or_anonymous",
    "require_admin",
    "require_dataset_permission",
]
