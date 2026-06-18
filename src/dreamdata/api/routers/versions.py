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
from dreamdata.errors import DatasetNotFound
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}/versions", tags=["versions"])


# In-memory job storage for async operations
_jobs: dict[str, JobStatus] = {}


def _version_info(version: Any) -> VersionInfo:
    """Convert version dict to response model."""
    return VersionInfo(
        version_id=getattr(version, "version_id", getattr(version, "id", 0)),
        version_number=getattr(version, "version_number", 1),
        row_count=getattr(version, "row_count", 0),
        created_at=getattr(version, "created_at", datetime.now()),
        parent_version=getattr(version, "parent_version", None),
    )


def _df_to_rows(df: Any, offset: int, limit: int) -> list[RowResponse]:
    """Convert DataFrame to RowResponse list with pagination."""
    rows = []
    for i, row in df.iterrows():
        if i < offset:
            continue
        if i >= offset + limit:
            break
        rows.append(
            RowResponse(
                row_idx=int(row["row_idx"]),
                data=row["data"],
                tags=[],
            )
        )
    return rows


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
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.get("/{version_number}", response_model=SearchResponse)
def get_version(
    name: str,
    version_number: int,
    limit: int = 100,
    offset: int = 0,
    engine: Engine = Depends(get_engine),
) -> SearchResponse:
    """Get a specific version with rows."""
    try:
        dataset = engine.open_dataset(name, version_number=version_number)
        df = dataset.scan()
        result_rows = _df_to_rows(df, offset, limit)
        return SearchResponse(rows=result_rows, total=dataset.row_count)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("/{version_number}/append", response_model=JobStatus)
def append_rows(
    name: str,
    version_number: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Append rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.now(),
    )
    _jobs[job_id] = job

    def _do_append() -> None:
        job.status = "completed"
        job.completed_at = datetime.now()

    background_tasks.add_task(_do_append)
    return job


@router.post("/{version_number}/map", response_model=JobStatus)
def map_rows(
    name: str,
    version_number: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Map rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.now(),
    )
    _jobs[job_id] = job

    def _do_map() -> None:
        job.status = "completed"
        job.completed_at = datetime.now()

    background_tasks.add_task(_do_map)
    return job


@router.post("/{version_number}/filter-map", response_model=JobStatus)
def filter_map_rows(
    name: str,
    version_number: int,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Filter and map rows (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.now(),
    )
    _jobs[job_id] = job

    def _do_filter_map() -> None:
        job.status = "completed"
        job.completed_at = datetime.now()

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
