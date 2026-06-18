"""
API dependencies - authentication, engine access.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, Header

from dreamdata.config import Settings
from dreamdata.sdk import Engine

# Global engine instance
_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the engine instance."""
    global _engine
    if _engine is None:
        # Try to create settings from env or defaults for testing
        kwargs: dict[str, Any] = {}
        if "DATABASE_URL" in os.environ:
            kwargs["database_url"] = os.environ["DATABASE_URL"]
        else:
            kwargs["database_url"] = "postgresql://localhost:5432/dreamdata_test"

        if "WORKSPACE_PATH" in os.environ:
            kwargs["workspace_path"] = Path(os.environ["WORKSPACE_PATH"])
        else:
            kwargs["workspace_path"] = Path("/tmp/dreamdata-test-workspace")

        if "USER_ID" in os.environ:
            kwargs["user_id"] = os.environ["USER_ID"]
        else:
            kwargs["user_id"] = "api-user"

        settings = Settings(**kwargs)
        _engine = Engine(settings=settings)
    return _engine


def verify_api_key(
    x_api_key: str | None = Header(None),
) -> str:
    """Verify API key header. Returns user_id or raises HTTPException."""
    # For v0.3.0, simple API key auth
    # If no key is provided, default to "anonymous"
    if not x_api_key:
        return "anonymous"

    # Accept any non-empty key for now
    # In future versions, this would validate against stored keys
    return x_api_key


def get_user_id(
    x_user_id: str | None = Header(None),
    api_key: str = Depends(verify_api_key),
) -> str:
    """Get user_id from header or derive from API key."""
    if x_user_id:
        return x_user_id
    # If no user_id provided, use API key as user_id
    return api_key
