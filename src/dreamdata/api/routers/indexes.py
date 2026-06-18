"""
Index API endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from dreamdata.api.dependencies import get_engine
from dreamdata.api.models import IndexInfo, IndexListResponse
from dreamdata.errors import DatasetNotFound
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}/indexes", tags=["indexes"])


@router.get("", response_model=IndexListResponse)
def list_indexes(
    name: str,
    engine: Engine = Depends(get_engine),
) -> IndexListResponse:
    """List all indexes for a dataset."""
    try:
        dataset = engine.open_dataset(name)
        indexes = dataset.list_indexes()
        now = datetime.now()
        return IndexListResponse(
            indexes=[IndexInfo(field_path=idx.field_path, created_at=now) for idx in indexes],
            total=len(indexes),
        )
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_index(
    name: str,
    field_path: str,
    engine: Engine = Depends(get_engine),
) -> None:
    """Create an index on a field."""
    try:
        dataset = engine.open_dataset(name)
        dataset.create_index(field_path)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.delete("/{field_path:path}", status_code=status.HTTP_204_NO_CONTENT)
def drop_index(
    name: str,
    field_path: str,
    engine: Engine = Depends(get_engine),
) -> None:
    """Drop an index."""
    try:
        dataset = engine.open_dataset(name)
        dataset.drop_index(field_path)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )
