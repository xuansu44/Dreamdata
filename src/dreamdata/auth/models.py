"""Pydantic models for auth API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# Permission level type
PermissionLevel = Literal["owner", "read_write", "read_only"]
UserRole = Literal["admin", "user"]


# ============================================
# Base models for database rows
# ============================================


class UserBase(BaseModel):
    """Base user model with common fields."""

    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class User(UserBase):
    """Public user model (no sensitive data)."""

    model_config = {"from_attributes": True}


class APIKeyBase(BaseModel):
    """Base API key model."""

    id: int
    user_id: int
    key_prefix: str
    name: str | None
    scopes: list[str] | None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    is_active: bool


class APIKey(APIKeyBase):
    """API key model (no key_hash)."""

    model_config = {"from_attributes": True}


class APIKeyWithSecret(APIKey):
    """API key with the full secret (only returned at creation time)."""

    secret: str


class DatasetPermissionBase(BaseModel):
    """Base dataset permission model."""

    id: int
    dataset_id: int
    user_id: int
    permission_level: PermissionLevel
    granted_by: int | None
    granted_at: datetime
    expires_at: datetime | None


class DatasetPermission(DatasetPermissionBase):
    """Dataset permission model with user info."""

    user: User | None = None
    model_config = {"from_attributes": True}


class DatasetPermissionWithDataset(DatasetPermission):
    """Permission with dataset name included."""

    dataset_name: str


# ============================================
# Request models
# ============================================


class SetupRequest(BaseModel):
    """Request to set up the initial admin user."""

    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str | None = None
    expires_in_days: int | None = Field(None, ge=1, le=365)


class CreateUserRequest(BaseModel):
    """Request to create a new user (admin only)."""

    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = "user"

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UpdateUserRequest(BaseModel):
    """Request to update a user."""

    username: str | None = Field(None, min_length=3, max_length=64)
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class GrantPermissionRequest(BaseModel):
    """Request to grant a dataset permission."""

    user_id: int
    permission_level: PermissionLevel
    expires_at: datetime | None = None


class UpdatePermissionRequest(BaseModel):
    """Request to update an existing permission."""

    permission_level: PermissionLevel
    expires_at: datetime | None = None


# ============================================
# Response models
# ============================================


class SetupResponse(BaseModel):
    """Response from initial setup."""

    success: bool
    user: User


class LoginResponse(BaseModel):
    """Response from successful login."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    refresh_token: str
    user: User


class TokenRefreshResponse(BaseModel):
    """Response from token refresh."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class ListResponse(BaseModel):
    """Generic list response."""

    items: list[Any]
    total: int
