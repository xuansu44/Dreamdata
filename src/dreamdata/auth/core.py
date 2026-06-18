"""Password hashing, JWT token generation, and API key utilities."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

# Argon2 is optional - if not available, fall back to bcrypt or PBKDF2
try:
    import argon2
    from argon2.exceptions import VerifyMismatchError

    _HAS_ARGON2 = True
except ImportError:
    _HAS_ARGON2 = False


class PasswordHelper:
    """Password hashing and verification using Argon2id (best practice) or PBKDF2 fallback."""

    # Argon2 parameters - tuned for ~100ms on modern hardware
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536  # 64MB
    ARGON2_PARALLELISM = 4
    ARGON2_SALT_LENGTH = 16
    ARGON2_HASH_LENGTH = 32

    # PBKDF2 fallback parameters
    PBKDF2_ITERATIONS = 310000
    PBKDF2_HASH_NAME = "sha256"
    PBKDF2_SALT_LENGTH = 16
    PBKDF2_KEY_LENGTH = 32

    # Prefix to identify hash type
    ARGON2_PREFIX = b"$argon2id$"
    PBKDF2_PREFIX = b"$pbkdf2$"

    def __init__(self) -> None:
        if _HAS_ARGON2:
            self._hasher = argon2.PasswordHasher(
                time_cost=self.ARGON2_TIME_COST,
                memory_cost=self.ARGON2_MEMORY_COST,
                parallelism=self.ARGON2_PARALLELISM,
                salt_len=self.ARGON2_SALT_LENGTH,
                hash_len=self.ARGON2_HASH_LENGTH,
            )

    def hash_password(self, password: str) -> tuple[bytes, bytes]:
        """Hash a password. Returns (hashed_password, salt)."""
        password_bytes = password.encode("utf-8")

        if _HAS_ARGON2:
            # Argon2 includes salt in the hash string itself
            hashed = self._hasher.hash(password_bytes)
            return hashed.encode("utf-8"), b""

        # PBKDF2 fallback
        salt = os.urandom(self.PBKDF2_SALT_LENGTH)
        hashed = hashlib.pbkdf2_hmac(
            self.PBKDF2_HASH_NAME,
            password_bytes,
            salt,
            self.PBKDF2_ITERATIONS,
            self.PBKDF2_KEY_LENGTH,
        )
        # Combine prefix + iterations + salt + hash for storage
        storage = (
            self.PBKDF2_PREFIX
            + str(self.PBKDF2_ITERATIONS).encode("utf-8")
            + b"$"
            + base64.b64encode(salt)
            + b"$"
            + base64.b64encode(hashed)
        )
        return storage, salt

    def verify_password(self, password: str, hashed_password: bytes) -> bool:
        """Verify a password against a stored hash."""
        password_bytes = password.encode("utf-8")

        if hashed_password.startswith(self.ARGON2_PREFIX):
            if not _HAS_ARGON2:
                raise RuntimeError("Argon2 not available but password uses Argon2")
            try:
                self._hasher.verify(hashed_password.decode("utf-8"), password_bytes)
                return True
            except VerifyMismatchError:
                return False

        if hashed_password.startswith(self.PBKDF2_PREFIX):
            # Parse PBKDF2 format: $pbkdf2$iterations$salt_b64$hash_b64
            parts = hashed_password.split(b"$")
            if len(parts) != 5:
                return False
            try:
                iterations = int(parts[2])
                salt = base64.b64decode(parts[3])
                stored_hash = base64.b64decode(parts[4])
            except (ValueError, TypeError):
                return False
            computed = hashlib.pbkdf2_hmac(
                self.PBKDF2_HASH_NAME, password_bytes, salt, iterations, self.PBKDF2_KEY_LENGTH
            )
            # Constant time comparison
            return secrets.compare_digest(computed, stored_hash)

        return False


class TokenHelper:
    """JWT token generation and verification."""

    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def create_access_token(self, *, user_id: int, username: str, role: str) -> str:
        """Create a short-lived access token."""
        expire = datetime.now(UTC) + timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "role": role,
            "type": "access",
            "exp": expire,
            "iat": datetime.now(UTC),
        }
        return jwt.encode(to_encode, self._secret_key, algorithm=self.ALGORITHM)

    def create_refresh_token(self, *, user_id: int) -> str:
        """Create a long-lived refresh token."""
        expire = datetime.now(UTC) + timedelta(days=self.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(UTC),
        }
        return jwt.encode(to_encode, self._secret_key, algorithm=self.ALGORITHM)

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify a token and return its payload, or None if invalid."""
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self.ALGORITHM])
            return payload
        except JWTError:
            return None

    def verify_access_token(self, token: str) -> tuple[int, str, str] | None:
        """Verify an access token. Returns (user_id, username, role) or None."""
        payload = self.verify_token(token)
        if payload is None or payload.get("type") != "access":
            return None
        try:
            user_id = int(payload["sub"])
            username = payload["username"]
            role = payload["role"]
            return user_id, username, role
        except (KeyError, ValueError, TypeError):
            return None

    def verify_refresh_token(self, token: str) -> int | None:
        """Verify a refresh token. Returns user_id or None."""
        payload = self.verify_token(token)
        if payload is None or payload.get("type") != "refresh":
            return None
        try:
            return int(payload["sub"])
        except (KeyError, ValueError, TypeError):
            return None


class APIKeyHelper:
    """API key generation and verification."""

    KEY_PREFIX = "dk_"  # Dreamdata Key
    KEY_LENGTH = 32  # bytes of randomness
    PREFIX_LENGTH = 8  # characters for key_prefix field

    def __init__(self) -> None:
        pass

    def generate_api_key(self) -> tuple[str, str, bytes]:
        """Generate a new API key. Returns (full_key, key_prefix, key_hash)."""
        # Generate random bytes
        random_bytes = secrets.token_bytes(self.KEY_LENGTH)
        # Base64 encode without padding
        key_part = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("utf-8")
        full_key = self.KEY_PREFIX + key_part

        # Hash for storage
        key_hash = hashlib.sha256(full_key.encode("utf-8")).digest()
        # Prefix for lookup
        key_prefix = full_key[: self.PREFIX_LENGTH + len(self.KEY_PREFIX)]

        return full_key, key_prefix, key_hash

    def hash_api_key(self, api_key: str) -> tuple[str, bytes]:
        """Hash an API key for lookup. Returns (key_prefix, key_hash)."""
        key_hash = hashlib.sha256(api_key.encode("utf-8")).digest()
        key_prefix = api_key[: self.PREFIX_LENGTH + len(self.KEY_PREFIX)]
        return key_prefix, key_hash

    def is_valid_api_key_format(self, api_key: str) -> bool:
        """Check if an API key has the correct format."""
        if not api_key.startswith(self.KEY_PREFIX):
            return False
        # Should be prefix + base64 (no padding)
        key_part = api_key[len(self.KEY_PREFIX):]
        try:
            # Try to decode to verify it's valid base64
            # Note: we don't care about the result, just that it's valid
            base64.urlsafe_b64decode(key_part + "==")
            return True
        except Exception:
            return False
