"""
Parquet cache API endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from dreamdata.api.dependencies import get_engine
from dreamdata.api.models import (
    JobStatus,
    ParquetCacheInfo,
    ParquetCacheListResponse,
)
from dreamdata.errors import DatasetNotFoundError
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}/parquet-cache", tags=["parquet"])


# In-memory job storage
_jobs: dict = {}


@router.get("", response_model=ParquetCacheListResponse)
def list_parquet_caches(
    name: str,
    engine: Engine = Depends(get_engine),
) -> ParquetCacheListResponse:
    """List all Parquet caches for a dataset."""
    try:
        dataset = engine.open_dataset(name)
        caches = dataset.list_parquet_caches()
        return ParquetCacheListResponse(
            caches=[
                ParquetCacheInfo(
                    cache_id=cache["cache_id"],
                    fields=cache.get("fields"),
                    created_at=cache["created_at"],
                    row_count=cache["row_count"],
                )
                for cache in caches
            ],
            total=len(caches),
        )
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("", response_model=JobStatus)
def refresh_parquet_cache(
    name: str,
    background_tasks: BackgroundTasks,
    fields: list[str] | None = None,
    engine: Engine = Depends(get_engine),
) -> JobStatus:
    """Refresh Parquet cache (async job placeholder)."""
    import uuid

    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        created_at=datetime.utcnow(),
    )
    _jobs[job_id] = job

    def _do_refresh():
        try:
            dataset = engine.open_dataset(name)
            dataset.refresh_parquet_cache(fields=fields)
            job.status = "completed"
            job.result = {"success": True}
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        job.completed_at = datetime.utcnow()

    background_tasks.add_task(_do_refresh)
    return job
