"""
Tag and note API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from dreamdata.api.dependencies import get_engine, get_user_id
from dreamdata.api.models import (
    NoteCreateRequest,
    NoteResponse,
    NotesListResponse,
    TagCreateRequest,
    TagRemoveRequest,
    TagsListResponse,
)
from dreamdata.errors import DatasetNotFoundError
from dreamdata.sdk import Engine

router = APIRouter(prefix="/datasets/{name}", tags=["annotations"])


@router.get("/tags", response_model=TagsListResponse)
def list_tags(
    name: str,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> TagsListResponse:
    """List all tags for a dataset."""
    try:
        dataset = engine.open_dataset(name)
        tags = dataset.tags(user_id=user_id)
        row_tags = {}
        for tag in tags:
            rows = dataset.search_by_tag(tag, user_id=user_id)
            for row in rows:
                if row.row_idx not in row_tags:
                    row_tags[row.row_idx] = []
                row_tags[row.row_idx].append(tag)
        return TagsListResponse(tags=list(tags), row_tags=row_tags)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("/tags", status_code=status.HTTP_201_CREATED)
def add_tag(
    name: str,
    request: TagCreateRequest,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> None:
    """Add a tag to a row."""
    try:
        dataset = engine.open_dataset(name)
        dataset.tag(request.row_idx, request.tag, user_id=user_id)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.delete("/tags")
def remove_tag(
    name: str,
    request: TagRemoveRequest,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> None:
    """Remove a tag from a row."""
    try:
        dataset = engine.open_dataset(name)
        dataset.remove_tag(request.row_idx, request.tag, user_id=user_id)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.get("/notes", response_model=NotesListResponse)
def list_notes(
    name: str,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> NotesListResponse:
    """List all notes for a dataset."""
    try:
        dataset = engine.open_dataset(name)
        notes_dict = dataset.notes(user_id=user_id)
        notes = [
            NoteResponse(
                row_idx=row_idx,
                note=n["note"],
                created_at=n["created_at"],
                updated_at=n["updated_at"],
            )
            for row_idx, n in notes_dict.items()
        ]
        return NotesListResponse(notes=notes)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    name: str,
    request: NoteCreateRequest,
    user_id: str = Depends(get_user_id),
    engine: Engine = Depends(get_engine),
) -> None:
    """Add a note to a row."""
    try:
        dataset = engine.open_dataset(name)
        dataset.note(request.row_idx, request.note, user_id=user_id)
    except DatasetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )
