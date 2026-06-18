"""
Search API endpoints.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from dreamdata.api.dependencies import get_engine, get_user_id
from dreamdata.api.models import RowResponse, SearchResponse
from dreamdata.errors import DatasetNotFoundError
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}", tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_by_field(
    name: str,
    field_path: str,
    value: str,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> SearchResponse:
    """Search by field value."""
    try:
        dataset = engine.open_dataset(name)
        # Try to parse value appropriately
        parsed_value: Any = value
        if value.lower() == "true":
            parsed_value = True
        elif value.lower() == "false":
            parsed_value = False
        elif value.isdigit():
            parsed_value = int(value)
        elif value.replace(".", "", 1).isdigit() and value.count(".") <= 1:
            parsed_value = float(value)

        rows = dataset.search_by_field(field_path, parsed_value)
        result_rows = []
        for i, row in enumerate(rows):
            if i < offset:
                continue
            if i >= offset + limit:
                break
            result_rows.append(
                RowResponse(
                    row_idx=row.row_idx,
                    data=row.data,
                    tags=row.tags,
                )
            )
        return SearchResponse(rows=result_rows, total=len(rows))
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.get("/search-by-tag", response_model=SearchResponse)
def search_by_tag(
    name: str,
    tag: str,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> SearchResponse:
    """Search by tag."""
    try:
        dataset = engine.open_dataset(name)
        rows = dataset.search_by_tag(tag, user_id=user_id)
        result_rows = []
        for i, row in enumerate(rows):
            if i < offset:
                continue
            if i >= offset + limit:
                break
            result_rows.append(
                RowResponse(
                    row_idx=row.row_idx,
                    data=row.data,
                    tags=row.tags,
                )
            )
        return SearchResponse(rows=result_rows, total=len(rows))
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.get("/scan", response_model=SearchResponse)
def scan(
    name: str,
    limit: int = 100,
    offset: int = 0,
    version_id: int | None = None,
    engine: Engine = Depends(get_engine),
) -> SearchResponse:
    """Scan rows with pagination."""
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
