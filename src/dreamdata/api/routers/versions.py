"""
Version API endpoints.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from dreamdata.api.dependencies import get_engine
from dreamdata.api.models import (
    JobStatus,
    RowResponse,
    SearchResponse,
    VersionInfo,
    VersionListResponse,
)
from dreamdata.errors import DatasetNotFoundError
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}/versions", tags=["versions"])


# In-memory job storage for async operations
_jobs: dict[str, JobStatus] = {}


def _version_info(version: dict[str, Any]) -> VersionInfo:
    """Convert version dict to response model."""
    return VersionInfo(
        version_id=version["version_id"],
        version_number=version["version_number"],
        row_count=version["row_count"],
        created_at=version["created_at"],
        parent_version=version.get("parent_version"),
    )


@router.get("", response_model=VersionListResponse)
def list_versions(
    name: str,
    engine: Engine = Depends(get_engine),
) -> VersionListResponse:
    """List all versions of a dataset."""
    try:
        versions = engine.list_versions(name)
        return VersionListResponse(
            versions=[_version_info(v) for v in versions],
            total=len(versions),
        )
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.get("/{version_id}", response_model=SearchResponse)
def get_version(
    name: str,
    version_id: int,
    limit: int = 100,
    offset: int = 0,
    engine: Engine = Depends(get_engine),
) -> SearchResponse:
    """Get a specific version with rows."""
    try:
        dataset = engine.open_dataset(name, version_id=version_id)
        rows = []
        for i, row in enumerate(dataset.scan()):
            if i < offset:
                continue
            if i >= offset + limit:
                break
            rows.append(
                RowResponse(
                    row_idx=row.row_idx,
                    data=row.data,
                    tags=row.tags,
                )
            )
        return SearchResponse(rows=rows, total=dataset.row_count)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("/{version_id}/append", response_model=JobStatus)
def append_rows(
    name: str,
    version_id: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Append rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.utcnow(),
    )
    _jobs[job_id] = job

    def _do_append():
        job.status = "completed"
        job.completed_at = datetime.utcnow()

    background_tasks.add_task(_do_append)
    return job


@router.post("/{version_id}/map", response_model=JobStatus)
def map_rows(
    name: str,
    version_id: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Map rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.utcnow(),
    )
    _jobs[job_id] = job

    def _do_map():
        job.status = "completed"
        job.completed_at = datetime.utcnow()

    background_tasks.add_task(_do_map)
    return job


@router.post("/{version_id}/filter-map", response_model=JobStatus)
def filter_map_rows(
    name: str,
    version_id: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Filter and map rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.utcnow(),
    )
    _jobs[job_id] = job

    def _do_filter_map():
        job.status = "completed"
        job.completed_at = datetime.utcnow()

    background_tasks.add_task(_do_filter_map)
    return job


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job_status(
    job_id: str,
) -> JobStatus:
    """Get async job status."""
    if job_id not in _jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return _jobs[job_id]
