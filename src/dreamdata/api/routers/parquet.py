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
from dreamdata.errors import DatasetNotFound
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}/parquet-cache", tags=["parquet"])


# In-memory job storage
_jobs: dict[str, JobStatus] = {}


@router.get("", response_model=ParquetCacheListResponse)
def list_parquet_caches(
    name: str,
    engine: Engine = Depends(get_engine),
) -> ParquetCacheListResponse:
    """List all Parquet caches for a dataset."""
    try:
        dataset = engine.open_dataset(name)
        caches = dataset.list_parquet_caches()
        result = []
        now = datetime.now()
        for cache in caches:
            cache_info = ParquetCacheInfo(
                cache_id=getattr(cache, "cache_id", ""),
                fields=getattr(cache, "fields", None),
                created_at=getattr(cache, "created_at", now),
                row_count=getattr(cache, "row_count", 0),
            )
            result.append(cache_info)
        return ParquetCacheListResponse(
            caches=result,
            total=len(result),
        )
    except DatasetNotFound:
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
        created_at=datetime.now(),
    )
    _jobs[job_id] = job

    def _do_refresh() -> None:
        try:
            dataset = engine.open_dataset(name)
            # SDK uses field_path parameter, not fields
            if fields and len(fields) == 1:
                dataset.refresh_parquet_cache(field_path=fields[0])
            else:
                dataset.refresh_parquet_cache(field_path=None)
            job.status = "completed"
            job.result = {"success": True}
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
        job.completed_at = datetime.now()

    background_tasks.add_task(_do_refresh)
    return job
