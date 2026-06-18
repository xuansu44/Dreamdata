"""
Tag and note API endpoints.
"""

from datetime import datetime

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
from dreamdata.errors import DatasetNotFound
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
        tags_list = dataset.tags(user_id=user_id)
        # Extract unique tags
        unique_tags: set[str] = set()
        row_tags: dict[int, list[str]] = {}
        for row_idx, tag in tags_list:
            unique_tags.add(tag)
            if row_idx not in row_tags:
                row_tags[row_idx] = []
            row_tags[row_idx].append(tag)
        return TagsListResponse(tags=list(unique_tags), row_tags=row_tags)
    except DatasetNotFound:
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
        dataset.tag(request.row_idx, request.tag)
    except DatasetNotFound:
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
        dataset.remove_tag(request.row_idx, request.tag)
    except DatasetNotFound:
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
        notes_list = dataset.notes(user_id=user_id)
        notes = []
        now = datetime.now()
        for _note_id, row_idx, body in notes_list:
            notes.append(
                NoteResponse(
                    row_idx=row_idx,
                    note=body,
                    created_at=now,
                    updated_at=now,
                )
            )
        return NotesListResponse(notes=notes)
    except DatasetNotFound:
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
        dataset.note(request.row_idx, request.note)
    except DatasetNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{name}' not found",
        )
