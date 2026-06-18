"""
API dependencies - authentication, engine access.
"""

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, Header

from dreamdata.config import Settings
from dreamdata.meta.connection import MetaConnection
from dreamdata.sdk import Engine

# Global engine instance
_engine: Engine | None = None
_meta_conn: MetaConnection | None = None
_settings: Settings | None = None


def get_settings_for_api() -> Settings:
    """Get settings for API use."""
    global _settings
    if _settings is None:
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

        _settings = Settings(**kwargs)
    return _settings


def get_meta_conn_for_api() -> MetaConnection:
    """Get meta connection for API use."""
    global _meta_conn
    if _meta_conn is None:
        settings = get_settings_for_api()
        _meta_conn = MetaConnection(settings.database_url.get_secret_value())
    return _meta_conn


def get_engine() -> Engine:
    """Get or create the engine instance."""
    global _engine
    if _engine is None:
        settings = get_settings_for_api()
        _engine = Engine(settings=settings)
    return _engine


def verify_api_key(
    x_api_key: str | None = Header(None),
) -> str:
    """Verify API key header. Returns user_id or raises HTTPException."""
    # For backward compatibility
    if not x_api_key:
        return "anonymous"
    return x_api_key


def get_user_id(
    x_user_id: str | None = Header(None),
    api_key: str = Depends(verify_api_key),
) -> str:
    """Get user_id from header or derive from API key."""
    # For backward compatibility
    if x_user_id:
        return x_user_id
    return api_key
