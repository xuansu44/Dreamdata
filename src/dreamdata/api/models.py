"""
API request/response models.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetInfo(BaseModel):
    """Dataset information response."""

    name: str
    row_count: int
    version_count: int
    created_at: datetime
    updated_at: datetime


class DatasetListResponse(BaseModel):
    """List of datasets."""

    datasets: list[DatasetInfo]
    total: int


class VersionInfo(BaseModel):
    """Version information response."""

    version_id: int
    version_number: int
    row_count: int
    created_at: datetime
    parent_version: int | None = None


class VersionListResponse(BaseModel):
    """List of versions."""

    versions: list[VersionInfo]
    total: int


class TagCreateRequest(BaseModel):
    """Request to add a tag."""

    row_idx: int
    tag: str


class TagRemoveRequest(BaseModel):
    """Request to remove a tag."""

    row_idx: int
    tag: str


class TagsListResponse(BaseModel):
    """List of tags."""

    tags: list[str]
    row_tags: dict[int, list[str]]


class NoteCreateRequest(BaseModel):
    """Request to add a note."""

    row_idx: int
    note: str


class NoteResponse(BaseModel):
    """Note response."""

    row_idx: int
    note: str
    created_at: datetime
    updated_at: datetime


class NotesListResponse(BaseModel):
    """List of notes."""

    notes: list[NoteResponse]


class FieldSearchRequest(BaseModel):
    """Field search request."""

    field_path: str
    value: Any


class TagSearchRequest(BaseModel):
    """Tag search request."""

    tag: str


class RowResponse(BaseModel):
    """Single row response."""

    row_idx: int
    data: dict[str, Any]
    tags: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Search results response."""

    rows: list[RowResponse]
    total: int


class ScanRequest(BaseModel):
    """Scan request with pagination."""

    limit: int = 100
    offset: int = 0
    version_id: int | None = None


class IndexCreateRequest(BaseModel):
    """Create index request."""

    field_path: str


class IndexInfo(BaseModel):
    """Index information."""

    field_path: str
    created_at: datetime


class IndexListResponse(BaseModel):
    """List of indexes."""

    indexes: list[IndexInfo]
    total: int


class ParquetCacheRefreshRequest(BaseModel):
    """Refresh Parquet cache request."""

    fields: list[str] | None = None


class ParquetCacheInfo(BaseModel):
    """Parquet cache information."""

    cache_id: str
    fields: list[str] | None
    created_at: datetime
    row_count: int


class ParquetCacheListResponse(BaseModel):
    """List of Parquet caches."""

    caches: list[ParquetCacheInfo]
    total: int


class JobStatus(BaseModel):
    """Async job status."""

    job_id: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
