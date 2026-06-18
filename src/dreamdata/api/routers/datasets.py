"""
Dataset API endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from dreamdata.api.dependencies import get_engine
from dreamdata.api.models import (
    DatasetInfo,
    DatasetListResponse,
)
from dreamdata.errors import DatasetAlreadyExists, DatasetNotFound
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _dataset_info(engine: Engine, name: str) -> DatasetInfo:
    """Get dataset info."""
    info = engine.info(name)
    versions = engine.list_versions(name)
    # Get created_at from the first version or use a default
    created_at = datetime.now()
    if versions and hasattr(versions[0], "created_at"):
        created_at = versions[0].created_at
    return DatasetInfo(
        name=name,
        row_count=info.row_count,
        version_count=len(versions),
        created_at=created_at,
        updated_at=created_at,
    )


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    engine: Engine = Depends(get_engine),
) -> DatasetListResponse:
    """List all datasets."""
    names = engine.list_datasets()
    datasets = []
    for name in names:
        try:
            datasets.append(_dataset_info(engine, name))
        except DatasetNotFound:
            continue
    return DatasetListResponse(datasets=datasets, total=len(datasets))


@router.get("/{name}", response_model=DatasetInfo)
def get_dataset(
    name: str,
    engine: Engine = Depends(get_engine),
) -> DatasetInfo:
    """Get dataset info."""
    try:
        return _dataset_info(engine, name)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DatasetInfo)
async def register_dataset(
    name: str,
    file: UploadFile = File(...),
    overwrite: bool = False,
    engine: Engine = Depends(get_engine),
) -> DatasetInfo:
    """Register a new dataset from JSONL file upload."""
    import tempfile
    from pathlib import Path

    # Save uploaded file to temp
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".jsonl", delete=False) as f:
        content = await file.read()
        f.write(content)
        temp_path = Path(f.name)

    try:
        engine.register_dataset(name, [temp_path], overwrite=overwrite)
        return _dataset_info(engine, name)
    except DatasetAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dataset '{name}' already exists",
        )
    finally:
        temp_path.unlink(missing_ok=True)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    name: str,
    engine: Engine = Depends(get_engine),
) -> None:
    """Delete a dataset."""
    try:
        engine.delete_dataset(name)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("/{name}/rename", response_model=DatasetInfo)
def rename_dataset(
    name: str,
    new_name: str,
    engine: Engine = Depends(get_engine),
) -> DatasetInfo:
    """Rename a dataset."""
    try:
        engine.rename_dataset(name, new_name)
        return _dataset_info(engine, new_name)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )
    except DatasetAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dataset '{new_name}' already exists",
        )
